from sqlalchemy import create_engine

from evalops_dashboard.database import engine


def test_test_database_uses_in_memory_sqlite() -> None:
    assert engine.dialect.name == "sqlite"
    assert str(engine.url) == "sqlite://"


def test_application_engine_enables_sqlite_foreign_keys() -> None:
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1


def test_application_foreign_key_listener_is_not_global() -> None:
    separate_engine = create_engine("sqlite:///:memory:")
    try:
        with separate_engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 0
    finally:
        separate_engine.dispose()
