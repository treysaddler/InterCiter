"""Evaluation harness — a first-class component, not a citation-intent shortcut.

Implements the per-stage evaluation described in docs/evaluation.md: a manually
adjudicated gold corpus, metrics computed separately for each pipeline stage (errors
compound, so stages are measured independently), and abstention treated as measured
behavior (selective risk / coverage, calibration error).

The harness ingests the gold papers into an isolated in-memory database and scores the
pipeline's predictions against the gold labels. It is offline infrastructure: a library
plus a CLI (``interciter evaluate``), demonstrated here on the deterministic stub.
"""
