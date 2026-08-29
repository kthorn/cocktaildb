import conftest


class FailingPostgresContainer:
    def __enter__(self):
        raise RuntimeError("Docker daemon unavailable")

    def __exit__(self, *_args):
        return False


class FailingOnExitPostgresContainer:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        raise RuntimeError("container cleanup failed")

    def get_connection_url(self):
        return "postgresql://test"


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
