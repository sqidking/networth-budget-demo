"""Command line: ``stmtrecon --db FILE <command>``."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import store
from .csv_import import parse_csv
from .models import ACCOUNT_TYPES
from .scan import import_found, scan


def _accounts(conn, args):
    if args.name:
        acct = store.add_bank_account(conn, args.name, args.type, args.last4)
        print(f"Added account {acct}: {args.name} ({args.type}, ending {args.last4})")
    for r in store.bank_accounts(conn):
        print(f"{r['id']:>3}  {r['name']:<20} {r['type']:<12} {r['last4'] or ''}")


def _rule(conn, args):
    store.add_rule(conn, args.match, args.category, source=args.source, priority=args.priority)
    print(f"Rule added: {args.source} '{args.match}' -> {args.category}")


def _scan(conn, args):
    found = scan(conn, Path(args.folder))
    if not found:
        print("No PDF statements found.")
    for f in found:
        print(f"{f.status:<40} {f.new_rows:>3} new  {f.path.name}")
        for p in (f.statement.problems if f.statement else []):
            print(f"    - {p}")
    if args.import_ready:
        for f in found:
            if f.ready:
                r = import_found(conn, f)
                print(f"Imported {f.path.name}: {r.added} added, {r.skipped} already stored")


def _csv(conn, args):
    r = store.import_transactions(conn, args.account, parse_csv(Path(args.file)), Path(args.file).name)
    print(f"Imported {args.file}: {r.added} added, {r.skipped} already stored")


def _list(conn, args):
    rows = store.transactions(conn)[::-1]                    # oldest first
    for r in rows:
        print(f"{r['date']}  {r['account']:<12} {r['description'][:40]:<40} {r['amount']:>10,.2f}  "
              f"{r['category'] or '(uncategorized)'}")
    print(f"{len(rows)} transactions")


def _undo(conn, args):
    print(f"Removed import {args.import_id} and its {store.undo_import(conn, args.import_id)} transactions")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="stmtrecon", description=__doc__)
    p.add_argument("--db", default="transactions.db", help="SQLite database file (default: transactions.db)")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("accounts", help="list accounts, or add one with --name/--type/--last4")
    a.add_argument("--name")
    a.add_argument("--type", choices=list(ACCOUNT_TYPES))
    a.add_argument("--last4")
    a.set_defaults(fn=_accounts)

    r = sub.add_parser("rule", help="add a categorizing rule")
    r.add_argument("match", help="merchant words, or a bank category/type with --source bank")
    r.add_argument("category")
    r.add_argument("--source", choices=["merchant", "bank"], default="merchant")
    r.add_argument("--priority", type=int, default=0)
    r.set_defaults(fn=_rule)

    s = sub.add_parser("scan", help="check every PDF statement in a folder (add --import to import ready ones)")
    s.add_argument("folder")
    s.add_argument("--import", dest="import_ready", action="store_true")
    s.set_defaults(fn=_scan)

    c = sub.add_parser("import-csv", help="import a CSV export into an account")
    c.add_argument("file")
    c.add_argument("--account", type=int, required=True)
    c.set_defaults(fn=_csv)

    sub.add_parser("list", help="show stored transactions").set_defaults(fn=_list)

    u = sub.add_parser("undo", help="remove one import and the transactions it added")
    u.add_argument("import_id", type=int)
    u.set_defaults(fn=_undo)

    args = p.parse_args(argv)
    if args.cmd == "accounts" and args.name and not args.type:
        p.error("--type is required when adding an account")
    conn = store.connect(args.db)
    try:
        args.fn(conn, args)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
