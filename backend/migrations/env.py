from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.core.config import Settings
from backend.app.core.database import Base
from backend.app.data import models as data_models  # register P1-01 metadata
from backend.app.auth import models as auth_models  # register P2-01 metadata
from backend.app.audit import models as audit_models  # register P2-01 metadata

# Import each domain model module here before autogeneration, so its tables are
# registered on Base.metadata. Each domain owns and reviews its own revisions.
target_metadata = Base.metadata
config = context.config
if config.config_file_name and config.file_config.has_section("loggers"):
    fileConfig(config.config_file_name)


def run_migrations_offline():
    context.configure(url=Settings.from_env().database_url, target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # Supply URL as a plain value rather than Config.set_main_option: passwords
    # may contain percent signs, which ConfigParser would otherwise interpolate.
    connectable = engine_from_config({"sqlalchemy.url": Settings.from_env().database_url},
                                     prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
