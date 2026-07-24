#!/usr/bin/env python3
"""Offline vLLM batch runner for InterCiter claim extraction (NIEHS SLURM / GPU node).

Reads a ``prompts.jsonl`` produced by ``interciter llm-export-corpus`` (or
``llm-export-batch``) and writes a ``completions.jsonl`` of ``{"request_id","completion"}``
rows that ``interciter llm-import-corpus`` replays back through the strict extractor.

This script is **standalone** — it imports only ``vllm`` (plus the stdlib), so it does
not need the InterCiter package installed on the cluster. It is model-agnostic: pass any
HuggingFace model id or a local path via ``--model`` / ``$MODEL``.

Each prompt row looks like::

    {"request_id": "...", "model": "...", "temperature": 0.0, "max_tokens": 1536,
     "messages": [{"role": "system", ...}, {"role": "user", ...}]}

Requests are grouped by sampling params so each group is one efficient vLLM batch. The
model's chat template is applied automatically by ``LLM.chat``.

Example (inside an sbatch job)::

    python run_vllm_batch.py \
        --prompts prompts.jsonl --out completions.jsonl \
        --model meta-llama/Llama-3.1-8B-Instruct \
        --tensor-parallel-size 1 --max-model-len 8192
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict


def _load_prompts(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Offline vLLM batch runner for InterCiter.")
    p.add_argument("--prompts", default=os.environ.get("PROMPTS", "prompts.jsonl"))
    p.add_argument("--out", default=os.environ.get("OUT", "completions.jsonl"))
    p.add_argument(
        "--model",
        default=os.environ.get("MODEL"),
        help="HuggingFace model id or a local path (or set $MODEL).",
    )
    p.add_argument(
        "--tensor-parallel-size",
        type=int,
        default=int(os.environ.get("TENSOR_PARALLEL_SIZE", "1")),
        help="Number of GPUs to shard the model across (match --gres).",
    )
    p.add_argument(
        "--max-model-len",
        type=int,
        default=int(os.environ["MAX_MODEL_LEN"]) if os.environ.get("MAX_MODEL_LEN") else None,
        help="Max context length; defaults to the model's own setting.",
    )
    p.add_argument(
        "--gpu-memory-utilization",
        type=float,
        default=float(os.environ.get("GPU_MEMORY_UTILIZATION", "0.90")),
    )
    p.add_argument(
        "--dtype",
        default=os.environ.get("DTYPE", "auto"),
        help="auto | bfloat16 | float16 (auto is usually right).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        default=os.environ.get("GUIDED_JSON", "").lower() in ("1", "true", "yes"),
        help="Constrain output to a JSON object via guided decoding (if supported).",
    )
    p.add_argument(
        "--enable-thinking",
        action="store_true",
        default=os.environ.get("ENABLE_THINKING", "").lower() in ("1", "true", "yes"),
        help="Let reasoning models (Qwen3.x, etc.) emit a thinking trace. Off by default "
        "— claim extraction wants fast, deterministic JSON, not chain-of-thought.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.model:
        print("error: pass --model or set $MODEL", file=sys.stderr)
        return 2

    prompts = _load_prompts(args.prompts)
    if not prompts:
        print(f"No prompts in {args.prompts}; nothing to do.", file=sys.stderr)
        # Still write an (empty) output so downstream steps have a stable artifact.
        open(args.out, "w", encoding="utf-8").close()
        return 0

    # Import here so --help works without vllm installed.
    from vllm import LLM, SamplingParams

    llm_kwargs: dict = {
        "model": args.model,
        "tensor_parallel_size": args.tensor_parallel_size,
        "gpu_memory_utilization": args.gpu_memory_utilization,
        "dtype": args.dtype,
    }
    if args.max_model_len:
        llm_kwargs["max_model_len"] = args.max_model_len

    print(
        f"Loading {args.model} (tp={args.tensor_parallel_size}, dtype={args.dtype}) "
        f"for {len(prompts)} prompt(s)…",
        flush=True,
    )
    llm = LLM(**llm_kwargs)

    guided = None
    if args.json:
        try:
            from vllm.sampling_params import GuidedDecodingParams

            guided = GuidedDecodingParams(json={"type": "object"})
        except Exception as exc:  # noqa: BLE001
            print(f"warning: guided JSON unavailable ({exc}); continuing free-form.",
                  file=sys.stderr)

    # Group by sampling params so each group is one homogeneous vLLM batch.
    groups: dict[tuple[float, int], list[dict]] = defaultdict(list)
    for row in prompts:
        key = (float(row.get("temperature", 0.0)), int(row.get("max_tokens", 1536)))
        groups[key].append(row)

    written = 0
    # Reasoning models read this from their chat template; harmless for models that
    # ignore it (Jinja simply doesn't reference the unused variable).
    chat_kwargs = {"chat_template_kwargs": {"enable_thinking": args.enable_thinking}}
    with open(args.out, "w", encoding="utf-8") as out_fh:
        for (temperature, max_tokens), rows in groups.items():
            sp_kwargs: dict = {"temperature": temperature, "max_tokens": max_tokens}
            if guided is not None:
                sp_kwargs["guided_decoding"] = guided
            sampling = SamplingParams(**sp_kwargs)
            conversations = [row["messages"] for row in rows]
            try:
                outputs = llm.chat(conversations, sampling, **chat_kwargs)
            except TypeError:
                # Older vLLM without chat_template_kwargs support.
                outputs = llm.chat(conversations, sampling)
            for row, output in zip(rows, outputs):
                completion = output.outputs[0].text if output.outputs else ""
                out_fh.write(
                    json.dumps({"request_id": row["request_id"], "completion": completion})
                    + "\n"
                )
                written += 1
            print(
                f"  temp={temperature} max_tokens={max_tokens}: {len(rows)} done",
                flush=True,
            )

    print(f"Wrote {written} completion(s) to {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
