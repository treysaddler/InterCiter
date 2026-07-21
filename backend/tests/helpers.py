"""Shared test helpers."""

from __future__ import annotations

from importlib import resources


def load_sample(name: str) -> str:
    return (
        resources.files("interciter.data.sample")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )
