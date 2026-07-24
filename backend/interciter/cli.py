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
    from .ingestion.extractor import build_extractor

    xml = Path(args.path).read_text(encoding="utf-8")
    extractor = build_extractor(args.extractor, model=args.model)
    init_db()
    with SessionLocal() as session:
        result = ingest_paper(
            session, xml=xml, extractor=extractor, settings=get_settings()
        )
    print(
        f"Ingested work={result.work_id} version={result.version_id} "
        f"[{extractor.name}]\n"
        f"  passages={result.passages} occurrences={result.occurrences} "
        f"interpretations={result.interpretations}\n"
        f"  relations={result.relation_assertions} "
        f"(claim_resolved={result.claim_resolved}, paper_resolved={result.paper_resolved})"
    )
    return 0


def _load_source_xml(source: str) -> str:
    """Resolve a CLI source to JATS XML: a local file path, else a PMCID to fetch."""
    path = Path(source)
    if path.exists():
        return path.read_text(encoding="utf-8")
    from .ingestion.pmc import fetch_jats

    return fetch_jats(source, get_settings())


def _cmd_llm_export_batch(args: argparse.Namespace) -> int:
    from .ingestion.extractor import build_extractor
    from .ingestion.llm_extractor import export_requests
    from .ingestion.parser import parse_jats

    paper = parse_jats(_load_source_xml(args.source))
    extractor = build_extractor("llm", client=_NullClient(), model=args.model)
    requests = extractor.build_requests(paper)
    count = export_requests(requests, args.out)
    print(f"Wrote {count} prompt(s) to {args.out} (model={extractor.model})")
    print("Run these through your offline runner (e.g. vLLM on Biowulf), then import.")
    return 0


def _cmd_llm_import_batch(args: argparse.Namespace) -> int:
    from .ingestion.extractor import build_extractor
    from .ingestion.llm_client import BatchResponseClient, load_batch_responses

    responses = load_batch_responses(args.responses)
    client = BatchResponseClient(responses)
    extractor = build_extractor("llm", client=client, model=args.model)
    xml = _load_source_xml(args.source)
    init_db()
    with SessionLocal() as session:
        result = ingest_paper(
            session, xml=xml, extractor=extractor, settings=get_settings()
        )
    print(
        f"Imported {len(responses)} response(s); ingested work={result.work_id} "
        f"[{extractor.name}]\n"
        f"  occurrences={result.occurrences} interpretations={result.interpretations} "
        f"relations={result.relation_assertions}"
    )
    return 0


def _cmd_llm_compare(args: argparse.Namespace) -> int:
    from .evaluation.compare import compare_extractors, format_comparison
    from .evaluation.gold import load_gold, load_gold_named
    from .ingestion.extractor import build_extractor
    from .ingestion.llm_client import BatchResponseClient, load_batch_responses

    gold = load_gold_named(args.corpus) if args.corpus else load_gold(args.gold)
    extractors = {}
    if args.include_stub:
        extractors["stub"] = build_extractor("stub")
    for model in args.model or []:
        extractors[model] = build_extractor("llm", model=model)
    for spec in args.batch or []:
        name, _, path = spec.partition("=")
        if not path:
            print(f"error: --batch expects NAME=PATH, got {spec!r}", file=sys.stderr)
            return 1
        client = BatchResponseClient(load_batch_responses(path))
        extractors[name] = build_extractor("llm", client=client, model=name)
    if not extractors:
        print("error: provide --model, --batch, or --include-stub", file=sys.stderr)
        return 1
    reports = compare_extractors(gold, extractors)
    print(format_comparison(reports))
    return 0


class _NullClient:
    """A client that never returns a completion — used for prompt export only."""

    def complete(self, request):  # noqa: D401, ANN001
        return None



def _cmd_seed(_: argparse.Namespace) -> int:
    from .sample import seed_sample_corpus

    init_db()
    with SessionLocal() as session:
        summary = seed_sample_corpus(session)
    for line in summary:
        print(line)
    return 0


def _seed_corpus_dir():
    from importlib import resources

    return resources.files("interciter.data.seed_corpus")


def _load_seeds(path: str | None) -> tuple[list[str], int]:
    """Load seed ids + default target size from a JSON file (path or bundled default)."""
    import json

    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = _seed_corpus_dir().joinpath("seeds.json").read_text(encoding="utf-8")
    data = json.loads(text)
    seeds = list(data.get("seeds") or [])
    target = int(data.get("target_size") or 0)
    return seeds, target


def _cmd_seed_corpus(args: argparse.Namespace) -> int:
    import json
    from datetime import datetime, timezone

    from .ingestion import snowball

    seeds, default_target = _load_seeds(args.seeds)
    if not seeds:
        print("error: no seed ids found (check seeds.json)", file=sys.stderr)
        return 1
    target = args.target or default_target or snowball.DEFAULT_TARGET_SIZE

    init_db()
    print(f"Snowballing ~{target} papers from {len(seeds)} seed(s) via Semantic Scholar…")
    with SessionLocal() as session:
        result = snowball.build_corpus(
            session,
            seeds,
            target_size=target,
            refs_per_paper=args.refs_per_paper,
            use_cache=not args.no_cache,
            progress=lambda msg: print(f"  {msg}"),
        )

    if result.seeds_missing:
        print(f"  (unresolved seeds: {', '.join(result.seeds_missing)})")
    print(
        f"-- corpus: {result.works_total} papers "
        f"({result.works_created} new), {result.edges_created} citation edges, "
        f"{result.expansions} expansions, {result.papers_fetched} seed fetches --"
    )

    # Manifest = identifiers only, safe to commit for reproducibility.
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seeds": seeds,
        "target_size": target,
        "works_total": result.works_total,
        "works_created": result.works_created,
        "edges_created": result.edges_created,
        "papers": sorted(
            (
                {k: v for k, v in row.items() if k in ("corpus_id", "doi", "pmid")}
                for row in result.corpus
            ),
            key=lambda r: (r.get("corpus_id") or "", r.get("doi") or ""),
        ),
    }
    manifest_path = Path(args.manifest) if args.manifest else Path(
        str(_seed_corpus_dir().joinpath("manifest.json"))
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote manifest ({len(manifest['papers'])} ids): {manifest_path}")
    return 0


def _cmd_s2_fetch(args: argparse.Namespace) -> int:
    from .services import lookup

    init_db()
    with SessionLocal() as session:
        try:
            result = lookup.fetch_and_cache_paper(
                session,
                args.id,
                with_references=not args.no_references,
                refs_limit=args.refs_limit,
                use_cache=not args.no_cache,
            )
        except lookup.LookupError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    verb = "cached" if result.cache_hit else "fetched"
    print(f"{verb} work {result.work_id}")
    if result.fields_filled:
        print(f"  filled: {', '.join(result.fields_filled)}")
    print(
        f"  references: {result.stubs_created} new stub(s), "
        f"{result.edges_created} citation edge(s)"
    )
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


def _cmd_userlist(args: argparse.Namespace) -> int:
    from . import auth

    init_db()
    with SessionLocal() as session:
        users = auth.list_users(session)
    if not users:
        print("(no users — create one with `interciter useradd <name> --role admin`)")
        return 0
    for u in users:
        state = "active" if u.is_active else "inactive"
        print(f"{u.user_id}  {u.role.value:<8}  {state:<8}  {u.display_name}")
    return 0


def _cmd_usermod(args: argparse.Namespace) -> int:
    from . import auth
    from .auth import LastAdminError
    from .enums import Role

    init_db()
    with SessionLocal() as session:
        user = auth.get_user(session, args.user_id)
        if user is None:
            print(f"No such user: {args.user_id}", file=sys.stderr)
            return 1
        try:
            if args.role is not None:
                auth.set_user_role(session, user, Role(args.role))
            if args.active is not None:
                auth.set_user_active(session, user, args.active)
        except LastAdminError as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 1
        state = "active" if user.is_active else "inactive"
        print(f"Updated {user.user_id}: role={user.role.value} ({state})")
    return 0


def _cmd_userrotate(args: argparse.Namespace) -> int:
    from . import auth

    init_db()
    with SessionLocal() as session:
        user = auth.get_user(session, args.user_id)
        if user is None:
            print(f"No such user: {args.user_id}", file=sys.stderr)
            return 1
        token = auth.rotate_api_token(session, user)
    print(f"Rotated token for {user.user_id} (existing sessions revoked)")
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
            result = enrich_work(
                session,
                work,
                fetch_embedding=not args.no_embedding,
                persist_references=args.refs,
            )
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


def _cmd_integrity_check(args: argparse.Namespace) -> int:
    from . import models
    from .services.integrity import check_all, check_work

    init_db()
    with SessionLocal() as session:
        if args.all:
            results = check_all(
                session, limit=args.limit, only_unchecked=args.only_unchecked
            )
        else:
            if not args.work_id:
                print("error: provide a work id or --all", file=sys.stderr)
                return 1
            work = session.get(models.PaperWork, args.work_id)
            if work is None:
                print(f"error: work {args.work_id} not found", file=sys.stderr)
                return 1
            result = check_work(session, work)
            session.commit()
            results = [result]

    retracted = 0
    for r in results:
        if r.skipped_reason:
            note = r.skipped_reason
        else:
            note = (
                f"retracted={r.is_retracted} notice={r.integrity_notice!r} "
                f"changed={r.changed}"
            )
        print(f"{r.work_id}: {note}")
        if r.is_retracted:
            retracted += 1
    print(f"-- {len(results)} work(s) checked, {retracted} retracted --")
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
        elif args.action == "backfill":
            from .services import local_enrichment

            datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
            init_db()
            with SessionLocal() as session:
                reports = local_enrichment.backfill(
                    session,
                    datasets,
                    dry_run=args.dry_run,
                    on_shard=lambda basename: print(f"  scanning {basename}"),
                )
            for report in reports:
                mode = " (dry run)" if report.dry_run else ""
                print(f"{report.dataset}{mode}:")
                print(f"  records scanned: {report.records_scanned}")
                print(f"  works matched:   {report.works_matched}")
                if report.fields_filled:
                    filled = ", ".join(
                        f"{k}={v}" for k, v in sorted(report.fields_filled.items())
                    )
                    print(f"  fields filled:   {filled}")
                if report.dataset == "citations":
                    print(f"  edges created:   {report.edges_created}")
                    print(f"  edges existing:  {report.edges_existing}")
    except (S2DatasetsError, ValueError) as exc:
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
        written = 0
        if args.persist:
            from .services.grounding import persist_grounding

            written = persist_grounding(session, result)
            session.commit()
    payload = {
        "interpretation_id": result.interpretation_id,
        "groundings": [vars(g) for g in result.groundings],
        "persisted": written,
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
    p_ingest.add_argument(
        "--extractor", default="stub", choices=["stub", "llm"], help="Extraction backend"
    )
    p_ingest.add_argument(
        "--model", default=None, help="Model name for --extractor llm (overrides config)"
    )
    p_ingest.set_defaults(func=_cmd_ingest)

    sub.add_parser("seed", help="Seed the bundled sample corpus").set_defaults(
        func=_cmd_seed
    )

    p_corpus = sub.add_parser(
        "seed-corpus",
        help="Build a large citation-graph corpus by snowballing Semantic Scholar",
    )
    p_corpus.add_argument(
        "--target", type=int, default=None, help="Target number of papers (default from seeds.json)"
    )
    p_corpus.add_argument(
        "--seeds", default=None, help="Path to a seeds JSON file (default: bundled seeds.json)"
    )
    p_corpus.add_argument(
        "--refs-per-paper", type=int, default=50, help="Max references walked per paper"
    )
    p_corpus.add_argument(
        "--manifest", default=None, help="Where to write the id manifest (default: next to seeds.json)"
    )
    p_corpus.add_argument("--no-cache", action="store_true", help="Bypass the local S2 cache")
    p_corpus.set_defaults(func=_cmd_seed_corpus)

    p_fetch = sub.add_parser(
        "s2-fetch",
        help="Fetch one paper from Semantic Scholar by id and cache it into the DB",
    )
    p_fetch.add_argument("id", help="A Semantic Scholar id (DOI:…, PMID:…, CorpusId:…, or a bare DOI)")
    p_fetch.add_argument(
        "--no-references", action="store_true", help="Skip materializing the paper's references"
    )
    p_fetch.add_argument(
        "--refs-limit", type=int, default=100, help="Max references to materialize"
    )
    p_fetch.add_argument("--no-cache", action="store_true", help="Bypass the local S2 cache")
    p_fetch.set_defaults(func=_cmd_s2_fetch)

    p_user = sub.add_parser("useradd", help="Create a user and print its token")
    p_user.add_argument("display_name", help="Display name for the user")
    p_user.add_argument(
        "--role", default="user", choices=["user", "reviewer", "admin"]
    )
    p_user.set_defaults(func=_cmd_useradd)

    sub.add_parser("userlist", help="List accounts (id, role, state, name)").set_defaults(
        func=_cmd_userlist
    )

    p_umod = sub.add_parser("usermod", help="Change a user's role and/or activation")
    p_umod.add_argument("user_id", help="A user id (e.g. user_…)")
    p_umod.add_argument(
        "--role", default=None, choices=["user", "reviewer", "admin"], help="New role"
    )
    active = p_umod.add_mutually_exclusive_group()
    active.add_argument(
        "--activate", dest="active", action="store_const", const=True, default=None,
        help="Reactivate the account",
    )
    active.add_argument(
        "--deactivate", dest="active", action="store_const", const=False,
        help="Deactivate the account (revokes its sessions)",
    )
    p_umod.set_defaults(func=_cmd_usermod)

    p_urot = sub.add_parser(
        "userrotate", help="Issue a new token for a user (revokes old token + sessions)"
    )
    p_urot.add_argument("user_id", help="A user id (e.g. user_…)")
    p_urot.set_defaults(func=_cmd_userrotate)

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
    p_bf.add_argument(
        "--refs", action="store_true",
        help="Also fetch references and persist S2 intents/contexts onto mentions",
    )
    p_bf.set_defaults(func=_cmd_s2_backfill)

    p_int = sub.add_parser(
        "integrity-check",
        help="Flag retracted / noticed works from Crossref (scite WP5)",
    )
    p_int.add_argument("work_id", nargs="?", default=None, help="A single PaperWork id")
    p_int.add_argument(
        "--all", action="store_true", help="Check every work that has a DOI"
    )
    p_int.add_argument(
        "--only-unchecked",
        action="store_true",
        help="With --all, skip works already checked (is_retracted set)",
    )
    p_int.add_argument("--limit", type=int, default=None, help="Cap works processed with --all")
    p_int.set_defaults(func=_cmd_integrity_check)

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
    p_ds_bf = ds_sub.add_parser(
        "backfill",
        help="Stream local bulk shards into the system of record (additive only)",
    )
    p_ds_bf.add_argument(
        "--datasets",
        default="papers,tldrs,abstracts",
        help="Comma-separated passes to run (papers,tldrs,abstracts,citations)",
    )
    p_ds_bf.add_argument(
        "--dry-run", action="store_true", help="Report matches without writing"
    )
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
    p_gc.add_argument(
        "--persist", action="store_true", help="Write EntityGrounding rows to the database"
    )
    p_gc.set_defaults(func=_cmd_ground_claim)

    p_llm_export = sub.add_parser(
        "llm-export-batch",
        help="Build LLM extraction prompts for a paper as JSONL (offline batch runs)",
    )
    p_llm_export.add_argument("source", help="A JATS file path or a PMCID to fetch")
    p_llm_export.add_argument("--out", required=True, help="Output JSONL path for prompts")
    p_llm_export.add_argument("--model", default=None, help="Model name (overrides config)")
    p_llm_export.set_defaults(func=_cmd_llm_export_batch)

    p_llm_import = sub.add_parser(
        "llm-import-batch",
        help="Ingest a paper using offline batch responses (e.g. from Biowulf)",
    )
    p_llm_import.add_argument("source", help="A JATS file path or a PMCID to fetch")
    p_llm_import.add_argument("--responses", required=True, help="Batch responses JSONL")
    p_llm_import.add_argument("--model", default=None, help="Model name (overrides config)")
    p_llm_import.set_defaults(func=_cmd_llm_import_batch)

    p_llm_cmp = sub.add_parser(
        "llm-compare", help="Score extractors side by side on a gold corpus"
    )
    p_llm_cmp.add_argument("--corpus", default=None, help="Bundled gold corpus name")
    p_llm_cmp.add_argument("--gold", default=None, help="Path to a gold corpus JSON")
    p_llm_cmp.add_argument(
        "--model", action="append", default=None, help="Live LLM model (repeatable)"
    )
    p_llm_cmp.add_argument(
        "--batch", action="append", default=None,
        help="Batch-backed extractor as NAME=responses.jsonl (repeatable)",
    )
    p_llm_cmp.add_argument(
        "--include-stub", action="store_true", help="Include the deterministic stub"
    )
    p_llm_cmp.set_defaults(func=_cmd_llm_compare)

    p_serve = sub.add_parser("serve", help="Run the API server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
