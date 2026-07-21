"""Structured evaluation report.

A per-stage report mirroring docs/evaluation.md. Everything is plain dataclasses so the
report serializes cleanly to JSON (for storage/CI) and renders as a readable table.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PRF:
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    tp: int = 0
    fp: int = 0
    fn: int = 0


@dataclass
class ClassMetrics:
    precision: float
    recall: float
    f1: float
    support: int


@dataclass
class ClassificationReport:
    macro_f1: float = 0.0
    n: int = 0
    per_class: dict[str, ClassMetrics] = field(default_factory=dict)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class ParsingReport:
    citation_resolution_accuracy: float = 0.0
    citations_evaluated: int = 0
    section_recognition_accuracy: float = 0.0
    sections_evaluated: int = 0


@dataclass
class ClaimExtractionReport:
    spans: PRF = field(default_factory=PRF)
    effect_direction_accuracy: float = 0.0
    negation_accuracy: float = 0.0
    certainty_accuracy: float = 0.0
    qualifiers_evaluated: int = 0


@dataclass
class TargetRetrievalReport:
    recall_at_1: float = 0.0
    recall_at_3: float = 0.0
    precision_at_threshold: float = 0.0
    claim_resolved_gold: int = 0
    claim_resolved_predicted: int = 0


@dataclass
class CalibrationReport:
    ece: float = 0.0
    accuracy: float = 0.0
    n: int = 0
    risk_coverage: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class OperationsReport:
    papers: int = 0
    total_seconds: float = 0.0
    throughput_papers_per_s: float = 0.0
    mean_latency_s: float = 0.0
    max_latency_s: float = 0.0
    cost_per_paper_usd: float = 0.0
    cost_note: str = ""


@dataclass
class EvaluationReport:
    domain: str
    corpus_version: str
    extractor: str
    parsing: ParsingReport = field(default_factory=ParsingReport)
    claim_extraction: ClaimExtractionReport = field(default_factory=ClaimExtractionReport)
    citation_scope_accuracy: float = 0.0
    citation_scope_evaluated: int = 0
    function_classification: ClassificationReport = field(default_factory=ClassificationReport)
    stance_classification: ClassificationReport = field(default_factory=ClassificationReport)
    target_retrieval: TargetRetrievalReport = field(default_factory=TargetRetrievalReport)
    calibration: CalibrationReport = field(default_factory=CalibrationReport)
    clustering: PRF = field(default_factory=PRF)
    operations: OperationsReport = field(default_factory=OperationsReport)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_text(self) -> str:
        lines: list[str] = []
        add = lines.append
        add(f"InterCiter evaluation — {self.domain} ({self.corpus_version})")
        add(f"extractor: {self.extractor}")
        add("")
        add("Document parsing")
        add(f"  citation-marker resolution : {self.parsing.citation_resolution_accuracy:.3f} "
            f"(n={self.parsing.citations_evaluated})")
        add(f"  section recognition        : {self.parsing.section_recognition_accuracy:.3f} "
            f"(n={self.parsing.sections_evaluated})")
        add("")
        ce = self.claim_extraction
        add("Claim extraction (empirical result claims)")
        add(f"  span P / R / F1            : {ce.spans.precision:.3f} / {ce.spans.recall:.3f} "
            f"/ {ce.spans.f1:.3f}  (tp={ce.spans.tp} fp={ce.spans.fp} fn={ce.spans.fn})")
        add(f"  qualifier accuracy         : dir={ce.effect_direction_accuracy:.3f} "
            f"neg={ce.negation_accuracy:.3f} cert={ce.certainty_accuracy:.3f} "
            f"(n={ce.qualifiers_evaluated})")
        add("")
        add(f"Citation scope accuracy      : {self.citation_scope_accuracy:.3f} "
            f"(n={self.citation_scope_evaluated})")
        add("")
        add(self._format_classification("Relationship function", self.function_classification))
        add(self._format_classification("Relationship stance", self.stance_classification))
        tr = self.target_retrieval
        add("Target-claim retrieval")
        add(f"  recall@1 / recall@3        : {tr.recall_at_1:.3f} / {tr.recall_at_3:.3f} "
            f"(gold claim_resolved={tr.claim_resolved_gold})")
        add(f"  precision @ link threshold : {tr.precision_at_threshold:.3f} "
            f"(predicted={tr.claim_resolved_predicted})")
        add("")
        cal = self.calibration
        add("Confidence (stance)")
        add(f"  ECE / accuracy             : {cal.ece:.3f} / {cal.accuracy:.3f} (n={cal.n})")
        rc = "  ".join(f"cov {c:.2f}: risk {r:.3f}" for c, r in cal.risk_coverage)
        add(f"  selective risk/coverage    : {rc}")
        add("")
        cl = self.clustering
        add("Clustering (pairwise)")
        add(f"  P / R / F1                 : {cl.precision:.3f} / {cl.recall:.3f} / {cl.f1:.3f} "
            f"(tp={cl.tp} fp={cl.fp} fn={cl.fn})")
        add("")
        op = self.operations
        add("Operations")
        add(f"  papers / throughput        : {op.papers} / {op.throughput_papers_per_s:.2f} papers/s")
        add(f"  latency mean / max         : {op.mean_latency_s:.3f}s / {op.max_latency_s:.3f}s")
        add(f"  cost per paper             : ${op.cost_per_paper_usd:.4f}  ({op.cost_note})")
        return "\n".join(lines)

    @staticmethod
    def _format_classification(title: str, report: ClassificationReport) -> str:
        rows = [f"{title} (macro-F1={report.macro_f1:.3f}, n={report.n})"]
        for label, m in report.per_class.items():
            if m.support == 0:
                continue
            rows.append(
                f"  {label:<15} P={m.precision:.3f} R={m.recall:.3f} "
                f"F1={m.f1:.3f} (support={m.support})"
            )
        return "\n".join(rows) + "\n"
