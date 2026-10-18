"""initial_migration

Creates all four tables for the Market Analysis MVP Phase 1:
  - holdings
  - analysis_results
  - recommendations
  - user_settings

Revision ID: 885329e7ee93
Revises:
Create Date: 2026-10-18 20:54:20.643550

Requirements: 10.1, 10.2, 10.3
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "885329e7ee93"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # user_settings — must exist before it can be referenced by holdings
    # (no FK in the ORM currently, but created first for logical ordering)
    # ------------------------------------------------------------------
    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("daily_investment", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )

    # ------------------------------------------------------------------
    # holdings
    # ------------------------------------------------------------------
    op.create_table(
        "holdings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("buy_price", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_holdings_user_id", "holdings", ["user_id"])
    op.create_index("ix_holdings_symbol", "holdings", ["symbol"])
    op.create_index(
        "ix_holdings_user_id_symbol",
        "holdings",
        ["user_id", "symbol"],
    )

    # ------------------------------------------------------------------
    # analysis_results  (Requirements 10.2, 10.3)
    # ------------------------------------------------------------------
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("metrics_json", sa.String(), nullable=False),
        sa.Column("trend_json", sa.String(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=False),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("run_timestamp", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_results_symbol", "analysis_results", ["symbol"])
    op.create_index(
        "ix_analysis_results_run_timestamp",
        "analysis_results",
        ["run_timestamp"],
    )

    # ------------------------------------------------------------------
    # recommendations  (Requirements 10.2, 10.3)
    # ------------------------------------------------------------------
    op.create_table(
        "recommendations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.String(), nullable=False),
        sa.Column("run_timestamp", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommendations_user_id", "recommendations", ["user_id"])
    op.create_index(
        "ix_recommendations_run_timestamp",
        "recommendations",
        ["run_timestamp"],
    )
    op.create_index(
        "ix_recommendations_user_id_run_timestamp",
        "recommendations",
        ["user_id", "run_timestamp"],
    )


def downgrade() -> None:
    # Drop in reverse creation order to respect any implicit dependencies.
    op.drop_index("ix_recommendations_user_id_run_timestamp", "recommendations")
    op.drop_index("ix_recommendations_run_timestamp", "recommendations")
    op.drop_index("ix_recommendations_user_id", "recommendations")
    op.drop_table("recommendations")

    op.drop_index("ix_analysis_results_run_timestamp", "analysis_results")
    op.drop_index("ix_analysis_results_symbol", "analysis_results")
    op.drop_table("analysis_results")

    op.drop_index("ix_holdings_user_id_symbol", "holdings")
    op.drop_index("ix_holdings_symbol", "holdings")
    op.drop_index("ix_holdings_user_id", "holdings")
    op.drop_table("holdings")

    op.drop_table("user_settings")
