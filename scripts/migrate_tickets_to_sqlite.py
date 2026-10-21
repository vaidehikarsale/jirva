"""
One-time migration: data/tickets_store.json -> data/jirva.db (SQLite).

Safe to re-run - uses INSERT OR REPLACE per ticket, so re-running after
new JSON tickets appear (e.g. if you're mid-migration and api.py is still
briefly writing JSON) just re-syncs those rows rather than duplicating.

Usage:
    cd scripts
    python migrate_tickets_to_sqlite.py [--json-file ../data/tickets_store.json] [--db-file ../data/jirva.db]
"""

import argparse
import json
import os

from ticket_store import TicketStore


def main():
    parser = argparse.ArgumentParser(description="Migrate JIRVA ticket history from JSON to SQLite")
    parser.add_argument("--json-file", default="../data/tickets_store.json")
    parser.add_argument("--db-file", default="../data/jirva.db")
    args = parser.parse_args()

    if not os.path.exists(args.json_file):
        print(f"No JSON store found at {args.json_file} - nothing to migrate.")
        return

    with open(args.json_file, "r", encoding="utf-8") as f:
        tickets = json.load(f)

    store = TicketStore(args.db_file)
    for ticket_id, result in tickets.items():
        store.save(ticket_id, result)

    print(f"Migrated {len(tickets)} ticket(s) from {args.json_file} to {args.db_file}.")
    print(f"Database now contains {store.count()} ticket(s) total.")
    print(f"\nOriginal JSON file left untouched at {args.json_file} - "
          f"delete it manually once you've confirmed the API works against the new DB.")


if __name__ == "__main__":
    main()
