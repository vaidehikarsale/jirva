"""
JIRVA - FastAPI Backend (Day 10 Task 4, extended Day 11)
-------------------------------------------------
Exposes the existing pipeline over HTTP. No new AI logic - every endpoint
calls functions already built and verified in Days 7-10 (check_domain,
decide, and the LangGraph app from langgraph_flow.py).

Endpoints:
  POST /ticket/analyze  - classification only (check_domain + decide directly,
                          NOT via the graph). No generation call.
  POST /ticket/resolve  - full pipeline via the LangGraph app. Not persisted.
  POST /ticket/upload   - takes title + description, runs the full pipeline
                          on the DESCRIPTION ALONE (title is display-only -
                          see Day 11 fix note below), assigns a ticket_id,
                          persists the result. Image upload is Day 12 scope.
  GET  /ticket/{id}     - retrieves a previously uploaded ticket by id.
                          404 if not found.
  GET  /tickets         - NEW (Day 11): lightweight summary list of every
                          stored ticket (id, title, category, outcome, risk,
                          created_at), newest first. Powers the Dashboard
                          cards and the Tickets history table. Deliberately
                          excludes full answer/evidence text to keep the
                          list payload light.
  GET  /logs            - paginated processing/error events (event_log.py),
                          newest first. Powers the System Logs page.
  GET  /evaluation       - calibration accuracy (from the frozen, hand-
                          labeled Day 5/9 calibration logs) plus live,
                          unlabeled operational distribution/latency/error
                          stats. Powers the Evaluation page.

Storage: SQLite (JIRVA_DB_FILE, default ../data/jirva.db), via ticket_store.py.
Originally a hand-rolled JSON file (Day 11) with no concurrent-write
locking and a full-file rewrite on every save; migrated to SQLite for real
locking, indexed listing, and crash-safety (see ticket_store.py's docstring
for the full rationale). Existing JSON history is a one-time import via
migrate_tickets_to_sqlite.py, not read directly by this file anymore.

Day 11 fix (upload endpoint): the pipeline (retrieval + ticket_analysis)
runs on `description` ALONE, not title+description concatenated. Title
wording was confirmed live to change retrieval confidence enough to flip
a ticket between FALLBACK and ESCALATE for the same underlying issue.

New dependencies (free, open-source): fastapi, uvicorn
    pip install fastapi uvicorn

Run:
    cd scripts
    uvicorn api:app --reload --port 8000

CORS is currently wide open (allow_origins=["*"]) for local development
with the React frontend. Tighten before deployment (Day 14 checklist item).
"""

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder

from bm25_search import build_bm25_index
from domain_guard import build_reference_embeddings, check_domain
from decision_engine import decide, ESCALATE
from langgraph_flow import build_graph
from jirva import OUT_OF_DOMAIN_MESSAGE
from ticket_store import TicketStore
from event_log import EventLog, timed_event
from evaluation import calibration_summary, live_summary

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"

# Matches the --chunks-dir / --collection values used throughout every CLI
# script so far. Overridable via env vars without touching code.
CHUNKS_DIR = os.getenv("JIRVA_CHUNKS_DIR", "../data/chunks/400_variant")
COLLECTION = os.getenv("JIRVA_COLLECTION", "jirva_400")

# SQLite-backed persistence (see ticket_store.py). Survives uvicorn --reload
# restarts the same way the old JSON file did, but with real concurrent-write
# safety and indexed listing instead of a full-file rewrite per save.
DB_FILE = os.getenv("JIRVA_DB_FILE", "../data/jirva.db")

# Populated once at startup (see lifespan below), reused across requests -
# models/index are loaded once, not per-request, same principle every CLI
# script in this project already follows.
resources = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_dotenv()
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_API_KEY")

    print("Loading models ...")
    resources["embed_model"] = SentenceTransformer(EMBED_MODEL_NAME)
    resources["cross_encoder"] = CrossEncoder(RERANK_MODEL_NAME)
    resources["qdrant_client"] = QdrantClient(url=url, api_key=api_key)

    print(f"Building BM25 index from {CHUNKS_DIR} ...")
    bm25, chunks = build_bm25_index(CHUNKS_DIR)
    resources["bm25"] = bm25
    resources["chunks"] = chunks

    print("Embedding reference ticket set ...")
    ref_texts, ref_embeddings = build_reference_embeddings(resources["embed_model"])
    resources["ref_texts"] = ref_texts
    resources["ref_embeddings"] = ref_embeddings

    print("Building LangGraph app ...")
    resources["graph"] = build_graph(
        resources["qdrant_client"], resources["embed_model"], resources["cross_encoder"],
        resources["bm25"], resources["chunks"], resources["ref_texts"], resources["ref_embeddings"],
        COLLECTION,
    )

    resources["ticket_store"] = TicketStore(DB_FILE)
    print(f"Loaded {resources['ticket_store'].count()} previously stored ticket(s) from {DB_FILE}")

    resources["event_log"] = EventLog(DB_FILE)

    print("Startup complete - JIRVA API ready.")

    yield
    resources.clear()


app = FastAPI(title="JIRVA API", lifespan=lifespan)

# WIDE OPEN for local dev with the Day 11 React frontend. Tighten before
# deployment (Day 14 checklist item) - not addressed today, by design.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    # Without this, the browser's fetch() can't read X-Total-Count at all
    # (CORS hides non-standard response headers from JS by default even
    # though the request itself succeeds) - needed for TicketsList's
    # pagination to compute a page count.
    expose_headers=["X-Total-Count"],
)


class TicketRequest(BaseModel):
    ticket: str


class UploadRequest(BaseModel):
    title: str
    description: str


def _serialize_ticket_analysis(ta: dict) -> dict:
    return {
        "intent": ta["intent"],
        "category": ta["category"],
        "severity": ta["severity"],
        "risk": ta["risk"],
        "domain": ta["domain"],
    }


def _serialize_decision(decision: dict) -> dict:
    return {
        "outcome": decision["outcome"],
        "reason": decision["reason"],
        "category_aligned": bool(decision["category_aligned"]),
    }


@app.get("/")
def health_check():
    """Cheap endpoint to confirm the server is up, before touching anything
    model-related. No pipeline calls, no cost."""
    return {"status": "ok", "service": "JIRVA API"}


@app.post("/ticket/analyze")
def analyze_ticket_endpoint(body: TicketRequest):
    """Classification only - NOT via the graph, no generation call. Calls
    check_domain() + decide() directly, the same functions the graph uses
    internally, just without the conditional generate step."""
    with timed_event(resources["event_log"], "/ticket/analyze", body.ticket) as rec:
        guard_result = check_domain(
            body.ticket, resources["qdrant_client"], resources["embed_model"],
            resources["cross_encoder"], resources["bm25"], resources["chunks"],
            resources["ref_texts"], resources["ref_embeddings"], COLLECTION,
        )
        rec.domain = guard_result["domain"]

        if guard_result["domain"] == "Out-of-Domain":
            return {
                "ticket": body.ticket,
                "domain": "Out-of-Domain",
                "message": OUT_OF_DOMAIN_MESSAGE,
            }

        reranked = guard_result["reranked_evidence"]
        ta = guard_result["analysis"]
        evidence_confidence = float(reranked[0][1]) if reranked else 0.0
        top_evidence_category = reranked[0][0]["category"] if reranked else None

        decision = decide(
            evidence_confidence=evidence_confidence,
            risk=ta["risk"],
            ticket_category=ta["category"],
            top_evidence_category=top_evidence_category,
        )
        rec.outcome = decision["outcome"]

        return {
            "ticket": body.ticket,
            "domain": "Jira",
            "ticket_analysis": _serialize_ticket_analysis(ta),
            "evidence_confidence": evidence_confidence,
            "decision": _serialize_decision(decision),
        }


def _run_full_pipeline(ticket_text: str, endpoint: str) -> dict:
    """Shared by /ticket/resolve and /ticket/upload - runs the LangGraph app
    and returns a clean, JSON-safe response dict. Single source of truth for
    this shape so the two endpoints can't silently drift apart. Also the
    single place logging happens for both callers, so neither can forget to
    record an event."""
    with timed_event(resources["event_log"], endpoint, ticket_text) as rec:
        result = resources["graph"].invoke({"ticket": ticket_text})
        rec.domain = result["domain"]

        if result["domain"] == "Out-of-Domain":
            return {
                "ticket": ticket_text,
                "domain": "Out-of-Domain",
                "answer": result["answer"],
            }

        rec.outcome = result["outcome"]
        response = {
            "ticket": ticket_text,
            "domain": result["domain"],
            "ticket_analysis": _serialize_ticket_analysis(result["ticket_analysis"]),
            "outcome": result["outcome"],
            "decision": _serialize_decision(result["decision"]),
            "answer": result.get("answer"),
            "evidence_used": result.get("evidence_used", []),
        }
        if result["outcome"] == ESCALATE:
            response["escalation_reason"] = result.get("escalation_reason")
        return response


@app.post("/ticket/resolve")
def resolve_ticket_endpoint(body: TicketRequest):
    """Full pipeline via the LangGraph app. Not persisted - for ad-hoc
    resolution of arbitrary ticket text."""
    return _run_full_pipeline(body.ticket, "/ticket/resolve")


@app.post("/ticket/upload")
def upload_ticket_endpoint(body: UploadRequest):
    """Full pipeline, persisted under a new ticket_id. Text only today -
    image upload is Day 12 scope, not implemented here.

    Day 11 fix: the pipeline (retrieval + ticket_analysis) now runs on
    `description` ALONE, not title+description concatenated. Title is
    stored only for display. Previously, title wording silently changed
    retrieval confidence and classification input - confirmed live to be
    enough to flip a ticket between FALLBACK and ESCALATE for the same
    underlying issue, purely based on how the title was worded.
    """
    ticket_text = body.description.strip()
    ticket_id = str(uuid.uuid4())

    result = _run_full_pipeline(ticket_text, "/ticket/upload")
    result["ticket_id"] = ticket_id
    result["title"] = body.title
    result["description"] = body.description
    result["created_at"] = datetime.now(timezone.utc).isoformat()

    resources["ticket_store"].save(ticket_id, result)
    return result


@app.get("/ticket/{ticket_id}")
def get_ticket_endpoint(ticket_id: str):
    result = resources["ticket_store"].get(ticket_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No ticket found with id {ticket_id}")
    return result


@app.delete("/ticket/{ticket_id}")
def delete_ticket_endpoint(ticket_id: str):
    """Day 11 addition. Removes a ticket from history - useful for clearing
    out test/duplicate submissions made while verifying behavior."""
    deleted = resources["ticket_store"].delete(ticket_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No ticket found with id {ticket_id}")
    return {"deleted": True, "ticket_id": ticket_id}


@app.get("/tickets")
def list_tickets_endpoint(
    response: Response,
    limit: Optional[int] = None,
    offset: int = 0,
    outcome: Optional[str] = None,
    q: Optional[str] = None,
):
    """Lightweight summary list for the Dashboard cards and Tickets history
    table. Deliberately excludes full answer/evidence text - GET /ticket/{id}
    still serves that when a specific ticket is opened. Sorting/filtering
    now happens in SQL (ticket_store.list_summaries), not by scanning every
    ticket's full JSON payload on every request.

    Real pagination: omit `limit` (the Dashboard's usage) to get the full,
    unpaginated history for accurate outcome counts. Pass `limit`/`offset`
    (TicketsList's usage) to get one page; the total count for the current
    `outcome`/`q` filters is returned via the `X-Total-Count` response
    header so the client can compute page count without a second request.

    `q` is a case-insensitive title substring filter (see
    ticket_store.list_summaries's docstring for scope - title only, not
    full ticket text).
    """
    total = resources["ticket_store"].count(outcome=outcome, search=q)
    response.headers["X-Total-Count"] = str(total)
    return resources["ticket_store"].list_summaries(limit=limit, offset=offset, outcome=outcome, search=q)


@app.get("/knowledge-base")
def list_knowledge_base_endpoint():
    """Day 11 addition. Read-only view of the documents the retrieval
    pipeline draws evidence from. Deliberately isolated from the actual
    retrieval logic: this just reads resources["chunks"], the same list
    build_bm25_index() already loaded once at startup for retrieval - no
    new file reads, no changes to bm25_search.py/hybrid_search.py/
    rerank_search.py. Chunks are deduplicated down to one row per document
    (grouped by document_id), since a document usually spans several chunks
    and the KB view should show documents, not raw chunks.

    Every field returned here was confirmed to exist on every chunk record
    by inspect_kb_metadata_v3.py before this endpoint was written - nothing
    assumed (source_type exists but has a single constant value across the
    whole corpus: "Atlassian Official Documentation" - included for
    completeness, not useful as a filter).
    """
    docs = {}
    for chunk in resources.get("chunks", []):
        doc_id = chunk["document_id"]
        if doc_id not in docs:
            docs[doc_id] = {
                "document_id": doc_id,
                "document_title": chunk["document_title"],
                "source_url": chunk["source_url"],
                "category": chunk["category"],
                "source_type": chunk["source_type"],
                "chunk_count": chunk.get("chunk_count_in_doc"),
            }

    return sorted(docs.values(), key=lambda d: (d["category"], d["document_title"]))


@app.get("/logs")
def list_logs_endpoint(response: Response, limit: int = 50, offset: int = 0, status: Optional[str] = None):
    """Backs the System Logs page. Every /ticket/analyze, /ticket/resolve,
    and /ticket/upload call is recorded via event_log.timed_event - this
    returns one page of rows, newest first, same real-pagination pattern as
    GET /tickets: the total count for the current `status` filter comes back
    via the X-Total-Count response header so the client can compute page
    count without a second request."""
    total = resources["event_log"].count(status=status)
    response.headers["X-Total-Count"] = str(total)
    return resources["event_log"].list_recent(limit=limit, offset=offset, status=status)


@app.get("/evaluation")
def evaluation_endpoint():
    """Backs the Evaluation page. Returns two clearly separate sections:
    `calibration` (real accuracy against hand-labeled Day 5/9 test sets -
    see evaluation.py's docstring for why this isn't re-run live) and
    `live` (unlabeled operational distribution/latency/error-rate stats
    from actual ticket history and recent events)."""
    return {
        "calibration": calibration_summary(),
        "live": live_summary(
            resources["ticket_store"].list_summaries(),
            resources["event_log"].list_recent(limit=500),
        ),
    }
