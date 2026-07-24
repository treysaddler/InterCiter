#!/bin/bash
# InterCiter bulk claim extraction — NIEHS SLURM (GPU) batch job.
#
# Runs a local LLM over a consolidated prompts.jsonl (produced by
# `interciter llm-export-corpus`) and writes completions.jsonl for
# `interciter llm-import-corpus`. Model-agnostic: set MODEL to any HF id or local path.
#
# NIEHS gpu partition (confirmed 2026-07): A100-PCIE-40GB (4 or 2 per node, compute
# 8.0, bf16-capable) and V100 (16-32GB). Prefer A100. Account niehs_dttothers, QOS normal.
# Type-qualified GRES works: --gres=gpu:a100:1 (or gpu:v100:1). Bump the count for
# tensor-parallel multi-GPU (e.g. --gres=gpu:a100:2 for Qwen3.6 27B / 35B-A3B).
#
# Smoke test on ONE A100-40GB (Gemma 4 12B or Qwen3.5 9B fit in bf16):
#   sbatch --gres=gpu:a100:1 \
#     --export=ALL,MODEL=google/gemma-4-12b-it,BATCH_DIR=$PWD/mybatch \
#     scripts/hpc/extract.sbatch
#
# Bulk run on TWO A100 (Qwen3.6 35B A3B — MoE, 3B active, fast; TP=2):
#   sbatch --gres=gpu:a100:2 \
#     --export=ALL,MODEL=Qwen/Qwen3.6-35B-A3B,TENSOR_PARALLEL_SIZE=2,BATCH_DIR=$PWD/mybatch \
#     scripts/hpc/extract.sbatch
#
# Confirm the exact HuggingFace repo id for your chosen model before submitting.
#
# The prompts file defaults to $BATCH_DIR/prompts.jsonl and the output to
# $BATCH_DIR/completions.jsonl. Copy $BATCH_DIR back to your workstation afterward.

#SBATCH --job-name=interciter-extract
#SBATCH --partition=gpu
#SBATCH --gres=gpu:a100:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64g
#SBATCH --time=24:00:00
#SBATCH --mail-type=END,FAIL
#SBATCH --output=interciter-extract-%j.out
# Set your address at submit time: --mail-user=you@nih.gov (or export SBATCH_MAIL_USER)

set -euo pipefail

# --- configuration (override via --export=ALL,VAR=value) --------------------------
: "${MODEL:?Set MODEL to a HuggingFace id or local path (e.g. google/gemma-4-12B-it)}"
BATCH_DIR="${BATCH_DIR:-$PWD}"
PROMPTS="${PROMPTS:-$BATCH_DIR/prompts.jsonl}"
OUT="${OUT:-$BATCH_DIR/completions.jsonl}"
TENSOR_PARALLEL_SIZE="${TENSOR_PARALLEL_SIZE:-${SLURM_GPUS_ON_NODE:-1}}"
CONTAINER="${CONTAINER:-$HOME/interciter/vllm.sif}"
# SLURM copies the batch script to a spool dir, so $0's dir is not the submit dir.
# The runner is expected alongside where you submitted from (SLURM_SUBMIT_DIR).
RUNNER="${RUNNER:-${SLURM_SUBMIT_DIR:-$PWD}/run_vllm_batch.py}"

# Persistent, SHARED HuggingFace cache: model weights download ONCE and are reused by
# every subsequent job (not re-downloaded per batch). It lives in $HOME (on the large
# shared /ddn filesystem, visible from all compute nodes). Override HF_HOME to relocate.
export HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
mkdir -p "$HF_HOME"

echo "Job $SLURM_JOB_ID on $(hostname)"
echo "  MODEL=$MODEL  TP=$TENSOR_PARALLEL_SIZE"
echo "  PROMPTS=$PROMPTS  OUT=$OUT  HF_HOME=$HF_HOME"
nvidia-smi --query-gpu=index,name,memory.total --format=csv || true

# --- run vLLM inside the Apptainer container (built by setup_env.sh) ---------------
# The compute nodes' glibc (2.28) is older than scigate's (2.34) and there is no module
# system, so a host conda/pip env is fragile. The container bundles a matching glibc +
# CUDA + vLLM. $HOME is auto-mounted by Apptainer, so the batch dir, runner, and HF
# cache (all under $HOME) are visible inside; --nv exposes the GPUs.
if [ ! -f "$CONTAINER" ]; then
    echo "error: container $CONTAINER not found — run scripts/hpc/setup_env.sh first" >&2
    exit 1
fi
apptainer exec --nv \
    --env HF_HOME="$HF_HOME" \
    --env HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-0}" \
    "$CONTAINER" \
    python3 "$RUNNER" \
        --prompts "$PROMPTS" \
        --out "$OUT" \
        --model "$MODEL" \
        --tensor-parallel-size "$TENSOR_PARALLEL_SIZE"

echo "Done. Copy $OUT back and run: interciter llm-import-corpus --dir $BATCH_DIR --responses $OUT"
