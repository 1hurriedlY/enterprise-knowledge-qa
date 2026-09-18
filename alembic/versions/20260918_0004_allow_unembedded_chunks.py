"""allow chunks before vectorization

Revision ID: 20260918_0004
Revises: 20260918_0003
Create Date: 2026-09-18
"""

import sqlalchemy as sa

from alembic import op

revision = "20260918_0004"
down_revision = "20260918_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("chunks", "embedding_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM chunks WHERE embedding_id IS NULL")
    op.alter_column("chunks", "embedding_id", existing_type=sa.UUID(), nullable=False)
