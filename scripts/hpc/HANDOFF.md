# NIEHS HPC bulk LLM extraction — handoff notes

Status: pipeline code is complete and tested; the **only** open blocker is getting
model weights onto the cluster (the compute nodes cannot reach HuggingFace). This
doc captures the hard-won operational facts so the work can be resumed cold.

## Goal

Run bulk **offline** claim extraction with a local LLM (vLLM) on the NIEHS SLURM
cluster, extending the existing single-paper batch seam (`llm-export-batch` /
`llm-import-batch`) to a whole corpus.

## What is built (this repo)

- `backend/interciter/ingestion/batch.py` — `export_corpus()` / `ingest_corpus()`.
  Writes `manifest.json` + `prompts.jsonl` + per-paper source XML; pins the model
  and `prompt_template_version` so the content-addressed `request_id`
  (`sha256(template\0model\0passage_text)`) matches on import.
- `backend/interciter/cli.py` — verbs `llm-export-corpus` / `llm-import-corpus`.
- `scripts/hpc/run_vllm_batch.py` — standalone vLLM runner (imports only `vllm` +
  stdlib, so no `interciter` install is needed on the cluster). Groups prompts by
  `(temperature, max_tokens)`, calls `llm.chat`, writes `{request_id, completion}`.
  `--enable-thinking` defaults OFF (reasoning models emit thinking otherwise).
- `scripts/hpc/extract.sbatch` — SLURM job; runs the runner via `apptainer exec --nv`.
- `scripts/hpc/setup_env.sh` — `apptainer pull ~/interciter/vllm.sif docker://vllm/vllm-openai:latest`.
- `scripts/hpc/README.md` — 3-step workflow + GPU sizing table.
- `backend/tests/test_batch.py` — 4 offline tests (full backend suite: 31 pass).

## Connecting to the cluster

- **Only public entry:** `ssh.niehs.nih.gov` (157.98.255.22), **smart-card / PKCS11**
  auth (`/usr/local/lib/opensc-pkcs11.so`), NIH user `saddlerto`.
- `scigate`, `fermi`, `triton` are **internal-only**. `fermi`/`triton` do not
  resolve from the laptop or the bastion (NXDOMAIN); only `scigate` resolves once
  you are on the bastion (157.98.105.15).
- Two working paths (see `~/.ssh/config`):
  - **SOCKS tunnel** (`niehs-tunnel` in `.zshrc`): `ssh -I opensc-pkcs11 -D 8080`,
    then `scigate` via `ProxyCommand nc -X 5 -x 127.0.0.1:8080`.
  - **Tunnel-free** (preferred, bypasses the `nc` SOCKS layer): host `niehs-gateway`
    (bastion, PKCS11) + `scigate-direct` (`ProxyJump niehs-gateway`, password auth,
    `PubkeyAuthentication no`).
- The internal hop (`scigate`) uses NIH **password**, not the card — set
  `PubkeyAuthentication no` and `PreferredAuthentications keyboard-interactive,password`
  or you hit "too many authentication failures" (the card is held by the tunnel).
- **fermi/triton** are only reachable as `ssh scigate` then `ssh fermi`
  (passwordless from scigate via GSSAPI/hostbased). Automate with:
  ```sh
  ssh scigate-direct 'ssh -o BatchMode=yes -o ConnectTimeout=8 fermi "…"'
  ```
  Triple-nested quoting is fragile — base64-encode the remote script and pipe it to
  `base64 -d | bash`.
- SLURM binaries live in `/ddn/gs1/tools/slurm/bin` (login-shell only) → wrap remote
  SLURM commands in `bash -lc "…"`.
- A harmless linuxbrew warning appears on login; filter with `| grep -viE 'linuxbrew|brew'`.

## Compute / environment facts

- `fermi` = `gn040801` = an **A100-PCIE-40GB** GPU node. The GPU partition also has
  A100 (4/node and 2/node) and V100 nodes. Account `niehs_dttothers`, QOS `normal`.
- Home is shared `/ddn/gs1` (multi-PB free), visible from scigate, fermi, and SLURM
  compute nodes — so a model staged once is visible to jobs.
- **GLIBC mismatch:** scigate glibc 2.34 vs compute-node glibc 2.28. Conda/pip envs
  built on scigate fail on compute nodes (vLLM's `llguidance` needs GLIBC_2.30).
  **Use the Apptainer container** (`~/interciter/vllm.sif`, 7.6 GB, vLLM 0.25.1).
  The `~/interciter-vllm` venv on fermi is the abandoned broken approach.
- Container has `python3` (not `python`); pass the runner path via `$SLURM_SUBMIT_DIR`
  (SLURM spools the batch script, so `$0`'s directory is wrong).

## The blocker: model staging

Every laptop↔NIEHS byte crosses one slow WAN segment, and the cluster cannot reach
HuggingFace:

| Attempt | Result |
| --- | --- |
| tar-over-ssh (SOCKS) | died (`tar: Write error`) at ~7 MB |
| rsync over SOCKS tunnel (`nc`) | ~7.8 kB/s (852 h ETA) |
| rsync over native ProxyJump (no SOCKS) | ~124 kB/s (53 h ETA) — 16× better, still unusable |
| compute/fermi → `huggingface.co` | **blocked** (CloudFront; curl 000 timeout, v4+v6) |
| `hf-mirror.com` API | works (HTTP 308) |
| `hf-mirror.com` file `/resolve/` endpoint | **308-redirects back to huggingface.co** → blocked; the mirror does not self-host files. Dead end. |

- Compute nodes **can** reach `pypi.org`, `github.com`, `registry-1.docker.io`.
- The laptop can reach official HF; Gemma 4 12B (24 GB) is downloaded and verified
  locally, and official SHA256 of all files is recorded (for provenance verification
  of whatever ultimately lands on the cluster).

## Options to try next (unblock staging)

1. **NIEHS outbound HTTP proxy** — ask HPC admins whether a web proxy reaches
   huggingface.co; if so, set `https_proxy`/`HF_ENDPOINT` on the compute node.
2. **SMB `//wine/<username>`** (advertised in the scigate banner) — likely maps to
   the same `/ddn` home and may be reachable on NIEHS **VPN** (not the SOCKS-only
   posture used this session; `wine` did not resolve without VPN).
3. **OCI artifact** — compute nodes reach dockerhub/GHCR; bake the weights into a
   container/registry you control and `apptainer pull` on the cluster at full speed.
4. **OpenOnDemand / dedicated data-transfer node (Globus?)** — advertised in the
   banner; may offer a fast transfer path.
5. **Prove the pipeline with a small model first** (e.g. a 2–4 GB model) — even the
   124 kB/s native-ProxyJump rsync can move that overnight, validating the full
   `sbatch → completions → llm-import-corpus` loop while staging is sorted.

## Ready-to-run once weights are staged

Batch already exported on the cluster at `~/interciter/batch-smoke`
(95 prompts; PMC4771973 + PMC6099453). Submit:

```sh
ssh scigate 'bash -lc "cd ~/interciter && sbatch --gres=gpu:a100:1 \
  --export=ALL,MODEL=google/gemma-4-12B-it,BATCH_DIR=\$HOME/interciter/batch-smoke,HF_HUB_OFFLINE=1 \
  extract.sbatch"'
```

Monitor `squeue -j <id>` and `tail ~/interciter/interciter-extract-<id>.out`, then
copy `completions.jsonl` back and run
`interciter llm-import-corpus --dir batch-smoke --responses completions.jsonl`.
