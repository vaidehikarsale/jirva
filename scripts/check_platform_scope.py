"""
JIRVA - Platform Scope Checker
---------------------------------
Scans every document in data/documents/<category>/*.json for two signals
that the content does NOT apply to Jira Cloud (JIRVA's target platform):
  1. In-content platform-notice phrases, e.g. "Data Center Only" banners.
  2. Server/Data Center documentation-space URL patterns (e.g. URLs
     containing "server", such as ADMINJIRASERVER or servicemanagementserver),
     which catch legacy Confluence-hosted Server docs even when they don't
     carry an explicit banner.

This does not delete anything automatically - it only reports flagged
documents so you can review and decide whether to remove or replace them.

Usage:
    python check_platform_scope.py --input ../data/documents
"""

import argparse
import json
import os

FLAG_PHRASES = [
    "data center only",
    "server only",
    "this article only applies to atlassian apps on the data center platform",
    "this article only applies to atlassian apps on the server platform",
]

# URL substrings that indicate a Server/Data Center documentation space rather
# than Cloud. Checked case-insensitively. "server" alone is safe here - it does
# NOT appear inside "service" (s-e-r-v-i-c-e vs s-e-r-v-e-r), so it won't
# false-positive on legitimate Cloud URLs like "jira-service-management-cloud".
FLAG_URL_PATTERNS = [
    "server",       # catches ADMINJIRASERVER, JIRASOFTWARESERVER, servicemanagementserver, etc.
    "/datacenter/",
    "data-center",
]


def check_documents(input_dir):
    flagged = []
    checked = 0

    for category in sorted(os.listdir(input_dir)):
        category_path = os.path.join(input_dir, category)
        if not os.path.isdir(category_path):
            continue
        for fname in sorted(os.listdir(category_path)):
            if not fname.endswith(".json"):
                continue
            checked += 1
            with open(os.path.join(category_path, fname), "r", encoding="utf-8") as f:
                try:
                    doc = json.load(f)
                except json.JSONDecodeError:
                    continue

            content_lower = doc.get("content", "").lower()
            url_lower = doc.get("source_url", "").lower()

            matched = None
            for phrase in FLAG_PHRASES:
                if phrase in content_lower:
                    matched = f'content phrase: "{phrase}"'
                    break
            if not matched:
                for pattern in FLAG_URL_PATTERNS:
                    if pattern in url_lower:
                        matched = f'URL pattern: "{pattern}"'
                        break

            if matched:
                flagged.append({
                    "id": doc.get("id"),
                    "title": doc.get("title"),
                    "category": category,
                    "matched_phrase": matched,
                    "source_url": doc.get("source_url"),
                })

    print(f"Checked {checked} documents.\n")
    if not flagged:
        print("No Data Center / Server-only notices or URL patterns found. All documents appear Cloud-relevant.")
    else:
        print(f"Flagged {len(flagged)} document(s) for manual review:\n")
        for item in flagged:
            print(f"  [{item['category']}] {item['id']} - {item['title']}")
            print(f"    Matched: \"{item['matched_phrase']}\"")
            print(f"    URL: {item['source_url']}\n")


def main():
    parser = argparse.ArgumentParser(description="Check JIRVA documents for Data Center/Server-only scope notices")
    parser.add_argument("--input", required=True, help="Path to data/documents")
    args = parser.parse_args()
    check_documents(args.input)


if __name__ == "__main__":
    main()
