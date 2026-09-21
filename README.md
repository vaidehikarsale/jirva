# JIRVA — AI-Powered Jira Support Assistant

JIRVA is a RAG-based AI support assistant for Jira-related issues. It retrieves relevant Atlassian documentation, evaluates the risk and confidence of a ticket, and decides whether the issue should be resolved, guided, escalated to a human, or handled as an unsupported request.

> **AI should solve what it can, but know when it should stop.**

JIRVA was developed as a final-year Artificial Intelligence & Data Science engineering project, with a focus on grounded retrieval, risk-aware decision making, and controlled LLM generation.

---

## What JIRVA Does

A user submits a Jira support ticket through the React interface.

JIRVA then:

1. Checks whether the ticket belongs to the supported Jira domain.
2. Retrieves relevant documentation using hybrid search.
3. Reranks the retrieved evidence using a cross-encoder.
4. Evaluates evidence confidence, risk, and category alignment.
5. Selects an appropriate outcome:
   - **RESOLVE** — generate a grounded answer.
   - **GUIDE** — provide limited diagnostic guidance.
   - **ESCALATE** — stop generation and prepare a human handoff.
   - **FALLBACK** — handle unsupported or insufficiently grounded requests.
6. Returns the response with supporting knowledge-base sources.

For high-risk cases such as unauthorized access or credential exposure, a deterministic safety backstop can force escalation even when the LLM classification is uncertain.

---

## Architecture

```text
                         ┌─────────────────┐
                         │ React Frontend  │
                         └────────┬────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │   FastAPI API   │
                         └────────┬────────┘
                                  │
                                  ▼
                    ┌──────────────────────────┐
                    │       LangGraph          │
                    │      Orchestration       │
                    └────────────┬─────────────┘
                                 │
                ┌────────────────┴────────────────┐
                ▼                                 ▼
       ┌─────────────────┐              ┌─────────────────┐
       │   Domain Guard  │              │  Risk Detection │
       └────────┬────────┘              └────────┬────────┘
                │                                │
                └──────────────┬─────────────────┘
                               ▼
                    ┌─────────────────────┐
                    │  Hybrid Retrieval   │
                    │ Vector + BM25 + RRF │
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │      Reranker       │
                    │  BGE Cross-Encoder  │
                    └──────────┬──────────┘
                               ▼
                    ┌─────────────────────┐
                    │   Decision Engine   │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
          RESOLVE            GUIDE           ESCALATE
              │                │                │
              ▼                ▼                ▼
        LLM Generation   Diagnostic LLM    Human Handoff
              │
              ▼
       Answer + Sources
```

---

## Retrieval Pipeline

JIRVA uses hybrid retrieval instead of relying on a single search method.

### Vector Search

Ticket text is embedded using:

```text
BAAI/bge-small-en-v1.5
```

The resulting embeddings are stored in Qdrant Cloud.

### BM25 Retrieval

A lexical BM25 search runs alongside semantic retrieval to capture exact Jira terminology, field names, error messages, and other keyword-heavy queries.

### Reciprocal Rank Fusion

The vector and BM25 results are merged using Reciprocal Rank Fusion (RRF).

### Reranking

The merged candidates are reranked using:

```text
BAAI/bge-reranker-base
```

The resulting ranking is used by the downstream decision engine.

---

## Decision Engine

The decision engine is separated from the LLM generation step.

It considers three main signals:

- **Evidence confidence** — confidence from the top reranked result.
- **Risk** — classification of the ticket.
- **Category alignment** — whether the retrieved evidence matches the ticket category.

The current calibrated thresholds are:

```text
fallback_threshold = 0.05
resolve_threshold  = 0.65
```

This prevents every retrieved result from automatically being treated as sufficient evidence for an answer.

---

## Domain & Risk Guard

Before normal answer generation, JIRVA checks whether the request belongs to the supported Jira domain.

The domain guard uses:

- Retrieval confidence
- Similarity to reference tickets
- Constrained LLM classification

The system can short-circuit the request when the lightweight signals independently agree that it is out-of-domain.

Risk detection also includes a deterministic keyword-based backstop for clearly sensitive cases, including:

- Unauthorized access
- Credential exposure
- Urgent access revocation
- Former-employee access retention

These cases are escalated rather than answered automatically.

---

## Knowledge Base

The current knowledge base contains:

- **57 unique source documents**
- Official Atlassian documentation
- **10 Jira-related categories**
- **223 chunks** in the primary 400-token chunking variant

The categories are:

1. Workflows
2. Permissions
3. Issues
4. Projects
5. Fields
6. Search
7. Boards
8. Notifications
9. Jira Service Management
10. Troubleshooting

The knowledge base is also exposed through the frontend for browsing, searching, and filtering.

---

## Models & Infrastructure

| Component | Technology |
|---|---|
| LLM | NVIDIA Nemotron 3 Nano Omni 30B A3B Reasoning — OpenRouter free tier |
| Embeddings | `BAAI/bge-small-en-v1.5` |
| Reranker | `BAAI/bge-reranker-base` |
| Vector Database | Qdrant Cloud |
| Retrieval | Vector Search + BM25 |
| Fusion | Reciprocal Rank Fusion |
| Orchestration | LangGraph |
| Backend | FastAPI |
| Frontend | React + Vite |
| Language | Python, JavaScript |
| Persistence | JSON-based ticket store |

The embedding and reranking models run locally. The LLM is accessed through OpenRouter.

---

## Frontend

The current application includes:

- **Dashboard** — ticket statistics, outcome distribution, and recent tickets
- **Raise Ticket** — submit a Jira support issue
- **Ticket Analysis** — view classification, evidence, and decision
- **Resolution / Escalation** — view the generated response or human handoff summary
- **Tickets** — searchable ticket history with outcome filtering and deletion
- **Knowledge Base** — searchable and filterable source documents

The UI is intentionally lightweight and professional rather than using a typical dark/neon AI interface.

---

## API

The FastAPI backend currently exposes:

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Health check |
| `POST` | `/ticket/analyze` | Analyze a ticket |
| `POST` | `/ticket/resolve` | Run the resolution flow |
| `POST` | `/ticket/upload` | Upload ticket data |
| `GET` | `/ticket/{id}` | Retrieve a ticket |
| `DELETE` | `/ticket/{id}` | Delete a ticket |
| `GET` | `/tickets` | List ticket history |
| `GET` | `/knowledge-base` | Retrieve knowledge-base documents |

---

## Project Structure

```text
JIRVA/
│
├── backend/
│   ├── api/
│   ├── decision/
│   ├── retrieval/
│   ├── generation/
│   └── ...
│
├── frontend/
│   └── src/
│
├── data/
│   ├── documents/
│   ├── chunks/
│   └── ...
│
├── logs/
├── scripts/
├── .env
├── .gitignore
└── README.md
```

---

## Running Locally

### Backend

From the `backend` directory:

```bash
python -m uvicorn api:app --reload --port 8000
```

The FastAPI backend will run locally on port `8000`.

### Frontend

From the `frontend` directory:

```bash
npm install
npm run dev
```

The frontend communicates with the locally running FastAPI backend.

> API keys and other credentials are stored in `.env` and are not committed to the repository.

---

## Current Status

### Implemented

- RAG-based Jira support pipeline
- Hybrid vector + BM25 retrieval
- Reciprocal Rank Fusion
- Cross-encoder reranking
- Domain/out-of-domain detection
- Risk classification
- Deterministic high-risk safety backstop
- Calibrated decision engine
- RESOLVE / GUIDE / ESCALATE / FALLBACK paths
- Grounded LLM generation
- LangGraph orchestration
- FastAPI backend
- Ticket persistence and history
- React frontend
- Searchable knowledge base

### Not Yet Implemented

- Image/screenshot-based ticket input
- Production deployment
- Evaluation dashboard
- System Logs interface

---

## Known Limitations

The current prototype has two documented areas for further improvement:

1. **LLM classification instability** can still occur in cases outside the deterministic safety backstop.
2. The **GUIDE path** requires further refinement around scope narrowing to ensure diagnostic responses remain sufficiently constrained.

These are treated as engineering limitations of the current prototype.

---

## Future Work

- Add screenshot/image understanding for support tickets
- Build an evaluation pipeline for retrieval and answer quality
- Add metrics such as faithfulness, retrieval precision, resolution accuracy, and escalation precision/recall
- Add a system-log viewer
- Deploy the application
- Further calibrate domain, risk, and decision thresholds

---

## Tech Stack

```text
Python 3.14.7
React + Vite
FastAPI
LangGraph
Qdrant Cloud
Sentence Transformers
Cross-Encoder
BM25
OpenRouter
Nemotron
```

---

## Project

JIRVA was developed as a final-year Artificial Intelligence & Data Science engineering project.

The project focuses on a practical RAG problem: retrieving trustworthy evidence, deciding when that evidence is sufficient, and knowing when an AI system should hand the problem to a human instead of generating an uncertain answer.

## Author

**Vaidehi Karsale**  
Final-year Artificial Intelligence & Data Science Engineering Student

JIRVA is an independent project and is not affiliated with or endorsed by Atlassian.