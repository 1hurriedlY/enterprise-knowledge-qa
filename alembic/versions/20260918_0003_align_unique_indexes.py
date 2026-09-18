"""align unique indexes with ORM metadata

Revision ID: 20260918_0003
Revises: 20260918_0002
Create Date: 2026-09-18
"""

from alembic import op

revision = "20260918_0003"
down_revision = "20260918_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.drop_index("ix_orders_order_id", table_name="orders")


def downgrade() -> None:
    op.create_index("ix_orders_order_id", "orders", ["order_id"])

    op.drop_index("ix_users_email", table_name="users")
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.create_index("ix_users_email", "users", ["email"])
