"""Initial schema: partitioned snapshots, role separation, SECURITY DEFINER asof functions.

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------- extensions ----------
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ---------- roles (idempotent: CREATE ROLE errors if exists, guard via DO block) ----------
    op.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'miami_app') THEN
            CREATE ROLE miami_app LOGIN PASSWORD 'miami_app';
          END IF;
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'miami_feature_compute') THEN
            CREATE ROLE miami_feature_compute LOGIN PASSWORD 'miami_feature_compute';
          END IF;
        END $$;
    """)

    # ---------- master catalog (not partitioned) ----------
    op.execute("""
        CREATE TABLE set (
          id BIGSERIAL PRIMARY KEY,
          tcgplayer_group_id INT UNIQUE,
          name TEXT NOT NULL,
          series TEXT,
          language TEXT NOT NULL DEFAULT 'en',
          release_date DATE,
          set_type TEXT,
          has_booster_box BOOLEAN NOT NULL DEFAULT TRUE,
          has_special_product_only BOOLEAN NOT NULL DEFAULT FALSE,
          msrp_pack NUMERIC(10, 2),
          msrp_etb NUMERIC(10, 2),
          msrp_booster_box NUMERIC(10, 2),
          pack_count_per_box INT,
          cards_per_pack INT,
          slot_distribution_json JSONB,
          official_pack_odds_source TEXT,
          retired_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_set_language_release ON set (language, release_date);
    """)

    op.execute("""
        CREATE TABLE card (
          id BIGSERIAL PRIMARY KEY,
          set_id BIGINT NOT NULL REFERENCES set (id),
          tcgplayer_product_id INT UNIQUE,
          pricecharting_id TEXT UNIQUE,
          pokemontcg_id TEXT UNIQUE,
          psa_key TEXT UNIQUE,
          name TEXT NOT NULL,
          card_number TEXT NOT NULL,
          rarity TEXT,
          sub_rarity TEXT,
          pokemon_name TEXT,
          language TEXT NOT NULL DEFAULT 'en',
          art_variant TEXT,
          illustrator TEXT,
          is_promo BOOLEAN NOT NULL DEFAULT FALSE,
          is_playable BOOLEAN NOT NULL DEFAULT FALSE,
          is_full_art BOOLEAN NOT NULL DEFAULT FALSE,
          is_alt_art BOOLEAN NOT NULL DEFAULT FALSE,
          rarity_slot_id BIGINT,
          condition_scope_default TEXT,
          aliases TEXT[] NOT NULL DEFAULT '{}',
          embedding vector(384),
          retired_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (set_id, card_number)
        );
        CREATE INDEX ix_card_pokemon_name ON card (pokemon_name);
        CREATE INDEX ix_card_aliases ON card USING GIN (aliases);
    """)

    op.execute("""
        CREATE TABLE sealed_product (
          id BIGSERIAL PRIMARY KEY,
          set_id BIGINT NOT NULL REFERENCES set (id),
          tcgplayer_product_id INT UNIQUE,
          product_name TEXT NOT NULL,
          product_type TEXT NOT NULL,
          msrp NUMERIC(10, 2),
          sku_aliases TEXT[] NOT NULL DEFAULT '{}',
          official_url TEXT,
          exclusive_type TEXT,
          retired_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_sealed_product_set ON sealed_product (set_id);
        CREATE INDEX ix_sealed_product_sku_aliases ON sealed_product USING GIN (sku_aliases);
    """)

    op.execute("""
        CREATE TABLE rarity_slot (
          id BIGSERIAL PRIMARY KEY,
          set_id BIGINT NOT NULL REFERENCES set (id),
          slot_name TEXT NOT NULL,
          slot_probability DOUBLE PRECISION NOT NULL,
          cards_in_slot INT NOT NULL,
          UNIQUE (set_id, slot_name)
        );
    """)

    # Versioned matching rules.
    op.execute("""
        CREATE TABLE match_rule (
          id BIGSERIAL PRIMARY KEY,
          rule_version TEXT NOT NULL,
          entity_type TEXT NOT NULL CHECK (entity_type IN ('card', 'sealed_product')),
          entity_id BIGINT NOT NULL,
          subject_variant TEXT NOT NULL
              CHECK (subject_variant IN ('raw', 'psa10', 'psa9', 'psa_other', 'sealed')),
          include_terms TEXT[] NOT NULL DEFAULT '{}',
          exclude_terms TEXT[] NOT NULL DEFAULT '{}',
          regex_patterns TEXT[] NOT NULL DEFAULT '{}',
          min_confidence DOUBLE PRECISION NOT NULL DEFAULT 0.6,
          applied_from TIMESTAMPTZ NOT NULL DEFAULT now(),
          applied_to TIMESTAMPTZ,
          UNIQUE (rule_version, entity_type, entity_id, subject_variant)
        );
        CREATE INDEX ix_match_rule_version ON match_rule (rule_version);
    """)

    # Alias rules used by the catalog search (kept separate from match_rule so
    # catalog-search changes don't force a new matcher version).
    op.execute("""
        CREATE TABLE alias_rule (
          id BIGSERIAL PRIMARY KEY,
          rule_version TEXT NOT NULL,
          entity_type TEXT NOT NULL,
          entity_id BIGINT NOT NULL,
          alias TEXT NOT NULL,
          UNIQUE (rule_version, entity_type, entity_id, alias)
        );
    """)

    # ---------- snapshot facts (all partitioned monthly on observed_date) ----------
    # Native declarative partitioning. A helper (see 0002 or create_partitions.py)
    # creates rolling monthly children. content_hash is in every PK so insert-only
    # ON CONFLICT DO NOTHING rejects exact duplicates without mutating prior rows.
    op.execute("""
        CREATE TABLE price_snapshot_daily (
          card_id BIGINT NOT NULL REFERENCES card (id),
          observed_date DATE NOT NULL,
          source TEXT NOT NULL,
          source_record_id TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          market_price NUMERIC(12, 2),
          low_price NUMERIC(12, 2),
          mid_price NUMERIC(12, 2),
          high_price NUMERIC(12, 2),
          near_mint_price NUMERIC(12, 2),
          modeled_price NUMERIC(12, 2),
          currency CHAR(3) NOT NULL DEFAULT 'USD',
          confidence DOUBLE PRECISION NOT NULL,
          ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          job_run_id BIGINT,
          correction_of_card_id BIGINT,
          correction_of_observed_date DATE,
          correction_of_source TEXT,
          correction_of_hash TEXT,
          PRIMARY KEY (observed_date, card_id, source, content_hash)
        ) PARTITION BY RANGE (observed_date);
    """)

    op.execute("""
        CREATE TABLE graded_snapshot_daily (
          card_id BIGINT NOT NULL REFERENCES card (id),
          observed_date DATE NOT NULL,
          source TEXT NOT NULL,
          grade_company TEXT NOT NULL,
          grade TEXT NOT NULL,
          source_record_id TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          market_price NUMERIC(12, 2),
          low_price NUMERIC(12, 2),
          high_price NUMERIC(12, 2),
          modeled_price NUMERIC(12, 2),
          currency CHAR(3) NOT NULL DEFAULT 'USD',
          confidence DOUBLE PRECISION NOT NULL,
          ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          job_run_id BIGINT,
          PRIMARY KEY (observed_date, card_id, source, grade_company, grade, content_hash)
        ) PARTITION BY RANGE (observed_date);
    """)

    op.execute("""
        CREATE TABLE sealed_snapshot_daily (
          sealed_product_id BIGINT NOT NULL REFERENCES sealed_product (id),
          observed_date DATE NOT NULL,
          source TEXT NOT NULL,
          source_record_id TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          market_price NUMERIC(12, 2),
          low_price NUMERIC(12, 2),
          high_price NUMERIC(12, 2),
          modeled_price NUMERIC(12, 2),
          currency CHAR(3) NOT NULL DEFAULT 'USD',
          confidence DOUBLE PRECISION NOT NULL,
          ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          job_run_id BIGINT,
          PRIMARY KEY (observed_date, sealed_product_id, source, content_hash)
        ) PARTITION BY RANGE (observed_date);
    """)

    op.execute("""
        CREATE TABLE listing_flow_snapshot (
          entity_type TEXT NOT NULL CHECK (entity_type IN ('card', 'sealed_product')),
          entity_id BIGINT NOT NULL,
          subject_variant TEXT NOT NULL
              CHECK (subject_variant IN ('raw', 'psa10', 'psa9', 'psa_other', 'sealed')),
          observed_date DATE NOT NULL,
          active_listings INT NOT NULL DEFAULT 0,
          new_listings INT NOT NULL DEFAULT 0,
          estimated_disappeared_count INT NOT NULL DEFAULT 0,
          avg_listing_price NUMERIC(12, 2),
          median_listing_price NUMERIC(12, 2),
          price_band_json JSONB,
          avg_days_active DOUBLE PRECISION,
          overmatch_count INT NOT NULL DEFAULT 0,
          discarded_count INT NOT NULL DEFAULT 0,
          match_rules_version TEXT NOT NULL,
          data_quality_score DOUBLE PRECISION NOT NULL,
          ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          job_run_id BIGINT,
          PRIMARY KEY (observed_date, entity_type, entity_id, subject_variant)
        ) PARTITION BY RANGE (observed_date);
    """)

    op.execute("""
        CREATE TABLE population_snapshot (
          card_id BIGINT NOT NULL REFERENCES card (id),
          observed_date DATE NOT NULL,
          grade_company TEXT NOT NULL,
          total_population INT NOT NULL,
          grade_10_population INT NOT NULL,
          grade_9_population INT NOT NULL,
          ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          job_run_id BIGINT,
          PRIMARY KEY (observed_date, card_id, grade_company)
        ) PARTITION BY RANGE (observed_date);
    """)

    op.execute("""
        CREATE TABLE retail_stock_snapshot (
          id BIGSERIAL,
          sealed_product_id BIGINT NOT NULL REFERENCES sealed_product (id),
          retailer TEXT NOT NULL,
          observed_at TIMESTAMPTZ NOT NULL,
          observed_date DATE NOT NULL,
          in_stock BOOLEAN NOT NULL,
          price NUMERIC(12, 2),
          restock_signal TEXT,
          ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          job_run_id BIGINT,
          PRIMARY KEY (observed_date, id)
        ) PARTITION BY RANGE (observed_date);
    """)

    # ---------- matching: split into identity (mutable) + observation (append-only) ----------
    op.execute("""
        CREATE TABLE listing_identity (
          source TEXT NOT NULL,
          source_listing_id TEXT NOT NULL,
          first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          first_decision TEXT NOT NULL,
          last_decision TEXT NOT NULL,
          latest_rule_version TEXT NOT NULL,
          latest_matched_entity_type TEXT,
          latest_matched_entity_id BIGINT,
          latest_matched_subject_variant TEXT,
          PRIMARY KEY (source, source_listing_id)
        );
        CREATE INDEX ix_listing_identity_last_seen ON listing_identity (last_seen_at);
    """)

    op.execute("""
        CREATE TABLE match_observation (
          source TEXT NOT NULL,
          source_listing_id TEXT NOT NULL,
          observed_date DATE NOT NULL,
          ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          decision TEXT NOT NULL
              CHECK (decision IN ('matched', 'ambiguous', 'rejected')),
          match_confidence DOUBLE PRECISION NOT NULL,
          rule_version TEXT NOT NULL,
          matched_entity_type TEXT,
          matched_entity_id BIGINT,
          matched_subject_variant TEXT,
          detected_set_code TEXT,
          detected_card_number TEXT,
          detected_variant TEXT,
          detected_grade TEXT,
          features_blob_key TEXT NOT NULL,
          job_run_id BIGINT,
          PRIMARY KEY (observed_date, source, source_listing_id)
        ) PARTITION BY RANGE (observed_date);
    """)

    # ---------- derived snapshots ----------
    op.execute("""
        CREATE TABLE feature_snapshot (
          entity_type TEXT NOT NULL CHECK (entity_type IN ('card', 'sealed_product')),
          entity_id BIGINT NOT NULL,
          subject_variant TEXT NOT NULL
              CHECK (subject_variant IN ('raw', 'psa10', 'psa9', 'psa_other', 'sealed')),
          as_of_date DATE NOT NULL,
          feature_set_version TEXT NOT NULL,
          features_json JSONB NOT NULL,
          ebay_input_weight DOUBLE PRECISION NOT NULL DEFAULT 0.0,
          trailing_cross_source_agreement BOOLEAN NOT NULL DEFAULT FALSE,
          computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (as_of_date, entity_type, entity_id, subject_variant, feature_set_version)
        ) PARTITION BY RANGE (as_of_date);
    """)

    op.execute("""
        CREATE TABLE score_snapshot (
          entity_type TEXT NOT NULL CHECK (entity_type IN ('card', 'sealed_product')),
          entity_id BIGINT NOT NULL,
          subject_variant TEXT NOT NULL
              CHECK (subject_variant IN ('raw', 'psa10', 'psa9', 'psa_other', 'sealed')),
          as_of_date DATE NOT NULL,
          formula_version TEXT NOT NULL,
          feature_set_version TEXT NOT NULL,
          inputs_hash TEXT NOT NULL,
          breakout_score DOUBLE PRECISION,
          arbitrage_score DOUBLE PRECISION,
          long_term_score DOUBLE PRECISION,
          confidence_raw DOUBLE PRECISION NOT NULL,
          confidence_label TEXT NOT NULL
              CHECK (confidence_label IN ('High', 'Medium', 'Low', 'Experimental')),
          ebay_input_weight DOUBLE PRECISION NOT NULL DEFAULT 0.0,
          trailing_cross_source_agreement BOOLEAN NOT NULL DEFAULT FALSE,
          recommendation_label TEXT,
          explanations JSONB,
          -- Populated ONLY by backtest/retrospective runs. Live score() NEVER reads this.
          retrospective_validation_score DOUBLE PRECISION,
          computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (as_of_date, entity_type, entity_id, subject_variant, formula_version)
        ) PARTITION BY RANGE (as_of_date);
    """)

    # ---------- scoring formula metadata ----------
    op.execute("""
        CREATE TABLE scoring_formula (
          id BIGSERIAL PRIMARY KEY,
          name TEXT NOT NULL,
          version TEXT NOT NULL,
          git_sha TEXT NOT NULL,
          content_hash TEXT NOT NULL,
          definition_yaml TEXT NOT NULL,
          activated_at TIMESTAMPTZ,
          retired_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          UNIQUE (name, version)
        );
    """)

    # ---------- operational tables ----------
    op.execute("""
        CREATE TABLE job_runs (
          id BIGSERIAL PRIMARY KEY,
          job_name TEXT NOT NULL,
          started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          finished_at TIMESTAMPTZ,
          status TEXT NOT NULL DEFAULT 'running'
              CHECK (status IN ('running', 'success', 'error')),
          rows_in INT,
          rows_out INT,
          error_text TEXT,
          params JSONB
        );
        CREATE INDEX ix_job_runs_job_name_started ON job_runs (job_name, started_at DESC);
    """)

    op.execute("""
        CREATE TABLE payload_archive_index (
          id BIGSERIAL PRIMARY KEY,
          source TEXT NOT NULL,
          fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          blob_key TEXT NOT NULL UNIQUE,
          size_bytes BIGINT,
          request_params JSONB,
          job_run_id BIGINT REFERENCES job_runs (id)
        );
    """)

    op.execute("""
        CREATE TABLE alert (
          id BIGSERIAL PRIMARY KEY,
          user_id TEXT NOT NULL,
          name TEXT NOT NULL,
          rule_json JSONB NOT NULL,
          channel TEXT NOT NULL DEFAULT 'email',
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_fired_at TIMESTAMPTZ,
          active BOOLEAN NOT NULL DEFAULT TRUE
        );
        CREATE INDEX ix_alert_user_id ON alert (user_id);
    """)

    op.execute("""
        CREATE TABLE alert_event (
          id BIGSERIAL PRIMARY KEY,
          alert_id BIGINT NOT NULL REFERENCES alert (id),
          fired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          entity_type TEXT NOT NULL,
          entity_id BIGINT NOT NULL,
          payload JSONB
        );
        CREATE INDEX ix_alert_event_alert_fired ON alert_event (alert_id, fired_at DESC);
    """)

    op.execute("""
        CREATE TABLE backtest_runs (
          id BIGSERIAL PRIMARY KEY,
          started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          finished_at TIMESTAMPTZ,
          formula_version TEXT NOT NULL,
          feature_set_version TEXT NOT NULL,
          params JSONB,
          metrics JSONB,
          notes TEXT
        );
    """)

    # ---------- partitions: create a seed window (prior year + next year) ----------
    # In prod, a cron job rolls forward using create_monthly_partition(). Here we bake
    # a generous default window so tests and dev are unblocked.
    op.execute("""
        CREATE OR REPLACE FUNCTION create_monthly_partition(
          p_parent TEXT,
          p_year INT,
          p_month INT
        ) RETURNS VOID LANGUAGE plpgsql AS $$
        DECLARE
          v_start DATE := make_date(p_year, p_month, 1);
          v_end   DATE := v_start + INTERVAL '1 month';
          v_child TEXT := format('%I_%s%s',
                                 p_parent,
                                 p_year::TEXT,
                                 lpad(p_month::TEXT, 2, '0'));
        BEGIN
          EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
            v_child, p_parent, v_start, v_end
          );
        END $$;
    """)

    # Seed a conservative 24-month window around now.
    op.execute("""
        DO $$
        DECLARE
          v_tbl TEXT;
          v_date DATE;
        BEGIN
          FOR v_tbl IN SELECT unnest(ARRAY[
            'price_snapshot_daily',
            'graded_snapshot_daily',
            'sealed_snapshot_daily',
            'listing_flow_snapshot',
            'population_snapshot',
            'retail_stock_snapshot',
            'match_observation',
            'feature_snapshot',
            'score_snapshot'
          ])
          LOOP
            FOR v_date IN
              SELECT generate_series(
                date_trunc('month', CURRENT_DATE - INTERVAL '12 months'),
                date_trunc('month', CURRENT_DATE + INTERVAL '12 months'),
                INTERVAL '1 month'
              )::date
            LOOP
              PERFORM create_monthly_partition(
                v_tbl,
                EXTRACT(YEAR FROM v_date)::INT,
                EXTRACT(MONTH FROM v_date)::INT
              );
            END LOOP;
          END LOOP;
        END $$;
    """)

    # ---------- SECURITY DEFINER as-of functions ----------
    # These are the ONLY way the feature_compute role can read snapshot data.
    # A 12-hour ingested_at cutoff keeps late-arriving raw rows (e.g. corrections
    # published after the as_of date) out of features for that date.
    op.execute("""
        CREATE OR REPLACE FUNCTION price_snapshot_asof(p_as_of_date DATE)
        RETURNS SETOF price_snapshot_daily
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        AS $$
          SELECT *
          FROM price_snapshot_daily
          WHERE observed_date <= p_as_of_date
            AND ingested_at <= (p_as_of_date + INTERVAL '12 hours');
        $$;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION graded_snapshot_asof(p_as_of_date DATE)
        RETURNS SETOF graded_snapshot_daily
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        AS $$
          SELECT *
          FROM graded_snapshot_daily
          WHERE observed_date <= p_as_of_date
            AND ingested_at <= (p_as_of_date + INTERVAL '12 hours');
        $$;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION sealed_snapshot_asof(p_as_of_date DATE)
        RETURNS SETOF sealed_snapshot_daily
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        AS $$
          SELECT *
          FROM sealed_snapshot_daily
          WHERE observed_date <= p_as_of_date
            AND ingested_at <= (p_as_of_date + INTERVAL '12 hours');
        $$;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION listing_flow_asof(p_as_of_date DATE)
        RETURNS SETOF listing_flow_snapshot
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        AS $$
          SELECT *
          FROM listing_flow_snapshot
          WHERE observed_date <= p_as_of_date
            AND ingested_at <= (p_as_of_date + INTERVAL '12 hours');
        $$;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION population_snapshot_asof(p_as_of_date DATE)
        RETURNS SETOF population_snapshot
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        AS $$
          SELECT *
          FROM population_snapshot
          WHERE observed_date <= p_as_of_date
            AND ingested_at <= (p_as_of_date + INTERVAL '12 hours');
        $$;
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION retail_stock_asof(p_as_of_date DATE)
        RETURNS SETOF retail_stock_snapshot
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        AS $$
          SELECT *
          FROM retail_stock_snapshot
          WHERE observed_date <= p_as_of_date
            AND ingested_at <= (p_as_of_date + INTERVAL '12 hours');
        $$;
    """)

    # ---------- materialized views ----------
    op.execute("""
        CREATE MATERIALIZED VIEW mv_latest_prices AS
          SELECT DISTINCT ON (card_id, source)
            card_id, source, observed_date, market_price, low_price, mid_price,
            high_price, currency, confidence
          FROM price_snapshot_daily
          ORDER BY card_id, source, observed_date DESC, ingested_at DESC;
        CREATE UNIQUE INDEX ux_mv_latest_prices ON mv_latest_prices (card_id, source);
    """)

    op.execute("""
        CREATE MATERIALIZED VIEW mv_latest_scores AS
          SELECT DISTINCT ON (entity_type, entity_id, subject_variant)
            entity_type, entity_id, subject_variant, as_of_date,
            breakout_score, arbitrage_score, long_term_score,
            confidence_raw, confidence_label, recommendation_label, explanations
          FROM score_snapshot
          ORDER BY entity_type, entity_id, subject_variant, as_of_date DESC;
        CREATE UNIQUE INDEX ux_mv_latest_scores
          ON mv_latest_scores (entity_type, entity_id, subject_variant);
    """)

    # ---------- grants (role separation) ----------
    # miami_app: reads + user-scoped writes. No direct access to *_asof (that's for jobs).
    op.execute("""
        GRANT USAGE ON SCHEMA public TO miami_app, miami_feature_compute;
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO miami_app;
        GRANT SELECT ON mv_latest_prices, mv_latest_scores TO miami_app;
        GRANT INSERT, UPDATE, DELETE ON alert, alert_event TO miami_app;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO miami_app;
    """)

    # miami_feature_compute: NO SELECT on snapshot tables. Only EXECUTE on *_asof functions,
    # plus SELECT on the immutable catalog (needed to join features against canonical entities),
    # plus INSERT into feature_snapshot/score_snapshot/job_runs/backtest_runs.
    op.execute("""
        REVOKE ALL ON price_snapshot_daily, graded_snapshot_daily, sealed_snapshot_daily,
                    listing_flow_snapshot, population_snapshot, retail_stock_snapshot
                 FROM miami_feature_compute;
        GRANT SELECT ON set, card, sealed_product, rarity_slot, scoring_formula
              TO miami_feature_compute;
        GRANT SELECT, INSERT, UPDATE ON feature_snapshot, score_snapshot, backtest_runs
              TO miami_feature_compute;
        GRANT SELECT, INSERT, UPDATE ON job_runs TO miami_feature_compute;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO miami_feature_compute;
        GRANT EXECUTE ON FUNCTION
          price_snapshot_asof(DATE),
          graded_snapshot_asof(DATE),
          sealed_snapshot_asof(DATE),
          listing_flow_asof(DATE),
          population_snapshot_asof(DATE),
          retail_stock_asof(DATE)
        TO miami_feature_compute;
    """)

    # Ensure future tables don't accidentally leak SELECT to feature_compute.
    op.execute("""
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
          REVOKE ALL ON TABLES FROM miami_feature_compute;
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_latest_scores")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_latest_prices")
    for fn in (
        "price_snapshot_asof",
        "graded_snapshot_asof",
        "sealed_snapshot_asof",
        "listing_flow_asof",
        "population_snapshot_asof",
        "retail_stock_asof",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}(DATE)")
    op.execute("DROP FUNCTION IF EXISTS create_monthly_partition(TEXT, INT, INT)")
    for tbl in (
        "alert_event",
        "alert",
        "backtest_runs",
        "payload_archive_index",
        "job_runs",
        "scoring_formula",
        "score_snapshot",
        "feature_snapshot",
        "match_observation",
        "listing_identity",
        "retail_stock_snapshot",
        "population_snapshot",
        "listing_flow_snapshot",
        "sealed_snapshot_daily",
        "graded_snapshot_daily",
        "price_snapshot_daily",
        "alias_rule",
        "match_rule",
        "rarity_slot",
        "sealed_product",
        "card",
        "set",
    ):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
