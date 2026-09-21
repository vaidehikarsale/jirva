"""
JIRVA - Verify documents_test/ and sources_test.csv are unreferenced
----------------------------------------------------------------
Read-only. Searches every .py file in scripts/ for any mention of
"documents_test" or "sources_test", so we know for certain whether these
are live inputs to any current script/pipeline before deleting anything.

Usage:
    python check_test_scaffolding_refs.py --scripts-dir .
"""

import argparse
import os


SEARCH_TERMS = ["documents_test", "sources_test"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scripts-dir", default=".")
    args = parser.parse_args()

    py_files = sorted(f for f in os.listdir(args.scripts_dir) if f.endswith(".py"))
    print(f"Scanning {len(py_files)} .py files in {args.scripts_dir} for: {SEARCH_TERMS}\n")

    any_found = False
    for fname in py_files:
        path = os.path.join(args.scripts_dir, fname)
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        for i, line in enumerate(lines, start=1):
            for term in SEARCH_TERMS:
                if term in line:
                    any_found = True
                    print(f"[FOUND] {fname}:{i}: {line.strip()}")

    print()
    if any_found:
        print("References found above - do NOT delete until these are reviewed.")
    else:
        print(f"No references to {SEARCH_TERMS} found in any .py file in {args.scripts_dir}.")


if __name__ == "__main__":
    main()
