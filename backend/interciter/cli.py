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

    p_serve = sub.add_parser("serve", help="Run the API server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
