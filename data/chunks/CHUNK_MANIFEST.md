# JIRVA Knowledge Base - Chunking Manifest (Day 3)

**Chunking date:** 2026-09-05
**Total source documents:** 57 (2 removed during Day 3 quality review - see notes below)
**Chunking strategy:** Recursive structure-aware splitting (paragraph -> line -> sentence -> forced), with ~12% token overlap between consecutive chunks. Token counts measured using the BAAI/bge-small-en-v1.5 tokenizer.
**Variants produced:** 400_variant (target ~300-400 tokens), 600_variant (target ~500-600 tokens)

**Total chunks - 400_variant:** 219
**Total chunks - 600_variant:** 153

| Category | Documents | Chunks (400_variant) | Chunks/doc (400) | Chunks (600_variant) | Chunks/doc (600) |
|---|---|---|---|---|---|
| 01_Workflows | 7 | 29 | 4.1 | 19 | 2.7 |
| 02_Permissions | 7 | 11 | 1.6 | 9 | 1.3 |
| 03_Issues | 4 | 15 | 3.8 | 10 | 2.5 |
| 04_Projects | 4 | 10 | 2.5 | 7 | 1.8 |
| 05_Fields | 6 | 16 | 2.7 | 11 | 1.8 |
| 06_Search | 8 | 81 | 10.1 | 54 | 6.8 |
| 07_Boards | 6 | 17 | 2.8 | 13 | 2.2 |
| 08_Notifications | 5 | 17 | 3.4 | 11 | 2.2 |
| 09_Jira_Service_Management | 8 | 12 | 1.5 | 11 | 1.4 |
| 10_Troubleshooting | 2 | 11 | 5.5 | 8 | 4.0 |

## Quality review notes (Day 3)

Two documents were removed from the knowledge base after manual chunk inspection revealed quality issues:

- **ts_001 - "Jira Service Management Cloud Knowledge Base"** (originally in 10_Troubleshooting): this source was a link-index/hub page. Its chunks contained only article titles pointing to other pages, with no actual troubleshooting instructions or explanations. Removed as low-value/noise content unsuitable for RAG.
- **ts_004 - "Automation for Jira Troubleshooting guide"** (originally in 10_Troubleshooting): this source explicitly stated "This article only applies to Atlassian apps on the Data Center platform," making it out of scope for JIRVA, which targets Jira Cloud. Removed to prevent JIRVA from citing Data-Center-specific steps to Cloud users.

A systematic scan (`scripts/check_platform_scope.py`) was run across all remaining 57 documents to check for similar Data Center/Server-only notices. Result: 0 additional flags.

## Known limitation flagged for later

`10_Troubleshooting` now has only 2 source documents, the thinnest category in the knowledge base. This is a deliberate quality-over-quantity trade-off, not an oversight. If Day 11 evaluation shows weak retrieval performance for troubleshooting-type tickets, this category should be revisited for expansion with genuinely substantive (not hub/index) Cloud-relevant articles.

## Chunk size comparison (qualitative, pending Day 11 quantitative evaluation)

Initial manual comparison on a 3-document pilot suggested the 600-token variant preserves more complete procedural continuity (e.g., full numbered steps in a single chunk) compared to the 400-token variant. This is noted as a hypothesis to be tested quantitatively once retrieval evaluation is possible (Day 11), not a conclusion.