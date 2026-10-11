"""Add patient-reported medication stock and reminder preferences.

Revision ID: 0003_medication_stock_tracking
Revises: 0002_patient_timezone
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_medication_stock_tracking"
down_revision = "0002_patient_timezone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("prescription_items")}
    if "stock_remaining" not in columns:
        op.add_column("prescription_items", sa.Column("stock_remaining", sa.Integer(), nullable=True))
    if "stock_reminder_enabled" not in columns:
        op.add_column(
            "prescription_items",
            sa.Column("stock_reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if "stock_reminder_threshold" not in columns:
        op.add_column(
            "prescription_items",
            sa.Column("stock_reminder_threshold", sa.Integer(), nullable=False, server_default="10"),
        )


def downgrade() -> None:
    # Preserve patient-entered stock settings on downgrade rather than deleting them.
    pass
