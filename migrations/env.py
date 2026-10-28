import os
from alembic import context
from sqlalchemy import create_engine
from twinguard.edge.storage import metadata

config = context.config
url = os.environ["TWINGUARD_DB"]
with create_engine(url).connect() as connection:
    context.configure(connection=connection, target_metadata=metadata)
    with context.begin_transaction():
        context.run_migrations()
