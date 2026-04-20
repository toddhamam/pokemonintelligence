# Changelog

## [Unreleased] — 2026-04-20

Initial commit of the Miami Pokemon Market Intelligence platform. Ships the
complete v1a scaffold described in the plan at
`/Users/toddhamam/.claude/plans/ticklish-hopping-snail.md`, survives three rounds
of Codex review, and runs end-to-end locally against a native Postgres 17 +
pgvector install.

### Added

**Infrastructure + scaffolding**
- pnpm + uv polyglot monorepo (Python workers/API + Next.js web)
- `docker-compose.dev.yml` as the containerized option; native `postgresql@17 +
  pgvector` via Homebrew as the documented alternative
- `.env.example` with every required var; `apps/web/.env.local` for Next-specific
  tokens (gitignored)
- GitHub Actions CI: ruff, pytest, alembic migrate-against-ephemeral-pg,
  openapi-typescript diff check, next build, `as_of` grep enforcement, and
  scoring-formula content-hash verification

**Database**
- `apps/api/alembic/versions/0001_initial_partitioned.py` — full schema with
  monthly native partitioning on all snapshot tables, `pgvector` enabled, three
  Postgres roles (`miami_owner`, `miami_app`, `miami_feature_compute`)
- SECURITY DEFINER `*_asof(p_as_of_date date)` table-valued functions; the
  `miami_feature_compute` role has EXECUTE on the functions and NO SELECT on the
  base snapshot tables — so a buggy feature job fails at the DB layer, not
  silently with lookahead
- `listing_identity` (mutable, not partitioned) + `match_observation`
  (append-only, partitioned monthly) — resolves the Codex v2 finding that unique
  constraints on partitioned tables must include the partition key
- `0002_mv_latest_scores_extras.py` — rebuilds `mv_latest_scores` with
  `ebay_input_weight` and `trailing_cross_source_agreement` so
  `/v1/cards/{id}/confidence` can project them

**Matcher**
- `packages/matching` — deterministic three-valued matcher (matched / ambiguous /
  rejected), card-number-mismatch hard reject, Japanese rejection, grade-company
  consistency
- 49-row hand-labeled eBay title fixture with a CI gate at
  **precision ≥ 0.90, recall ≥ 0.70**

**Collectors**
- PriceCharting raw + graded, Pokémon TCG (raw-card current prices only per
  Codex v2 finding), eBay Browse (active listings only; "sold" is inferred from
  snapshot differencing per Codex v2), PSA population, Pokemon Center stock
- Every collector insert-only with `ON CONFLICT DO NOTHING` on a `content_hash`
  composite PK (except PSA + Pokemon Center, which opt out via
  `has_content_hash = False` since those tables don't carry that column)
- Dev-mode fallback (`MIAMI_DEV_MODE=1`) returns hand-written fixture payloads so
  the full pipeline runs without any external credentials
- Vercel Blob archive with local filesystem fallback; archive keys carry a uuid4
  suffix so two `pricecharting` collectors in the same second don't collide

**Feature + scoring engine**
- `packages/features/build.py` — reads only via the SECURITY DEFINER `*_asof`
  functions; emits one `feature_snapshot` per
  `(entity_type, entity_id, subject_variant, as_of_date, feature_set_version)`
- `packages/scoring/engine.py` — `score()` pure function with the
  confidence-cap clamp enforced **in code**, not just YAML: if
  `ebay_input_weight > 0.4` and `trailing_cross_source_agreement = false`, the
  label is pulled down to Medium regardless of the raw score
- Formula YAMLs in `packages/scoring/src/miami_scoring/formulas/` are
  Git-canonical; `verify_formula_hashes.py` mirrors them into `scoring_formula`
  with `git_sha` + `content_hash` and CI asserts no drift
- `replay()` and `retrospective_validate()` as the two reproducibility
  entrypoints; `retrospective_validate()` runs under `session_owner` because a
  backtest is not live scoring (Codex v3 finding #2)
- `retrospective_validation_score` is a separate `score_snapshot` column
  populated only by backtests; a pytest AST walker ensures live `score()` never
  references it

**FastAPI**
- `apps/api/src/miami_api/` with bearer-token middleware global dependency,
  slowapi rate limits, CORS
- Routers: `catalog`, `history`, `rankings`, `analytics`, `alerts` — all behind
  `Authorization: Bearer <FASTAPI_SERVICE_TOKEN>`; alerts additionally require
  `X-Clerk-User-Id`
- Daily pipeline entrypoint `miami_api.worker.daily_pipeline` runs
  collectors → `build_features` → `score()` → view refresh → POST to Next.js
  `/api/revalidate`

**Next.js 16**
- `apps/web/` with App Router + Cache Components + Clerk (Core 3)
- Pages: `/` (breakout leaderboard), `/arbitrage`, `/alerts`, `/cards/[id]`
  (dual-source price chart via Recharts with a honest "history: N days"
  indicator)
- `ClerkProvider` mounts conditionally based on `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`,
  so the dashboard is browsable without a Clerk account
- `/api/revalidate` route uses the Next.js 16 two-arg `revalidateTag(tag, "max")`
  API — single-arg is deprecated
- Cross-language contract enforced by `openapi-typescript`; CI fails on any
  `git diff` to `apps/web/src/generated/api.ts`

### Fixed

Three rounds of Codex review, every finding addressed:

**Round 1 — blockers**
- TCGplayer direct API removed from v1 (not granting new access); PriceCharting
  + Pokémon TCG picked up the transaction-truth slot
- eBay Browse scope corrected — no claim of sold/ended flow; market-state is
  snapshot-differenced inventory disappearance

**Round 2 — blockers**
- PriceCharting has no historical API — Phase 2 accumulates forward only,
  Week 8 backtest ship-gate removed, v1b now publishes a "limited-history
  preview" backtest honest about window depth
- Fly auth topology fixed — public HTTPS FastAPI + bearer token + rate limit,
  no private-networking contradiction
- `match_attempt` split into `listing_identity` + `match_observation`
- `trailing_cross_source_agreement` uses trailing data only; forward validation
  moved to a separate retrospective field
- PIT views replaced with SECURITY DEFINER table-valued functions
- Pokémon TCG demoted to raw-card current-price anchor only

**Round 3 — runtime bugs found by actually running the code**
- CI `uv sync --all-packages` missed the `dev` extras (ruff/pytest/mypy); fixed
  with `--all-extras`
- `BaseCollector` added `content_hash` unconditionally; PSA + Pokemon Center
  tables don't have that column — added `has_content_hash` class flag
- Blob archive key collided when two `pricecharting` collectors ran in the
  same second; added uuid4 nonce suffix
- Confidence-cap test fixture produced pre-cap Low so the clamp never fired;
  rebuilt with inputs that reach High pre-cap so the clamp has something to do

**Round 4 — the pass-the-typecheck round**
- `mv_latest_scores` was missing `ebay_input_weight` + `trailing_cross_source_agreement`
  columns that `/v1/cards/{id}/confidence` queries (migration 0002 fixes this)
- `retrospective_validate` was opening a `session_feature_compute` that's denied
  on raw snapshots — switched to `session_owner` since backtest is explicitly
  not live scoring
- Unused `@ts-expect-error` on Next 16's `RequestInit.next` — removed; Next 16
  types now accept it natively
- Dashboard linked to `/arbitrage` + `/alerts` which 404'd; shipped both
- Ruff cleanup: global `B008` ignore (FastAPI `Query(...)` default is correct),
  `RUF015`, `RUF012`, `RUF002`, `RUF005` fixed by hand

### Verified

- All 7 non-DB pytest tests green: matcher precision/recall, replay hash
  stability, confidence-cap enforcement (×3), no-forward-reads AST check
- `ruff check .` clean; `ruff format --check .` clean (50 files)
- `pnpm typecheck` clean
- Full daily pipeline runs end-to-end against dev fixtures: 23 snapshot rows
  ingested, 9 feature rows built, 9 scored, materialized views refreshed
- Dashboard http://localhost:3001 renders three real cards with breakout scores
  + confidence badges
- Card detail http://localhost:3001/cards/1 renders the dual-source price chart
- All listed endpoints respond correctly, including
  `/v1/cards/1/confidence` that Codex flagged as broken

### Known limitations

- No external API credentials are acquired — `MIAMI_DEV_MODE=1` is the default
  in `.env.example`
- No deep historical price data available from any v1 source; real backtests
  require days of wall-clock time after Phase 2 go-live (v1b at Week 12)
- Clerk is gated behind env vars; without keys the dashboard is browsable but
  alerts CRUD returns informational placeholder
- `apps/web/middleware.ts` kept at classic name per Clerk Core 3 docs; Next.js
  16 guidance is `proxy.ts` — the filename will migrate when Clerk's examples do
