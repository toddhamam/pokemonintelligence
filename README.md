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

```bash
# 1. Tooling
brew install uv pnpm
# requires Python 3.13 and Node 20 LTS

# 2. Install deps
uv sync
pnpm install

# 3. Copy env (MIAMI_DEV_MODE=1 uses fixtures — no credentials required)
cp .env.example .env

# 4. Start Postgres (pg_partman + pgvector preinstalled)
docker compose -f docker-compose.dev.yml up -d

# 5. Apply migrations + seed a tiny catalog
uv run --package miami-api alembic -c apps/api/alembic.ini upgrade head
uv run --package miami-api python -m miami_api.scripts.seed_catalog_dev

# 6. Run the daily pipeline once against fixtures
uv run --package miami-api python -m miami_api.worker.daily_pipeline

# 7. Start API + web
uv run --package miami-api uvicorn miami_api.main:app --reload --port 8000 &
pnpm dev
# open http://localhost:3000
```

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
