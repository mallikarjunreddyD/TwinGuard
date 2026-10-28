"""Durable inbox, observations, leased jobs, versioned records and transactional outbox."""

from alembic import op
from twinguard.edge.storage import metadata

revision = "0001_edge"
down_revision = None


def upgrade():
    metadata.create_all(op.get_bind())


def downgrade():
    metadata.drop_all(op.get_bind())
