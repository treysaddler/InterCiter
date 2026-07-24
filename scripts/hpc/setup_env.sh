#!/bin/bash
# One-time setup: build the vLLM Apptainer image for InterCiter bulk extraction on NIEHS.
#
# Why a container? The compute nodes run an OLDER glibc (2.28) than the scigate login
# node (2.34), and there is NO environment-module system. A pip/conda env built on
# scigate therefore fails on the compute nodes (e.g. vLLM's `llguidance` wheel needs
# GLIBC_2.30). Apptainer/Singularity IS available on the compute nodes, so the robust,
# HPC-native fix is to run vLLM inside a container that bundles a matching glibc + CUDA.
#
# Run this ONCE, on a COMPUTE node (never scigate), e.g.:
#   srun --partition=normal --cpus-per-task=4 --mem=16g --time=1:00:00 \
#       bash scripts/hpc/setup_env.sh
#
# Overrides:
#   IMAGE=docker://vllm/vllm-openai:latest   # source image (pin a tag for reproducibility)
#   SIF=$HOME/interciter/vllm.sif            # output .sif (persistent, reused every job)

set -euo pipefail

IMAGE="${IMAGE:-docker://vllm/vllm-openai:latest}"
SIF="${SIF:-$HOME/interciter/vllm.sif}"
export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-$HOME/.apptainer/cache}"

if ! command -v apptainer >/dev/null 2>&1; then
    echo "error: apptainer not found — run this on a compute node, not scigate" >&2
    exit 1
fi

mkdir -p "$(dirname "$SIF")" "$APPTAINER_CACHEDIR"
echo "Pulling $IMAGE -> $SIF (several GB, one time)…"
apptainer pull --force "$SIF" "$IMAGE"

echo
echo "Built $SIF:"
apptainer exec "$SIF" python3 -c "import vllm; print('vllm', vllm.__version__)"
echo
echo "Done. The sbatch script runs this image automatically (CONTAINER=$SIF)."
echo "Submit: sbatch --gres=gpu:a100:1 --export=ALL,MODEL=<model>,BATCH_DIR=<dir> scripts/hpc/extract.sbatch"
