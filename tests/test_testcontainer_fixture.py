import conftest


class FailingPostgresContainer:
    def waiting_for(self, _strategy):
        return self

    def __enter__(self):
        raise RuntimeError("Docker daemon unavailable")

    def __exit__(self, *_args):
        return False


class FailingOnExitPostgresContainer:
    def waiting_for(self, _strategy):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        raise RuntimeError("container cleanup failed")

    def get_connection_url(self):
        return "postgresql://test"


class FailingDuringReadinessPostgresContainer:
    def __init__(self):
        self.events = []

    def waiting_for(self, _strategy):
        self.events.append("waiting_for")
        return self

    def __enter__(self):
        self.events.append("enter")
        return self

    def __exit__(self, *_args):
        self.events.append("exit")
        return False

    def get_connection_url(self):
        self.events.append("connection_url")
        raise RuntimeError("PostgreSQL authentication timed out")


def test_postgres_container_setup_failure_exits_test_session():
    original = conftest.PostgresContainer
    conftest.PostgresContainer = lambda **_kwargs: FailingPostgresContainer()
    fixture = vars(conftest.postgres_container)["__wrapped__"]()

    try:
        next(fixture)
    except BaseException as error:
        assert type(error).__name__ == "Exit"
        assert vars(error).get("returncode") == 2
        assert "PostgreSQL test container" in str(error)
    else:
        raise AssertionError("fixture did not exit the test session")
    finally:
        conftest.PostgresContainer = original


def test_postgres_container_does_not_mask_post_readiness_failure():
    original = conftest.PostgresContainer
    conftest.PostgresContainer = lambda **_kwargs: FailingOnExitPostgresContainer()
    fixture = vars(conftest.postgres_container)["__wrapped__"]()

    try:
        next(fixture)
        next(fixture)
    except RuntimeError as error:
        assert str(error) == "container cleanup failed"
    else:
        raise AssertionError("fixture masked the cleanup failure")
    finally:
        conftest.PostgresContainer = original


def test_postgres_container_cleans_up_when_readiness_check_fails():
    original = conftest.PostgresContainer
    container = FailingDuringReadinessPostgresContainer()
    conftest.PostgresContainer = lambda **_kwargs: container
    fixture = vars(conftest.postgres_container)["__wrapped__"]()

    try:
        next(fixture)
    except BaseException as error:
        assert type(error).__name__ == "Exit"
        assert vars(error).get("returncode") == 2
        assert "PostgreSQL authentication timed out" in str(error)
    else:
        raise AssertionError("fixture did not exit the test session")
    finally:
        fixture.close()
        conftest.PostgresContainer = original

    assert container.events == ["waiting_for", "enter", "connection_url", "exit"]
