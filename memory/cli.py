"""RAVEN Memory - tiny manual CLI (prints raw data to YOUR terminal)."""
from __future__ import annotations

import argparse
import sys

from .exceptions import MemoryError_
from .manager import MemoryManager


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="raven-memory", description="RAVEN Memory CLI")
    p.add_argument("--db", default=None, help="Database path (default: <project>/data/raven.db)")
    sub = p.add_subparsers(dest="command")

    a = sub.add_parser("add", help="Add a fact")
    a.add_argument("content")
    a.add_argument("--category", default="other")
    a.add_argument("--sensitivity", type=int, default=None)
    a.add_argument("--source", default="user")
    a.add_argument("--pending", action="store_true", help="store as pending")

    s = sub.add_parser("search", help="Search facts")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--include-sensitive", action="store_true")
    s.add_argument("--include-pending", action="store_true")

    l = sub.add_parser("list", help="List facts")
    l.add_argument("--limit", type=int, default=50)
    l.add_argument("--offset", type=int, default=0)
    l.add_argument("--category", default=None)
    l.add_argument("--status", default=None)

    e = sub.add_parser("edit", help="Edit a fact")
    e.add_argument("id", type=int)
    e.add_argument("--content", default=None)
    e.add_argument("--category", default=None)
    e.add_argument("--sensitivity", type=int, default=None)

    for name, hlp in (("delete", "Delete a fact"), ("confirm", "Confirm a pending fact")):
        d = sub.add_parser(name, help=hlp)
        d.add_argument("id", type=int)

    x = sub.add_parser("export", help="Export to JSON (RAW private data!)")
    x.add_argument("path")
    i = sub.add_parser("import", help="Import from JSON")
    i.add_argument("path")

    sub.add_parser("entities", help="List entities")
    ae = sub.add_parser("add-entity", help="Add an entity")
    ae.add_argument("name")
    ae.add_argument("--type", default="person")
    ae.add_argument("--aliases", nargs="*", default=[])
    ue = sub.add_parser("update-entity", help="Update an entity")
    ue.add_argument("id", type=int)
    ue.add_argument("--name", default=None)
    ue.add_argument("--type", default=None)
    ue.add_argument("--aliases", nargs="*", default=None)
    de = sub.add_parser("delete-entity", help="Delete an entity")
    de.add_argument("id", type=int)
    return p


def _show(f) -> str:
    return f"[{f.id}] ({f.category}, s={f.sensitivity}, {f.status}) {f.content}"


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if not args.command:
        _parser().print_help()
        return 1
    c = args.command
    try:
        with MemoryManager(db_path=args.db) as m:
            if c == "add":
                f = m.add(args.content, category=args.category, sensitivity=args.sensitivity,
                          source=args.source, status="pending" if args.pending else "confirmed")
                print(f"Added: id={f.id} category={f.category} sensitivity={f.sensitivity} status={f.status}")
            elif c == "search":
                rs = m.search(args.query, k=args.k, include_sensitive=args.include_sensitive,
                              include_pending=args.include_pending)
                print("\n".join(_show(f) for f in rs) if rs else "No results.")
            elif c == "list":
                fs = m.list(limit=args.limit, offset=args.offset, category=args.category, status=args.status)
                print("\n".join(_show(f) for f in fs) if fs else "No facts.")
            elif c == "edit":
                print(f"Updated: id={m.update(args.id, content=args.content, category=args.category, sensitivity=args.sensitivity).id}")
            elif c == "delete":
                m.delete(args.id)
                print(f"Deleted: id={args.id}")
            elif c == "confirm":
                print(f"Confirmed: id={m.confirm(args.id).id}")
            elif c == "export":
                print(f"Exported {m.export_json(args.path)} records (RAW, unencrypted) to {args.path}")
            elif c == "import":
                n = m.import_json(args.path)
                r = m.last_import_report
                print(f"Imported {n} new records (duplicates={r['duplicates']}, skipped={r['skipped']})")
            elif c == "entities":
                es = m.entity_list()
                print("\n".join(f"  {e['name']} ({e['type']}) aliases={e['aliases']}" for e in es) if es else "No entities.")
            elif c == "add-entity":
                e = m.add_entity(args.name, type=args.type, aliases=args.aliases)
                print(f"Entity: id={e.id}")
            elif c == "update-entity":
                e = m.update_entity(args.id, name=args.name, type=args.type, aliases=args.aliases)
                print(f"Updated entity: id={e.id}")
            elif c == "delete-entity":
                m.delete_entity(args.id)
                print(f"Deleted entity: id={args.id}")
    except MemoryError_ as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())