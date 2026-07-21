"""Model-comparison harness — score extractors side by side on one gold corpus.

Runs the standard evaluation ([`harness.evaluate`](harness.py)) once per extractor and
lays the headline metrics out in a table, so a frontier model (via the NIEHS LiteLLM
proxy), a local Biowulf model, and the deterministic stub can be compared on identical
gold data. The point is quality vs. cost: same corpus, same scoring, different backend.
"""

from __future__ import annotations

from ..ingestion.extractor import Extractor
from .gold import GoldCorpus
from .harness import evaluate
from .report import EvaluationReport


def compare_extractors(
    gold: GoldCorpus, extractors: dict[str, Extractor]
) -> dict[str, EvaluationReport]:
    """Evaluate each named extractor on the same gold corpus."""
    return {name: evaluate(gold, extractor=ext) for name, ext in extractors.items()}


def format_comparison(reports: dict[str, EvaluationReport]) -> str:
    """Render a compact metric-by-model table."""
    if not reports:
        return "(no extractors compared)"

    rows: list[tuple[str, callable]] = [
        ("extraction recall", lambda r: r.claim_extraction.spans.recall),
        ("function macro-F1", lambda r: r.function_classification.macro_f1),
        ("stance macro-F1", lambda r: r.stance_classification.macro_f1),
        ("target recall@3", lambda r: r.target_retrieval.recall_at_3),
        ("clustering recall", lambda r: r.clustering.recall),
        ("calibration ECE", lambda r: r.calibration.ece),
        ("mean latency (s)", lambda r: r.operations.mean_latency_s),
    ]
    names = list(reports)
    width = max(18, *(len(n) for n in names))
    header = "metric".ljust(20) + "".join(n.rjust(width + 2) for n in names)
    lines = [header, "-" * len(header)]
    for label, getter in rows:
        cells = "".join(f"{getter(reports[n]):>{width + 2}.3f}" for n in names)
        lines.append(label.ljust(20) + cells)
    return "\n".join(lines)
