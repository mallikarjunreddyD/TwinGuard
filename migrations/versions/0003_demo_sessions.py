"""Explicit isolated simulation session and command persistence."""

from alembic import op
from twinguard.edge.demo_sessions import meta

revision = "0003_demo_sessions"
down_revision = "0002_planning"


def upgrade():
    connection = op.get_bind()
    meta.create_all(connection)
    if connection.dialect.name == "postgresql":
        from sqlalchemy import text

        if connection.execute(
            text("SELECT 1 FROM pg_roles WHERE rolname = 'tg_simulation'")
        ).scalar():
            op.execute("GRANT SELECT, UPDATE ON demo_sessions TO tg_simulation")
            op.execute("GRANT SELECT ON jobs TO tg_simulation")


def downgrade():
    meta.drop_all(op.get_bind())
