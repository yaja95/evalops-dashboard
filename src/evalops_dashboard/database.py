import os
from collections.abc import Generator

from sqlalchemy import event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

DATABASE_URL = os.getenv("EVALOPS_DATABASE_URL", "sqlite:///./evalops.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
pool_args = {"poolclass": StaticPool} if DATABASE_URL == "sqlite://" else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, **pool_args)


if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
