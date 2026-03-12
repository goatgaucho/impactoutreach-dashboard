"""Add unique constraint to prevent duplicate sends for same constituent+recipient pair

Revision ID: 002
Revises: 001
Create Date: 2026-03-12
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_sends_campaign_constituent_recipient",
        "sends",
        ["campaign_id", "constituent_id", "recipient_email"],
    )


def downgrade():
    op.drop_constraint("uq_sends_campaign_constituent_recipient", "sends")
