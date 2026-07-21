"""Command-line entry point.

Convenience commands for the MVP: initialize the database, ingest a JATS file, seed
the bundled sample corpus, and run the API server.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import get_settings
from .db import SessionLocal, init_db
from .ingestion.pipeline import ingest_paper


def _cmd_initdb(_: argparse.Namespace) -> int:
    init_db()
    print("Database initialized.")
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    xml = Path(args.path).read_text(encoding="utf-8")
    init_db()
    with SessionLocal() as session:
        result = ingest_paper(session, xml=xml, settings=get_settings())
    print(
        f"Ingested work={result.work_id} version={result.version_id}\n"
        f"  passages={result.passages} occurrences={result.occurrences} "
        f"interpretations={result.interpretations}\n"
        f"  relations={result.relation_assertions} "
        f"(claim_resolved={result.claim_resolved}, paper_resolved={result.paper_resolved})"
    )
    return 0


def _cmd_seed(_: argparse.Namespace) -> int:
    from .sample import seed_sample_corpus

    init_db()
    with SessionLocal() as session:
        summary = seed_sample_corpus(session)
    for line in summary:
        print(line)
    return 0


def _cmd_useradd(args: argparse.Namespace) -> int:
    from .auth import create_user
    from .enums import Role

    init_db()
    with SessionLocal() as session:
        user, token = create_user(session, args.display_name, Role(args.role))
    print(f"Created user {user.user_id} ({user.role.value})")
    print(f"  token: {token}")
    print("  (shown once — store it now; only its hash is kept)")
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    import json

    from .evaluation.gold import load_gold, load_gold_named
    from .evaluation.harness import evaluate

    gold = load_gold_named(args.corpus) if args.corpus else load_gold(args.gold)
    report = evaluate(gold)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(report.format_text())
    return 0


def _cmd_pmc_fetch(args: argparse.Namespace) -> int:
    from .ingestion.pmc import PMCFetchError, fetch_jats

    try:
        xml = fetch_jats(args.pmcid, get_settings(), use_cache=not args.no_cache)
    except PMCFetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.out:
        Path(args.out).write_text(xml, encoding="utf-8")
        print(f"Wrote {len(xml)} chars to {args.out}")
    else:
        print(f"Fetched {args.pmcid}: {len(xml)} chars (cached under pmc_cache_dir)")
    return 0


def _cmd_pmc_inspect(args: argparse.Namespace) -> int:
    """Fetch + parse a PMC paper and print passages/citations to aid annotation."""
    from .ingestion.parser import parse_jats
    from .ingestion.pmc import PMCFetchError, fetch_jats

    try:
        xml = fetch_jats(args.pmcid, get_settings())
    except PMCFetchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    paper = parse_jats(xml)
    print(f"# {paper.title}")
    print(f"doi={paper.doi} pmid={paper.pmid} year={paper.year} venue={paper.venue}")
    print(f"authors: {', '.join(paper.authors)}")
    print(f"references: {len(paper.references)} | passages: {len(paper.passages)}\n")
    for i, p in enumerate(paper.passages):
        cites = ", ".join(
            f"[{c.marker_text}->{c.rid}: {paper.references.get(c.rid).doi if c.rid in paper.references else '?'}]"
            for c in p.citations
        )
        section = p.section or "-"
        print(f"[{i}] ({section}) {p.text}")
        if cites:
            print(f"      cites: {cites}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("interciter.api.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="interciter", description="InterCiter MVP CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("initdb", help="Create database tables").set_defaults(func=_cmd_initdb)

    p_ingest = sub.add_parser("ingest", help="Ingest a JATS XML file")
    p_ingest.add_argument("path", help="Path to a JATS/PMC XML file")
    p_ingest.set_defaults(func=_cmd_ingest)

    sub.add_parser("seed", help="Seed the bundled sample corpus").set_defaults(
        func=_cmd_seed
    )

    p_user = sub.add_parser("useradd", help="Create a user and print its token")
    p_user.add_argument("display_name", help="Display name for the user")
    p_user.add_argument(
        "--role", default="user", choices=["user", "reviewer", "admin"]
    )
    p_user.set_defaults(func=_cmd_useradd)

    p_eval = sub.add_parser("evaluate", help="Run the evaluation harness on a gold corpus")
    p_eval.add_argument(
        "--gold", default=None, help="Path to a gold corpus JSON file"
    )
    p_eval.add_argument(
        "--corpus",
        default=None,
        help="Name of a bundled gold corpus under data/gold (e.g. t2d_glycemic_v1)",
    )
    p_eval.add_argument("--json", action="store_true", help="Emit the report as JSON")
    p_eval.set_defaults(func=_cmd_evaluate)

    p_fetch = sub.add_parser("pmc-fetch", help="Fetch and cache a PMC OA paper's JATS XML")
    p_fetch.add_argument("pmcid", help="PMC id, e.g. PMC1234567")
    p_fetch.add_argument("--out", default=None, help="Also write the XML to this path")
    p_fetch.add_argument("--no-cache", action="store_true", help="Bypass the local cache")
    p_fetch.set_defaults(func=_cmd_pmc_fetch)

    p_inspect = sub.add_parser(
        "pmc-inspect", help="Fetch + parse a PMC paper; print passages/citations"
    )
    p_inspect.add_argument("pmcid", help="PMC id, e.g. PMC1234567")
    p_inspect.set_defaults(func=_cmd_pmc_inspect)

    p_serve = sub.add_parser("serve", help="Run the API server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
