"""
JIRVA - Document Chunking Script
-----------------------------------
Reads collected documents from data/documents/<category>/*.json and splits
each into overlapping, structure-aware chunks (paragraph -> line -> sentence
-> forced token split), using the actual embedding-model tokenizer to measure
"tokens" accurately rather than an approximate character count.

Writes one JSON file per chunk into:
    data/chunks/<variant_name>/<category>/<doc_id>_c<NN>.json

Safe to rerun: if chunks already exist for a document in a given variant,
that document is skipped (logged as 'skipped'), so re-running never
duplicates or overwrites existing chunk files.

Usage:
    python chunk_docs.py --input <documents_dir> --output <chunks_dir> --log <log_csv> --target-tokens <int> --overlap-ratio <float>

Example (300-400 token variant):
    python chunk_docs.py --input ../data/documents --output ../data/chunks/400_variant --log ../logs/chunking_log.csv --target-tokens 400 --overlap-ratio 0.12

Example (500-600 token variant):
    python chunk_docs.py --input ../data/documents --output ../data/chunks/600_variant --log ../logs/chunking_log.csv --target-tokens 600 --overlap-ratio 0.12
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone

from transformers import AutoTokenizer
from langchain_text_splitters import RecursiveCharacterTextSplitter

TOKENIZER_MODEL = "BAAI/bge-small-en-v1.5"


def log_row(log_path, document_id, category, variant, status, chunk_count, reason):
    file_exists = os.path.isfile(log_path)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "document_id", "category", "variant", "status", "chunk_count", "reason"])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            document_id, category, variant, status, chunk_count, reason
        ])


def already_chunked(output_dir, category, doc_id):
    """Check if chunks already exist for this document in this variant's output dir."""
    category_dir = os.path.join(output_dir, category)
    if not os.path.isdir(category_dir):
        return False
    prefix = f"{doc_id}_c"
    return any(fname.startswith(prefix) for fname in os.listdir(category_dir))


def load_documents(input_dir):
    """Walk data/documents/<category>/*.json and yield (category, doc_dict)."""
    for category in sorted(os.listdir(input_dir)):
        category_path = os.path.join(input_dir, category)
        if not os.path.isdir(category_path):
            continue
        for fname in sorted(os.listdir(category_path)):
            if fname.endswith(".json") and fname != "MANIFEST.md":
                with open(os.path.join(category_path, fname), "r", encoding="utf-8") as f:
                    try:
                        doc = json.load(f)
                        yield category, doc
                    except json.JSONDecodeError:
                        continue


def chunk_document(doc, splitter):
    """Split one document's content into chunks and return the chunk text list."""
    content = doc.get("content", "")
    if not content or not content.strip():
        return []
    return splitter.split_text(content)


def build_chunk_records(doc, category, chunk_texts):
    records = []
    total = len(chunk_texts)
    for i, text in enumerate(chunk_texts, start=1):
        chunk_id = f"{doc['id']}_c{i:02d}"
        records.append({
            "chunk_id": chunk_id,
            "document_id": doc["id"],
            "document_title": doc["title"],
            "source_url": doc["source_url"],
            "category": category,
            "source_type": doc.get("source_type", "Atlassian Official Documentation"),
            "chunk_index": i,
            "chunk_count_in_doc": total,
            "content": text.strip(),
        })
    return records


def run(input_dir, output_dir, log_path, target_tokens, overlap_ratio):
    print(f"Loading tokenizer: {TOKENIZER_MODEL} (used only to count tokens, not to run the model)")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_MODEL)

    def token_length(text):
        return len(tokenizer.encode(text, add_special_tokens=False))

    overlap_tokens = int(target_tokens * overlap_ratio)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=target_tokens,
        chunk_overlap=overlap_tokens,
        length_function=token_length,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    variant_name = os.path.basename(os.path.normpath(output_dir))
    print(f"Variant: {variant_name} | target_tokens={target_tokens} | overlap_tokens={overlap_tokens}")

    total_docs, total_chunks, skipped, failed = 0, 0, 0, 0

    for category, doc in load_documents(input_dir):
        total_docs += 1
        doc_id = doc.get("id", "UNKNOWN")

        if already_chunked(output_dir, category, doc_id):
            print(f"  [SKIP] {doc_id} already chunked for variant {variant_name}")
            log_row(log_path, doc_id, category, variant_name, "skipped", 0, "chunks already exist")
            skipped += 1
            continue

        try:
            chunk_texts = chunk_document(doc, splitter)
            if not chunk_texts:
                print(f"  [FAILED] {doc_id} has empty content")
                log_row(log_path, doc_id, category, variant_name, "failed", 0, "empty content")
                failed += 1
                continue

            records = build_chunk_records(doc, category, chunk_texts)
            category_out_dir = os.path.join(output_dir, category)
            os.makedirs(category_out_dir, exist_ok=True)

            for record in records:
                out_path = os.path.join(category_out_dir, f"{record['chunk_id']}.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(record, f, indent=2, ensure_ascii=False)

            print(f"  [SUCCESS] {doc_id} -> {len(records)} chunks")
            log_row(log_path, doc_id, category, variant_name, "success", len(records), "saved")
            total_chunks += len(records)

        except Exception as e:
            print(f"  [FAILED] {doc_id}: {e}")
            log_row(log_path, doc_id, category, variant_name, "failed", 0, str(e))
            failed += 1

    print("\n--- Chunking summary ---")
    print(f"Variant:        {variant_name}")
    print(f"Documents seen: {total_docs}")
    print(f"Chunks created: {total_chunks}")
    print(f"Skipped:        {skipped}")
    print(f"Failed:         {failed}")
    print(f"Log written to: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="JIRVA document chunking script")
    parser.add_argument("--input", required=True, help="Path to data/documents")
    parser.add_argument("--output", required=True, help="Path to this variant's chunk output dir, e.g. data/chunks/400_variant")
    parser.add_argument("--log", required=True, help="Path to the chunking log CSV")
    parser.add_argument("--target-tokens", type=int, required=True, help="Target max tokens per chunk (e.g. 400 or 600)")
    parser.add_argument("--overlap-ratio", type=float, default=0.12, help="Overlap as a fraction of target-tokens (default 0.12)")
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(f"ERROR: input directory not found: {args.input}")
        sys.exit(1)

    run(args.input, args.output, args.log, args.target_tokens, args.overlap_ratio)


if __name__ == "__main__":
    main()
