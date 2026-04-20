# Architecture

One-pager summarizing what ships; the definitive plan lives in
`/Users/toddhamam/.claude/plans/ticklish-hopping-snail.md`.

## Invariants (non-negotiable)

1. **Transaction truth vs listing-flow inference are never averaged.** PriceCharting
   and Pokémon TCG current prices feed `price_snapshot_daily` / `graded_snapshot_daily` /
   `sealed_snapshot_daily`. eBay active-listing snapshots feed `listing_flow_snapshot` and
   the split `listing_identity` + `match_observation`. Features and scores keep them
   in separate columns.
2. **PIT is enforced by the database.** Feature code runs under `miami_feature_compute`,
   which has NO SELECT on base snapshot tables and EXECUTE only on SECURITY DEFINER
   `*_asof(p_as_of_date date)` functions. A shortcut query fails at the DB layer.
3. **Confidence cap lives in code.** `score()` clamps `confidence_label` to Medium when
   eBay-input-weight > 0.4 AND trailing_cross_source_agreement is false. The AST check
   `test_no_forward_reads.py` asserts `score()` never reads `retrospective_validation_score`.
4. **Formulas are Git-canonical.** YAMLs in `packages/scoring/src/miami_scoring/formulas/`
   are mirrored into `scoring_formula` with a content_hash; CI asserts no drift.
5. **Insert-only with content_hash.** No snapshot row ever mutates; corrections
   become new rows with later `ingested_at`. Materialized views provide "latest" reads.
6. **Match split.** `listing_identity` (mutable, not partitioned) + `match_observation`
   (append-only, partitioned monthly by `observed_date`).

## Flow (daily)

```
Vercel Cron → FastAPI webhook → Python worker
  ├─ collectors: PriceCharting (raw + graded), Pokémon TCG, eBay, PSA, Pokemon Center
  ├─ build_features(today)   [via *_asof SECURITY DEFINER funcs only]
  ├─ score() per feature row → score_snapshot
  ├─ REFRESH MATERIALIZED VIEW mv_latest_prices, mv_latest_scores
  └─ POST /api/revalidate (Next.js) → revalidateTag(tag, "max")
```

## Topology

- **Python API + worker** on Fly.io, public HTTPS, mandatory `Authorization: Bearer`.
  No anonymous endpoints.
- **Next.js** on Vercel. Server components fetch FastAPI with the service token
  injected from `process.env.FASTAPI_SERVICE_TOKEN`. Clerk gates user-scoped
  actions; Cache Components with `cacheTag` on reads.
- **Postgres (Neon paid tier)** with native monthly partitioning on all snapshot
  tables. pgvector loaded-but-unused (V2 matcher path). Three roles:
  `miami_owner` (DDL), `miami_app` (reads + user-scoped writes), `miami_feature_compute`
  (executes `*_asof` only).

## What is NOT built in v1

See plan §non-goals. Briefly: no deep historical price data; no ML matcher; no Redis;
no auto buy/sell; no multi-tenancy; Vercel Marketplace Insights is restricted and
not in scope.
