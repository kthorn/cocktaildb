import conftest
from testcontainers.core.wait_strategies import PortWaitStrategy


def test_postgres_fixture_waits_for_mapped_host_port_before_yield(monkeypatch):
    calls = {"events": []}

    class FakePostgresContainer:
        def __init__(self, **kwargs):
            calls["kwargs"] = kwargs

        def waiting_for(self, strategy):
            calls["strategy"] = strategy
            calls["events"].append("waiting_for")
            return self

        def __enter__(self):
            calls["events"].append("enter")
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            calls["events"].append("exit")
            return False

        def get_connection_url(self):
            calls["events"].append("connection_url")
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
    assert calls["events"] == ["waiting_for", "enter", "connection_url", "exit"]
