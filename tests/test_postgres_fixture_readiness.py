from testcontainers.core.wait_strategies import PortWaitStrategy

import conftest


def test_postgres_fixture_waits_for_mapped_host_port(monkeypatch):
    calls = {}

    class FakePostgresContainer:
        def __init__(self, **kwargs):
            calls["kwargs"] = kwargs

        def waiting_for(self, strategy):
            calls["strategy"] = strategy
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def get_connection_url(self):
            return "unused"

    monkeypatch.setattr(conftest, "PostgresContainer", FakePostgresContainer)
    fixture = conftest.postgres_container.__wrapped__()

    try:
        assert next(fixture) is not None
    finally:
        fixture.close()

    assert "strategy" in calls, (
        "the fixture must wait for the mapped host port before yielding"
    )
    assert isinstance(calls["strategy"], PortWaitStrategy)
    assert calls["strategy"]._port == 5432
