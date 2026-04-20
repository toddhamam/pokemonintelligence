# Miami — Pokemon Market Intelligence

Daily decision engine for the Pokemon card & sealed market. Combines transaction-truth pricing, eBay listing-flow inference, raw→PSA-10 grading EV, and a first-class confidence layer. See `/Users/toddhamam/.claude/plans/ticklish-hopping-snail.md` for the build plan.

## Stack

- **Backend**: Python 3.13 + FastAPI + Polars + SQLAlchemy 2.0 + Alembic
- **Frontend**: Next.js 16 App Router + Clerk + Cache Components
- **Database**: Postgres 16 (Neon in prod) with `pg_partman` + `pgvector`
- **Hosting**: Fly.io for FastAPI + worker, Vercel for Next.js

## Monorepo layout

```
apps/
  web/           Next.js frontend
  api/           FastAPI read API + worker entry points + Alembic
packages/
  common/        logging, settings, db session, retry, time utils
  domain/        SQLAlchemy + Pydantic models
  collectors/    per-source ingestion
  matching/      deterministic matcher
  features/      feature engine (PIT-enforced)
  scoring/       formula YAML + score() + replay()
docs/            architecture, data dictionary, formulas, runbooks
```

## Quickstart (dev)

One command brings a fresh clone all the way up — installs every dependency,
provisions Postgres + roles, runs migrations, seeds the dev catalog, and
executes the daily pipeline once so the dashboard has data:

```bash
./scripts/setup.sh
```

Idempotent — re-run anytime to reapply migrations or refresh dev state.
Pass `--no-run` to skip catalog seeding + pipeline (useful for CI).

Then start the two dev servers (in separate terminals):

```bash
# FastAPI
set -a && source .env && set +a
uv run --package miami-api uvicorn miami_api.main:app --reload --port 8000

# Next.js
pnpm --filter @miami/web dev --port 3001
```

Open http://localhost:3001 — breakout leaderboard with live scored data.

**What the setup script does** (each step idempotent):

1. Installs `uv`, `node@20`, `pnpm`, `postgresql@17`, `pgvector` via Homebrew if missing.
2. Starts `postgresql@17` and waits for it to accept connections.
3. Creates the `miami_owner` superuser and `miami` database if they don't exist.
4. Copies `.env.example → .env` (preserving any existing `.env`) and patches
   the DB URLs to `:5432` (native brew port, not the docker-compose `:5433`).
5. Creates `apps/web/.env.local` with dev tokens for Next.js.
6. `uv sync --all-packages --all-extras` + `pnpm install`.
7. `alembic upgrade head` — runs migrations 0001 + 0002 against your local DB.
8. Seeds 3 cards + 2 sealed products and runs the daily pipeline once against
   fixtures, producing 9 feature rows + 9 score rows ready for the UI.

**If you prefer docker-compose** — `docker-compose.dev.yml` ships Postgres 16
with `pg_partman` preloaded. Flip `.env` DB URLs back to `:5433` if you use it.

## CI checks

- `ruff` + `mypy`
- `pytest` — matcher precision/recall, PIT safety, confidence cap, no-forward-reads AST check
- `alembic upgrade head` against ephemeral Postgres
- `openapi-typescript` diff (no drift between FastAPI and generated TS client)
- `next build`
- `scoring_formula` content-hash verification
- `as_of` grep enforcement

## Provisioning checklist (plan Phase 0)

Manual actions outside this repo:

- [ ] Neon Postgres project (paid tier) via Vercel Marketplace
- [ ] Fly.io app for FastAPI + worker
- [ ] Clerk project
- [ ] Sentry projects (API + Web)
- [ ] Vercel Blob store
- [ ] Resend account
- [ ] **Credential gate** — Phase 2 blocked until:
  - [ ] PriceCharting paid API key
  - [ ] Pokémon TCG API key
  - [ ] eBay Browse API production token
  - [ ] PSA public API key
