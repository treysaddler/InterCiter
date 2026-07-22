# InterCiter API — FastAPI/uvicorn service.
#
# Multi-stage: build the package into an isolated virtualenv, then copy that venv
# into a slim runtime image that runs as an unprivileged user. Postgres support
# (the `prod` extra) is installed so the same image can target SQLite locally or a
# postgresql+psycopg URL in production via INTERCITER_DATABASE_URL.

# --- Build stage ------------------------------------------------------------
FROM python:3.13-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN python -m venv "$VIRTUAL_ENV"

# Copy only what the build needs first so the dependency layer caches well.
COPY pyproject.toml README.md ./
COPY interciter ./interciter

RUN pip install ".[prod]"

# --- Runtime stage ----------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Bind to all interfaces inside the container; keep cookies Secure by default.
    INTERCITER_SESSION_COOKIE_SECURE=true

# Run as a non-root user.
RUN groupadd --system app && useradd --system --gid app --home /app app

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
USER app

EXPOSE 8000

# uvicorn directly (not the CLI) so worker count is tunable via the compose command.
# init_db() runs on startup and create_all is idempotent.
CMD ["uvicorn", "interciter.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
