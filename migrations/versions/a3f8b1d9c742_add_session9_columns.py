"""add session9 columns — variant, mechanism, disconfirming on theses; kpi_family on claims

Revision ID: a3f8b1d9c742
Revises: e2613a6c2ebb
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'a3f8b1d9c742'
down_revision: Union[str, Sequence[str]] = 'e2613a6c2ebb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Static KPI → family mapping for backfill
_KPI_FAMILY: dict[str, str] = {
    "rpo_growth": "leading",
    "deferred_rev_growth": "leading",
    "nrr": "leading",
    "backlog": "leading",
    "book_to_bill": "leading",
    "revenue_growth": "lagging",
    "subscription_mix": "lagging",
    "gross_margin": "efficiency",
    "operating_margin": "efficiency",
    "r_and_d_intensity": "efficiency",
    "sm_revenue": "efficiency",
    "inventory_days": "efficiency",
    "capex_intensity": "efficiency",
    "rule_of_40": "quality",
    "fcf_margin": "quality",
    "sbc_revenue": "quality",
    "fcf_yield": "quality",
    "roe": "quality",
    "net_debt_ebitda": "quality",
}


def upgrade() -> None:
    # --- theses table ---
    op.add_column('theses', sa.Column('variant', sa.Text(), nullable=True))
    op.add_column('theses', sa.Column('mechanism', sa.Text(), nullable=True))
    op.add_column('theses', sa.Column('disconfirming', JSONB(), nullable=True))

    # Backfill disconfirming → empty array for existing rows
    op.execute("UPDATE theses SET disconfirming = '[]'::jsonb WHERE disconfirming IS NULL")

    # --- claims table ---
    op.add_column('claims', sa.Column('kpi_family', sa.String(20), nullable=True))

    # Backfill kpi_family from static KPI→family map
    for kpi_id, family in _KPI_FAMILY.items():
        op.execute(
            sa.text(
                "UPDATE claims SET kpi_family = :family "
                "WHERE kpi_id = :kpi_id AND kpi_family IS NULL"
            ).bindparams(family=family, kpi_id=kpi_id)
        )

    # Catch-all: any unmapped KPIs default to 'lagging'
    op.execute("UPDATE claims SET kpi_family = 'lagging' WHERE kpi_family IS NULL")

    # Make non-nullable with server default
    op.alter_column('claims', 'kpi_family', nullable=False, server_default='lagging')


def downgrade() -> None:
    op.drop_column('claims', 'kpi_family')
    op.drop_column('theses', 'disconfirming')
    op.drop_column('theses', 'mechanism')
    op.drop_column('theses', 'variant')
