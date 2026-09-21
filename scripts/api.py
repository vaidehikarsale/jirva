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

Storage: JSON file (JIRVA_TICKETS_FILE, default ../data/tickets_store.json).
NOT a real database - no concurrent-write locking, fine for a single-user
prototype. Previously in-memory only, which meant every uvicorn --reload
restart silently wiped ticket history - not usable as a real history
feature, so this was upgraded to file-backed storage on Day 11.

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

import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer, CrossEncoder

from bm25_search import build_bm25_index
from domain_guard import build_reference_embeddings, check_domain
from decision_engine import decide, ESCALATE
from langgraph_flow import build_graph
from jirva import OUT_OF_DOMAIN_MESSAGE

EMBED_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANK_MODEL_NAME = "BAAI/bge-reranker-base"

# Matches the --chunks-dir / --collection values used throughout every CLI
# script so far. Overridable via env vars without touching code.
CHUNKS_DIR = os.getenv("JIRVA_CHUNKS_DIR", "../data/chunks/400_variant")
COLLECTION = os.getenv("JIRVA_COLLECTION", "jirva_400")

# Day 11 update: JSON-file-backed persistence, not just an in-memory dict.
# Previously, every uvicorn --reload restart (which happens on every code
# save) silently wiped all uploaded tickets - not usable as a real "ticket
# history" feature. Still not a database, still zero new dependencies
# (json is stdlib) - just survives restarts now.
TICKETS_FILE = os.getenv("JIRVA_TICKETS_FILE", "../data/tickets_store.json")

TICKETS = {}


def _load_tickets_from_disk():
    if not os.path.exists(TICKETS_FILE):
        return {}
    try:
        with open(TICKETS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: could not load {TICKETS_FILE} ({e}) - starting with empty ticket history.")
        return {}


def _save_tickets_to_disk():
    os.makedirs(os.path.dirname(TICKETS_FILE) or ".", exist_ok=True)
    with open(TICKETS_FILE, "w", encoding="utf-8") as f:
        json.dump(TICKETS, f, indent=2)


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

    loaded = _load_tickets_from_disk()
    TICKETS.update(loaded)
    print(f"Loaded {len(loaded)} previously stored ticket(s) from {TICKETS_FILE}")

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
    guard_result = check_domain(
        body.ticket, resources["qdrant_client"], resources["embed_model"],
        resources["cross_encoder"], resources["bm25"], resources["chunks"],
        resources["ref_texts"], resources["ref_embeddings"], COLLECTION,
    )

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

    return {
        "ticket": body.ticket,
        "domain": "Jira",
        "ticket_analysis": _serialize_ticket_analysis(ta),
        "evidence_confidence": evidence_confidence,
        "decision": _serialize_decision(decision),
    }


def _run_full_pipeline(ticket_text: str) -> dict:
    """Shared by /ticket/resolve and /ticket/upload - runs the LangGraph app
    and returns a clean, JSON-safe response dict. Single source of truth for
    this shape so the two endpoints can't silently drift apart."""
    result = resources["graph"].invoke({"ticket": ticket_text})

    if result["domain"] == "Out-of-Domain":
        return {
            "ticket": ticket_text,
            "domain": "Out-of-Domain",
            "answer": result["answer"],
        }

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
    return _run_full_pipeline(body.ticket)


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

    result = _run_full_pipeline(ticket_text)
    result["ticket_id"] = ticket_id
    result["title"] = body.title
    result["description"] = body.description
    result["created_at"] = datetime.now(timezone.utc).isoformat()

    TICKETS[ticket_id] = result
    _save_tickets_to_disk()
    return result


@app.get("/ticket/{ticket_id}")
def get_ticket_endpoint(ticket_id: str):
    if ticket_id not in TICKETS:
        raise HTTPException(status_code=404, detail=f"No ticket found with id {ticket_id}")
    return TICKETS[ticket_id]


@app.delete("/ticket/{ticket_id}")
def delete_ticket_endpoint(ticket_id: str):
    """Day 11 addition. Removes a ticket from history - useful for clearing
    out test/duplicate submissions made while verifying behavior. Persists
    the deletion to disk immediately, same as upload does on write."""
    if ticket_id not in TICKETS:
        raise HTTPException(status_code=404, detail=f"No ticket found with id {ticket_id}")
    del TICKETS[ticket_id]
    _save_tickets_to_disk()
    return {"deleted": True, "ticket_id": ticket_id}


@app.get("/tickets")
def list_tickets_endpoint():
    """Lightweight summary list for the Dashboard cards and Tickets history
    table. Deliberately excludes full answer/evidence text - GET /ticket/{id}
    still serves that when a specific ticket is opened.

    outcome is "OUT_OF_DOMAIN" (a display-only sentinel, not a real
    decision_engine.py outcome) for tickets where domain was Out-of-Domain,
    since those never reach ticket_analysis/decision at all and so have no
    real outcome field to report.
    """
    summaries = []
    for ticket_id, t in TICKETS.items():
        if t.get("domain") == "Out-of-Domain":
            outcome = "OUT_OF_DOMAIN"
            category = "Out-of-Domain"
            risk = None
        else:
            outcome = t.get("outcome")
            category = t.get("ticket_analysis", {}).get("category")
            risk = t.get("ticket_analysis", {}).get("risk")

        summaries.append({
            "ticket_id": ticket_id,
            "title": t.get("title", ""),
            "category": category,
            "outcome": outcome,
            "risk": risk,
            "created_at": t.get("created_at"),
        })

    summaries.sort(key=lambda s: s["created_at"] or "", reverse=True)
    return summaries


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
