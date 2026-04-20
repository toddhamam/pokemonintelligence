# Data Dictionary

Tables owned by `miami_owner`. Read grants differ per role (see migration 0001).

## Catalog (not partitioned)

| Table | Key | Notes |
|---|---|---|
| `set` | `id` | Canonical set. `tcgplayer_group_id` unique. |
| `card` | `id` | Canonical card. Cross-source IDs: `tcgplayer_product_id`, `pricecharting_id`, `pokemontcg_id`, `psa_key`. `embedding vector(384)` reserved for V2 matcher. |
| `sealed_product` | `id` | Booster boxes, ETBs, bundles. |
| `rarity_slot` | `(set_id, slot_name)` | Drives pull-cost math. |
| `match_rule` | `(rule_version, entity_type, entity_id, subject_variant)` | Rules feeding the deterministic matcher. |
| `alias_rule` | `(rule_version, entity_type, entity_id, alias)` | Names/search aliases for catalog UI. |

## Snapshot facts (partitioned monthly on `observed_date`)

All snapshot rows carry `source`, `confidence`, `ingested_at`, `job_run_id`. PKs include
`content_hash` so `ON CONFLICT DO NOTHING` rejects exact duplicates without mutating
prior rows. **Corrections = new rows with later `ingested_at`**, never updates.

| Table | Primary key |
|---|---|
| `price_snapshot_daily` | `(observed_date, card_id, source, content_hash)` |
| `graded_snapshot_daily` | `(observed_date, card_id, source, grade_company, grade, content_hash)` |
| `sealed_snapshot_daily` | `(observed_date, sealed_product_id, source, content_hash)` |
| `listing_flow_snapshot` | `(observed_date, entity_type, entity_id, subject_variant)` |
| `population_snapshot` | `(observed_date, card_id, grade_company)` |
| `retail_stock_snapshot` | `(observed_date, id)` |

## Match split

| Table | Partition | Reason |
|---|---|---|
| `listing_identity` | not partitioned (small, mutable) | One row per `(source, source_listing_id)`. Upserted daily — stores `first_seen_at`, `last_seen_at`, latest decision/rule. |
| `match_observation` | monthly by `observed_date` | One row per listing per day. Append-only. Carries `features_blob_key` to Vercel Blob; DB holds only the pointer + denormalized detected fields. Retention: matched=∞, ambiguous=180d, rejected=90d. |

## Derived snapshots (partitioned by `as_of_date`)

| Table | Primary key |
|---|---|
| `feature_snapshot` | `(as_of_date, entity_type, entity_id, subject_variant, feature_set_version)` |
| `score_snapshot` | `(as_of_date, entity_type, entity_id, subject_variant, formula_version)` |

`score_snapshot.retrospective_validation_score` is populated ONLY by retrospective
runs. Live `score()` NEVER reads it (AST check enforces).

## Materialized views

| View | Refresh trigger |
|---|---|
| `mv_latest_prices` | end of daily pipeline |
| `mv_latest_scores` | end of daily pipeline |

Clients (rankings endpoints) read only from `mv_latest_scores`. Backtest code NEVER
reads materialized views — it queries the partitioned source tables with explicit
`as_of_date` bounds.

## SECURITY DEFINER as-of functions

The `miami_feature_compute` role has EXECUTE on these and no SELECT on base tables:

- `price_snapshot_asof(p_as_of_date date)`
- `graded_snapshot_asof(p_as_of_date date)`
- `sealed_snapshot_asof(p_as_of_date date)`
- `listing_flow_asof(p_as_of_date date)`
- `population_snapshot_asof(p_as_of_date date)`
- `retail_stock_asof(p_as_of_date date)`

Body is `WHERE observed_date <= p_as_of_date AND ingested_at <= p_as_of_date + interval '12 hours'`.
