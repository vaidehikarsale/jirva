"""
JIRVA - Knowledge Base Collection Script
------------------------------------------
Reads a CSV of approved source URLs, fetches each page, extracts the
main documentation content (stripping nav/sidebars/cookie notices/menus),
and writes one JSON file per document using JIRVA's locked schema:
    id, title, source_url, category, source_type, content

Safe to rerun: it skips any URL that has already been saved for its
category (checked by matching source_url inside existing JSON files),
so re-running never creates duplicates.

Usage:
    python collect_docs.py --input <sources.csv> --output <output_dir> --log <log_csv>

Example (test batch):
    python collect_docs.py --input ../data/sources/sources_test.csv --output ../data/documents_test --log ../logs/collection_log.csv
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone

import requests
import trafilatura
from bs4 import BeautifulSoup

SOURCE_TYPE = "Atlassian Official Documentation"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JIRVA-KB-Collector/1.0"
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 1.5  # be polite to Atlassian's servers


def log_row(log_path, category, url, status, reason, output_file):
    """Append a single row to the collection log (creates file + header if missing)."""
    file_exists = os.path.isfile(log_path)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "category", "url", "status", "reason", "output_file"])
        writer.writerow([
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            category, url, status, reason, output_file or ""
        ])


def load_existing_urls(output_dir, category):
    """Return the set of source_urls already saved for this category, so we never duplicate."""
    existing = set()
    category_dir = os.path.join(output_dir, category)
    if not os.path.isdir(category_dir):
        return existing
    for fname in os.listdir(category_dir):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(category_dir, fname), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "source_url" in data:
                        existing.add(data["source_url"].rstrip("/"))
            except (json.JSONDecodeError, OSError):
                continue  # ignore unreadable/corrupt files rather than crashing the run
    return existing


def next_id_number(output_dir, category, prefix):
    """Find the next available NNN for <prefix>_NNN based on existing files in the category folder."""
    category_dir = os.path.join(output_dir, category)
    max_num = 0
    if os.path.isdir(category_dir):
        for fname in os.listdir(category_dir):
            if fname.startswith(prefix + "_") and fname.endswith(".json"):
                num_part = fname[len(prefix) + 1: -5]
                if num_part.isdigit():
                    max_num = max(max_num, int(num_part))
    return max_num + 1


def fetch_html(url):
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.text


def extract_main_content(html, url):
    """
    Try trafilatura first (purpose-built for stripping nav/boilerplate).
    Fall back to a BeautifulSoup heuristic if trafilatura returns nothing useful.
    """
    text = trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    if text and len(text.strip()) > 200:
        return text.strip()

    # Fallback: BeautifulSoup heuristic - look for <main> or <article>, else <body>,
    # then strip nav/header/footer/script/style tags.
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["nav", "header", "footer", "script", "style", "noscript", "form"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.find("body")
    if not main:
        return None
    text = main.get_text(separator="\n", strip=True)
    return text.strip() if text and len(text.strip()) > 200 else None


def collect(input_csv, output_dir, log_path):
    with open(input_csv, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"Loaded {len(rows)} source rows from {input_csv}")

    # Pre-load existing URLs per category so duplicates are skipped even across reruns
    existing_by_category = {}

    success, failed, duplicate, skipped = 0, 0, 0, 0

    for row in rows:
        category = row["category"].strip()
        prefix = row["prefix"].strip()
        title = row["title"].strip()
        url = row["url"].strip()

        if not url or not category or not prefix:
            print(f"  [SKIP] Incomplete row, missing category/prefix/url: {row}")
            log_row(log_path, category, url, "skipped", "incomplete row", None)
            skipped += 1
            continue

        if category not in existing_by_category:
            existing_by_category[category] = load_existing_urls(output_dir, category)

        if url.rstrip("/") in existing_by_category[category]:
            print(f"  [DUPLICATE] Already collected, skipping: {url}")
            log_row(log_path, category, url, "duplicate", "already exists in output_dir", None)
            duplicate += 1
            continue

        print(f"  Fetching: {url}")
        try:
            html = fetch_html(url)
        except requests.RequestException as e:
            print(f"  [FAILED] Could not fetch {url}: {e}")
            log_row(log_path, category, url, "failed", f"fetch error: {e}", None)
            failed += 1
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        content = extract_main_content(html, url)
        if not content:
            print(f"  [FAILED] Could not extract usable content from {url}")
            log_row(log_path, category, url, "failed", "extraction returned empty/too short", None)
            failed += 1
            time.sleep(REQUEST_DELAY_SECONDS)
            continue

        # Build output record using the locked schema
        doc_id = f"{prefix}_{next_id_number(output_dir, category, prefix):03d}"
        record = {
            "id": doc_id,
            "title": title,
            "source_url": url,
            "category": category,
            "source_type": SOURCE_TYPE,
            "content": content,
        }

        category_dir = os.path.join(output_dir, category)
        os.makedirs(category_dir, exist_ok=True)
        output_file = os.path.join(category_dir, f"{doc_id}.json")

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)

        print(f"  [SUCCESS] Saved {output_file}")
        log_row(log_path, category, url, "success", "saved", output_file)
        existing_by_category[category].add(url.rstrip("/"))
        success += 1

        time.sleep(REQUEST_DELAY_SECONDS)  # be polite between requests

    print("\n--- Collection summary ---")
    print(f"Success:   {success}")
    print(f"Failed:    {failed}")
    print(f"Duplicate: {duplicate}")
    print(f"Skipped:   {skipped}")
    print(f"Total:     {len(rows)}")
    print(f"Log written to: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="JIRVA knowledge base collection script")
    parser.add_argument("--input", required=True, help="Path to sources CSV (category,prefix,title,url)")
    parser.add_argument("--output", required=True, help="Output directory for collected JSON documents")
    parser.add_argument("--log", required=True, help="Path to the collection log CSV")
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"ERROR: input file not found: {args.input}")
        sys.exit(1)

    collect(args.input, args.output, args.log)


if __name__ == "__main__":
    main()
