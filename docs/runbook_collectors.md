# Runbook — Collectors

## Dev mode (default)

With `MIAMI_DEV_MODE=1`, every collector returns a small hand-written fixture payload.
No credentials are required and no external HTTP calls are made. The daily pipeline
is fully exercisable end-to-end against docker-compose Postgres.

## Live credentials

Set all four before flipping `MIAMI_DEV_MODE=0`:

| Source | Env var | Notes |
|---|---|---|
| PriceCharting | `PRICECHARTING_API_KEY` | Paid subscription required. API returns current values only — no historical backfill available. |
| Pokémon TCG | `POKEMONTCG_API_KEY` | Free tier. Raw-card current-price anchor only. Rate-limited. |
| eBay Browse | `EBAY_OAUTH_TOKEN` | Production application approval is the long pole — submit Week 1. Live listings only; Marketplace Insights is restricted. |
| PSA | `PSA_API_KEY` | Free keys via psacard.com/publicapi. |

## Recovery

- **Collector errors** are written to `job_runs.error_text` with `status='error'`. Rerun
  with the same `as_of_date` — collectors are idempotent on content hash.
- **Rate-limit exhaustion** on eBay or Pokémon TCG: the collector backs off with
  tenacity retry. If the job times out, the partition has at minimum whatever rows
  succeeded before the failure. Rerun picks up the rest.
- **Pokemon Center blocks** (anti-bot): fall back to hourly cadence with jitter;
  accept gaps in `retail_stock_snapshot`. Missing observations are documented as
  limitations in the card detail page.

## Adding a new source

1. Create `packages/collectors/src/miami_collectors/<source>.py`.
2. Subclass `BaseCollector`, implement `fetch()` and `parse()`.
3. Add a dev fixture.
4. Declare the source in the daily pipeline's collector list.
5. Bump `feature_set_version` if the new source changes feature inputs.
