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


def _cmd_s2_enrich(args: argparse.Namespace) -> int:
    import json

    from .ingestion.semantic_scholar import (
        S2Error,
        get_embedding,
        get_paper,
        get_references,
    )

    try:
        paper = get_paper(args.id, use_cache=not args.no_cache)
        out: dict = {"paper": paper}
        if args.refs:
            out["references"] = get_references(
                args.id, max_records=args.max_refs, use_cache=not args.no_cache
            )
        if args.embedding:
            vector = get_embedding(args.id, use_cache=not args.no_cache)
            out["embedding_dims"] = len(vector) if vector else 0
    except S2Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2))
    return 0


def _cmd_s2_backfill(args: argparse.Namespace) -> int:
    from . import models
    from .services.enrichment import backfill_all, enrich_work

    init_db()
    with SessionLocal() as session:
        if args.all:
            results = backfill_all(
                session, limit=args.limit, fetch_embedding=not args.no_embedding
            )
        else:
            if not args.work_id:
                print("error: provide a work id or --all", file=sys.stderr)
                return 1
            work = session.get(models.PaperWork, args.work_id)
            if work is None:
                print(f"error: work {args.work_id} not found", file=sys.stderr)
                return 1
            result = enrich_work(session, work, fetch_embedding=not args.no_embedding)
            session.commit()
            results = [result]

    filled = 0
    for r in results:
        note = r.skipped_reason or (
            f"corpusId={r.s2_corpus_id} filled={r.fields_filled} "
            f"emb_dims={r.embedding_dims}"
        )
        print(f"{r.work_id}: {note}")
        filled += len(r.fields_filled)
    print(f"-- {len(results)} work(s), {filled} field(s) filled --")
    return 0


def _cmd_s2_datasets(args: argparse.Namespace) -> int:
    import json

    from .datasets import (
        S2DatasetsError,
        latest_release,
        list_releases,
        lookup_corpusid,
        pull_dataset,
    )

    try:
        if args.action == "releases":
            releases = list_releases()
            latest = latest_release()["release_id"]
            print(f"latest: {latest}")
            print(f"total releases: {len(releases)}")
            print("recent:", ", ".join(releases[-5:]))
        elif args.action == "pull":
            manifest = pull_dataset(
                args.name, release_id=args.release, max_shards=args.shards
            )
            print(f"release pinned: {manifest.release_id}")
            print(f"shards cached: {len(manifest.shards)}")
            for shard in manifest.shards:
                print(f"  {shard.dataset}/{shard.basename} ({shard.bytes} bytes)")
        elif args.action == "lookup":
            record = lookup_corpusid(args.corpusid, dataset_name=args.dataset)
            print(json.dumps(record, indent=2) if record else "not found")
    except S2DatasetsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_robokop(args: argparse.Namespace) -> int:
    import json

    from .ingestion.robokop import RobokopError, ground, query_edges
    from .services.grounding import corroborate

    try:
        if args.action == "ground":
            node = ground(args.term, biolink_type=args.type)
            print(json.dumps(node, indent=2) if node else "no grounding")
        elif args.action == "edges":
            edges = query_edges(args.subject, args.object, predicate=args.predicate)
            print(json.dumps(edges, indent=2))
        elif args.action == "corroborate":
            records = corroborate(args.subject, args.object, predicate=args.predicate)
            print(json.dumps(records, indent=2))
    except RobokopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_ground_claim(args: argparse.Namespace) -> int:
    import json

    from . import models
    from .ingestion.robokop import RobokopError
    from .services.grounding import ground_interpretation

    init_db()
    with SessionLocal() as session:
        interp = session.get(models.ClaimInterpretation, args.interpretation_id)
        if interp is None:
            print(
                f"error: interpretation {args.interpretation_id} not found",
                file=sys.stderr,
            )
            return 1
        extra = [("term", t) for t in (args.term or [])]
        try:
            result = ground_interpretation(session, interp, extra_terms=extra)
        except RobokopError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    payload = {
        "interpretation_id": result.interpretation_id,
        "groundings": [vars(g) for g in result.groundings],
    }
    print(json.dumps(payload, indent=2))
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

    p_s2 = sub.add_parser(
        "s2-enrich", help="Fetch Semantic Scholar enrichment for a paper id"
    )
    p_s2.add_argument("id", help="Paper id, e.g. DOI:10.…, PMID:…, PMCID:PMC…, CorpusId:…")
    p_s2.add_argument("--refs", action="store_true", help="Also fetch resolved references")
    p_s2.add_argument(
        "--max-refs", type=int, default=50, dest="max_refs", help="Cap references fetched"
    )
    p_s2.add_argument(
        "--embedding", action="store_true", help="Also report SPECTER2 embedding dims"
    )
    p_s2.add_argument("--no-cache", action="store_true", help="Bypass the local cache")
    p_s2.set_defaults(func=_cmd_s2_enrich)

    p_bf = sub.add_parser(
        "s2-backfill", help="Backfill s2_corpus_id + metadata gaps onto stored works"
    )
    p_bf.add_argument("work_id", nargs="?", default=None, help="A single PaperWork id")
    p_bf.add_argument(
        "--all", action="store_true", help="Enrich every work missing an s2_corpus_id"
    )
    p_bf.add_argument("--limit", type=int, default=None, help="Cap works processed with --all")
    p_bf.add_argument(
        "--no-embedding", action="store_true", help="Skip caching SPECTER2 embeddings"
    )
    p_bf.set_defaults(func=_cmd_s2_backfill)

    p_ds = sub.add_parser(
        "s2-datasets", help="Semantic Scholar bulk datasets (requires INTERCITER_S2_API_KEY)"
    )
    ds_sub = p_ds.add_subparsers(dest="action", required=True)
    ds_sub.add_parser("releases", help="List available releases")
    p_ds_pull = ds_sub.add_parser("pull", help="Download + manifest shards of a dataset")
    p_ds_pull.add_argument("name", help="Dataset name, e.g. papers, citations, abstracts")
    p_ds_pull.add_argument("--release", default="latest", help="Release id (default latest)")
    p_ds_pull.add_argument(
        "--shards", type=int, default=1, help="Max shards to pull (0/omit for all -> use --all)"
    )
    p_ds_pull.add_argument(
        "--all", action="store_const", const=None, dest="shards", help="Pull all shards"
    )
    p_ds_lookup = ds_sub.add_parser("lookup", help="Find a record by corpusid in the cache")
    p_ds_lookup.add_argument("corpusid", help="Semantic Scholar corpusId")
    p_ds_lookup.add_argument("--dataset", default="papers", help="Dataset to scan")
    p_ds.set_defaults(func=_cmd_s2_datasets)

    p_rk = sub.add_parser("robokop", help="ROBOKOP / Translator grounding + edge lookup")
    rk_sub = p_rk.add_subparsers(dest="action", required=True)
    p_rk_ground = rk_sub.add_parser("ground", help="Ground a name or CURIE to a canonical node")
    p_rk_ground.add_argument("term", help="Free-text name or a CURIE (prefix:local)")
    p_rk_ground.add_argument("--type", default=None, help="Optional BioLink type filter")
    p_rk_edges = rk_sub.add_parser("edges", help="One-hop TRAPI edges between two CURIEs")
    p_rk_edges.add_argument("subject", help="Subject CURIE")
    p_rk_edges.add_argument("object", help="Object CURIE")
    p_rk_edges.add_argument("--predicate", default=None, help="Optional BioLink predicate")
    p_rk_corr = rk_sub.add_parser(
        "corroborate", help="One-hop edges with BioLink knowledge-source provenance"
    )
    p_rk_corr.add_argument("subject", help="Subject CURIE")
    p_rk_corr.add_argument("object", help="Object CURIE")
    p_rk_corr.add_argument("--predicate", default=None, help="Optional BioLink predicate")
    p_rk.set_defaults(func=_cmd_robokop)

    p_gc = sub.add_parser(
        "ground-claim", help="Ground a stored interpretation's entity qualifiers to CURIEs"
    )
    p_gc.add_argument("interpretation_id", help="A ClaimInterpretation id")
    p_gc.add_argument(
        "--term", action="append", default=None, help="Extra free-text term to ground (repeatable)"
    )
    p_gc.set_defaults(func=_cmd_ground_claim)

    p_serve = sub.add_parser("serve", help="Run the API server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
