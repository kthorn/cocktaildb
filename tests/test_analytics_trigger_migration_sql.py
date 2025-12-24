from pathlib import Path


def test_analytics_refresh_migration_contains_expected_sql():
    sql = Path("migrations/09_migration_add_analytics_refresh_state.sql").read_text()
    assert "CREATE TABLE" in sql
    assert "analytics_refresh_state" in sql
    assert "mark_analytics_dirty" in sql
    assert "CREATE TRIGGER" in sql
