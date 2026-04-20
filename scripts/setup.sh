#!/usr/bin/env bash
# Miami — one-shot workspace setup.
#
# What it does (idempotent — safe to re-run):
#   1. Checks + installs required tooling (brew, uv, pnpm, postgres@17 + pgvector)
#   2. Ensures postgresql@17 is running, creates `miami_owner` superuser + `miami` db
#   3. Copies .env.example -> .env (only if .env is missing)
#   4. Copies apps/web/.env.example -> apps/web/.env.local for Next.js
#   5. uv sync --all-packages --all-extras
#   6. pnpm install
#   7. alembic upgrade head
#   8. Seeds the dev catalog + runs the daily pipeline once so the dashboard has data
#   9. Prints the URLs to open next
#
# Usage:
#   ./scripts/setup.sh           # full setup
#   ./scripts/setup.sh --no-run  # skip pipeline (fast CI-style setup)
#
# Platform: macOS (Homebrew). Linux/WSL users should adapt the postgres + pgvector
# install commands; the rest of the script is portable.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# --- colors ---
if [[ -t 1 ]]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'
  RED=$'\033[31m'; CYAN=$'\033[36m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; GREEN=""; YELLOW=""; RED=""; CYAN=""; RESET=""
fi

step() { echo "${BOLD}${CYAN}==>${RESET} ${BOLD}$*${RESET}"; }
info() { echo "${DIM}    $*${RESET}"; }
ok()   { echo "${GREEN}    ✓${RESET} $*"; }
warn() { echo "${YELLOW}    ⚠${RESET} $*"; }
fail() { echo "${RED}    ✗${RESET} $*" >&2; exit 1; }

RUN_PIPELINE=1
for arg in "$@"; do
  case "$arg" in
    --no-run) RUN_PIPELINE=0 ;;
    -h|--help)
      sed -n '2,22p' "$0"; exit 0 ;;
    *) fail "unknown arg: $arg" ;;
  esac
done

# ---------- 0. sanity ----------
step "Checking platform"
if [[ "$(uname)" != "Darwin" ]]; then
  warn "Non-macOS detected. You'll need to install Postgres 17 + pgvector yourself;"
  warn "the rest of this script should work unchanged."
fi

# ---------- 1. Homebrew ----------
if ! command -v brew >/dev/null; then
  fail "Homebrew is required on macOS. Install from https://brew.sh then re-run."
fi
ok "brew $(brew --version | head -1)"

# ---------- 2. uv ----------
step "Ensuring uv (Python package manager) is installed"
if ! command -v uv >/dev/null; then
  info "uv not found — installing via brew"
  brew install uv
fi
ok "uv $(uv --version)"

# ---------- 3. Node + pnpm ----------
step "Ensuring Node + pnpm are installed"
if ! command -v node >/dev/null; then
  info "Node not found — installing node@20 via brew"
  brew install node@20
fi
ok "node $(node --version)"

if ! command -v pnpm >/dev/null; then
  info "pnpm not found — installing via npm"
  npm install -g pnpm
fi
ok "pnpm $(pnpm --version)"

# ---------- 4. Postgres 17 + pgvector ----------
step "Ensuring postgresql@17 + pgvector are installed"
if ! brew list postgresql@17 >/dev/null 2>&1; then
  info "postgresql@17 not found — installing via brew"
  brew install postgresql@17
fi
if ! brew list pgvector >/dev/null 2>&1; then
  info "pgvector not found — installing via brew"
  brew install pgvector
fi
PG_BIN="/usr/local/opt/postgresql@17/bin"
[[ -d /opt/homebrew/opt/postgresql@17 ]] && PG_BIN="/opt/homebrew/opt/postgresql@17/bin"
export PATH="${PG_BIN}:${PATH}"
ok "postgresql@17 at ${PG_BIN}"

# ---------- 5. Start postgres ----------
step "Starting postgresql@17"
if ! brew services list | grep -q "postgresql@17.*started"; then
  brew services start postgresql@17 >/dev/null
  info "waiting for postgres to accept connections..."
  for i in {1..30}; do
    if pg_isready -h localhost -p 5432 >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi
pg_isready -h localhost -p 5432 >/dev/null 2>&1 || fail "postgres did not come up on :5432"
ok "postgres ready on localhost:5432"

# ---------- 6. Create roles + database ----------
step "Ensuring miami_owner superuser + miami database exist"
psql -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='miami_owner'" | grep -q 1 || \
  psql -d postgres -c "CREATE USER miami_owner WITH SUPERUSER LOGIN PASSWORD 'miami_owner';" >/dev/null
ok "role miami_owner"
psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='miami'" | grep -q 1 || \
  psql -d postgres -c "CREATE DATABASE miami OWNER miami_owner;" >/dev/null
ok "database miami"

# The `miami_app` and `miami_feature_compute` roles are created inside Alembic 0001,
# so they don't need to be provisioned here.

# ---------- 7. Env files ----------
step "Ensuring env files exist"
if [[ ! -f "${REPO_ROOT}/.env" ]]; then
  cp "${REPO_ROOT}/.env.example" "${REPO_ROOT}/.env"
  ok "created .env from .env.example"
else
  ok ".env already present (leaving as-is)"
fi
# Point .env at the native brew postgres port (5432, not the docker-compose 5433).
if grep -q "localhost:5433" "${REPO_ROOT}/.env"; then
  sed -i.bak 's/localhost:5433/localhost:5432/g' "${REPO_ROOT}/.env"
  rm -f "${REPO_ROOT}/.env.bak"
  ok "rewrote .env DB URLs 5433 -> 5432"
fi

WEB_ENV="${REPO_ROOT}/apps/web/.env.local"
if [[ ! -f "${WEB_ENV}" ]]; then
  cat > "${WEB_ENV}" <<EOF
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
FASTAPI_SERVICE_TOKEN=dev-service-token-change-in-prod
PIPELINE_REVALIDATE_TOKEN=dev-revalidate-token-change-in-prod
EOF
  ok "created apps/web/.env.local"
else
  ok "apps/web/.env.local already present"
fi

# ---------- 8. Python + Node deps ----------
step "Installing Python workspace dependencies (uv sync)"
uv sync --all-packages --all-extras >/dev/null
ok "uv workspace synced"

step "Installing Next.js dependencies (pnpm install)"
pnpm install --silent
ok "pnpm install complete"

# ---------- 9. Alembic migrations ----------
step "Applying Alembic migrations"
set -a; source "${REPO_ROOT}/.env"; set +a
uv run --package miami-api alembic -c apps/api/alembic.ini upgrade head >/dev/null
ok "migrations applied"

# ---------- 10. Seed + run pipeline once ----------
if [[ "${RUN_PIPELINE}" == "1" ]]; then
  step "Seeding dev catalog"
  uv run --package miami-api python -m miami_api.scripts.seed_catalog_dev >/dev/null
  ok "3 cards + 2 sealed products seeded"

  step "Running the daily pipeline once (dev fixtures)"
  uv run --package miami-api python -m miami_api.worker.daily_pipeline >/dev/null
  ok "pipeline done — 9 score_snapshot rows"
else
  warn "--no-run: skipped catalog seed + pipeline (DB is migrated but empty)"
fi

# ---------- 11. Done ----------
step "All set"
cat <<EOF

  Start the stack in two terminals:

    ${BOLD}FastAPI  :${RESET}
      set -a && source .env && set +a
      uv run --package miami-api uvicorn miami_api.main:app --reload --port 8000

    ${BOLD}Next.js  :${RESET}
      pnpm --filter @miami/web dev --port 3001

  Then open:

    ${CYAN}http://localhost:3001${RESET}                  breakout leaderboard
    ${CYAN}http://localhost:3001/arbitrage${RESET}        grading arbitrage
    ${CYAN}http://localhost:3001/cards/1${RESET}          card detail
    ${CYAN}http://localhost:8000/docs${RESET}             FastAPI OpenAPI (needs bearer token)

  Credentials to flip later (Phase 0 gate):
    PRICECHARTING_API_KEY, POKEMONTCG_API_KEY, EBAY_OAUTH_TOKEN, PSA_API_KEY
    → set in .env, then set MIAMI_DEV_MODE=0

EOF
