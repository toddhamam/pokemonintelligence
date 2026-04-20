"""mv_latest_scores: surface ebay_input_weight + trailing_cross_source_agreement.

The analytics router's /v1/cards/{id}/confidence endpoint projects these two columns
as confidence components. They exist on score_snapshot but were missing from the
materialized view, so the endpoint 500'd. This migration rebuilds the view.

Revision ID: 0002_mv_scores_extras
Revises: 0001_initial
Create Date: 2026-04-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_mv_scores_extras"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_latest_scores")
    op.execute("""
        CREATE MATERIALIZED VIEW mv_latest_scores AS
          SELECT DISTINCT ON (entity_type, entity_id, subject_variant)
            entity_type, entity_id, subject_variant, as_of_date,
            breakout_score, arbitrage_score, long_term_score,
            confidence_raw, confidence_label,
            ebay_input_weight, trailing_cross_source_agreement,
            recommendation_label, explanations
          FROM score_snapshot
          ORDER BY entity_type, entity_id, subject_variant, as_of_date DESC;
        CREATE UNIQUE INDEX ux_mv_latest_scores
          ON mv_latest_scores (entity_type, entity_id, subject_variant);
    """)
    op.execute("GRANT SELECT ON mv_latest_scores TO miami_app")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_latest_scores")
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
    op.execute("GRANT SELECT ON mv_latest_scores TO miami_app")
