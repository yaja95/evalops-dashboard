from evalops_dashboard.database import engine


def test_test_database_uses_in_memory_sqlite() -> None:
    assert engine.dialect.name == "sqlite"
    assert str(engine.url) == "sqlite://"
