"""Versioned planning records use existing records and artifact references; index isolated jobs."""

from alembic import op

revision = "0002_planning"
down_revision = "0001_edge"


def upgrade():
    op.create_index("ix_jobs_kind_status_created", "jobs", ["kind", "status", "created"])


def downgrade():
    op.drop_index("ix_jobs_kind_status_created", table_name="jobs")
