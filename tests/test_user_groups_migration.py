"""Migration tests against a captured pre-user-groups PostgreSQL schema."""

import re
from pathlib import Path

import psycopg2
import pytest

ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "migrations" / "15_migration_add_user_groups.sql"
PRE_FEATURE_SCHEMA = ROOT / "tests" / "fixtures" / "pre_user_groups_schema.sql"
HEX_CODE = re.compile(r"^[0-9a-f]{12}$")


def _reset_public_schema(params):
    connection = psycopg2.connect(**params)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                DO $$ DECLARE
                    item RECORD;
                BEGIN
                    FOR item IN (
                        SELECT tablename
                        FROM pg_tables
                        WHERE schemaname = 'public'
                    ) LOOP
                        EXECUTE format(
                            'DROP TABLE IF EXISTS public.%I CASCADE', item.tablename
                        );
                    END LOOP;
                    DROP EXTENSION IF EXISTS pgcrypto CASCADE;
                    DROP EXTENSION IF EXISTS citext CASCADE;
                    DROP EXTENSION IF EXISTS pg_trgm CASCADE;
                    DROP EXTENSION IF EXISTS unaccent CASCADE;
                    FOR item IN (
                        SELECT p.oid::regprocedure AS signature
                        FROM pg_proc p
                        JOIN pg_namespace n ON n.oid = p.pronamespace
                        WHERE n.nspname = 'public'
                    ) LOOP
                        EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', item.signature);
                    END LOOP;
                END $$;
                """
            )
            cursor.execute(PRE_FEATURE_SCHEMA.read_text())
    finally:
        connection.close()


@pytest.fixture
def pre_feature_db(postgres_connection_params):
    _reset_public_schema(postgres_connection_params)
    yield postgres_connection_params


def _seed_inventory(params, *, include_null=False):
    connection = psycopg2.connect(**params)
    connection.autocommit = True
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO ingredients (id, name) VALUES
                    (101, 'Bourbon'), (102, 'Rye'), (103, 'Lime')
                """
            )
            cursor.execute(
                """
                INSERT INTO user_ingredients
                    (cognito_user_id, ingredient_id, added_at)
                VALUES
                    ('user-a', 101, '2024-01-02 03:04:05'),
                    ('user-a', 102, '2024-01-03 04:05:06'),
                    ('user-b', 102, '2024-02-03 04:05:06'),
                    ('user-b', 103, '2024-02-04 05:06:07')
                """
            )
            if include_null:
                cursor.execute(
                    """
                    INSERT INTO user_ingredients
                        (cognito_user_id, ingredient_id, added_at)
                    VALUES ('user-null', 101, NULL)
                    """
                )
    finally:
        connection.close()


def _run_migration(params, *, inject_failure=False):
    migration = MIGRATION.read_text()
    if inject_failure:
        migration = migration.replace(
            "COMMIT;",
            "SELECT 1 / 0;\nCOMMIT;",
            1,
        )
    connection = psycopg2.connect(**params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(migration)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _fetchall(params, query, args=()):
    connection = psycopg2.connect(**params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, args)
            return cursor.fetchall()
    finally:
        connection.close()


def test_migration_backfills_distinct_users_and_preserves_inventory(pre_feature_db):
    _seed_inventory(pre_feature_db)
    before = _fetchall(
        pre_feature_db,
        """
        SELECT id, cognito_user_id, ingredient_id, added_at
        FROM user_ingredients
        ORDER BY cognito_user_id, ingredient_id
        """,
    )

    _run_migration(pre_feature_db)

    assert _fetchall(pre_feature_db, "SELECT count(*) FROM user_groups")[0][0] == 2
    members = _fetchall(
        pre_feature_db,
        """
        SELECT g.cognito_user_id, g.group_id, u.invite_code
        FROM user_group_members g
        JOIN user_groups u ON u.id = g.group_id
        ORDER BY g.cognito_user_id
        """,
    )
    assert [row[0] for row in members] == ["user-a", "user-b"]
    assert len({row[1] for row in members}) == 2
    assert all(HEX_CODE.fullmatch(row[2]) for row in members)
    assert len({row[2] for row in members}) == 2

    migrated = _fetchall(
        pre_feature_db,
        """
        SELECT m.cognito_user_id, i.ingredient_id, i.added_by, i.added_at
        FROM group_ingredients i
        JOIN user_group_members m ON m.group_id = i.group_id
        ORDER BY m.cognito_user_id, i.ingredient_id
        """,
    )
    expected = [
        (user, ingredient, user, timestamp)
        for _id, user, ingredient, timestamp in before
    ]
    assert migrated == expected
    assert _fetchall(
        pre_feature_db,
        """
        SELECT id, cognito_user_id, ingredient_id, added_at
        FROM user_ingredients
        ORDER BY cognito_user_id, ingredient_id
        """,
    ) == before


def test_migration_with_empty_legacy_inventory_creates_no_groups(pre_feature_db):
    _run_migration(pre_feature_db)

    assert _fetchall(pre_feature_db, "SELECT count(*) FROM user_groups")[0][0] == 0
    assert _fetchall(pre_feature_db, "SELECT count(*) FROM user_group_members")[0][0] == 0
    assert _fetchall(pre_feature_db, "SELECT count(*) FROM group_ingredients")[0][0] == 0
    assert _fetchall(
        pre_feature_db,
        "SELECT extname FROM pg_extension WHERE extname = 'pgcrypto'",
    ) == [("pgcrypto",)]


def test_migration_rejects_null_legacy_timestamps_atomically(pre_feature_db):
    _seed_inventory(pre_feature_db, include_null=True)

    with pytest.raises(psycopg2.Error, match="Resolve null user_ingredients.added_at"):
        _run_migration(pre_feature_db)

    assert _fetchall(pre_feature_db, "SELECT to_regclass('user_groups')")[0][0] is None
    assert _fetchall(
        pre_feature_db,
        "SELECT added_at FROM user_ingredients WHERE cognito_user_id = 'user-null'",
    ) == [(None,)]


def test_migration_rolls_back_all_objects_when_failure_is_injected(pre_feature_db):
    _seed_inventory(pre_feature_db)

    with pytest.raises(psycopg2.Error, match="division by zero"):
        _run_migration(pre_feature_db, inject_failure=True)

    assert _fetchall(pre_feature_db, "SELECT to_regclass('user_groups')")[0][0] is None
    assert _fetchall(pre_feature_db, "SELECT to_regclass('group_ingredients')")[0][0] is None
    assert _fetchall(pre_feature_db, "SELECT count(*) FROM user_ingredients")[0][0] == 4


def test_fresh_schema_has_group_tables_indexes_and_trigger(pg_db_with_schema):
    assert _fetchall(
        pg_db_with_schema,
        "SELECT extname FROM pg_extension WHERE extname = 'pgcrypto'",
    ) == [("pgcrypto",)]
    assert _fetchall(
        pg_db_with_schema,
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name IN ('user_groups', 'user_group_members', 'group_ingredients')
        ORDER BY table_name
        """,
    ) == [("group_ingredients",), ("user_group_members",), ("user_groups",)]

    assert _fetchall(
        pg_db_with_schema,
        """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('user_groups', 'user_group_members', 'group_ingredients')
        ORDER BY table_name, ordinal_position
        """,
    ) == [
        ("group_ingredients", "id", "integer", "NO"),
        ("group_ingredients", "group_id", "integer", "NO"),
        ("group_ingredients", "ingredient_id", "integer", "NO"),
        ("group_ingredients", "added_by", "text", "NO"),
        ("group_ingredients", "added_at", "timestamp without time zone", "NO"),
        ("user_group_members", "id", "integer", "NO"),
        ("user_group_members", "group_id", "integer", "NO"),
        ("user_group_members", "cognito_user_id", "text", "NO"),
        ("user_group_members", "joined_at", "timestamp without time zone", "NO"),
        ("user_groups", "id", "integer", "NO"),
        ("user_groups", "name", "text", "NO"),
        ("user_groups", "description", "text", "YES"),
        ("user_groups", "invite_code", "text", "NO"),
        ("user_groups", "created_at", "timestamp without time zone", "NO"),
        ("user_groups", "updated_at", "timestamp without time zone", "NO"),
    ]

    assert _fetchall(
        pg_db_with_schema,
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename IN ('user_groups', 'user_group_members', 'group_ingredients')
        ORDER BY indexname
        """,
    ) == [
        ("group_ingredients_group_id_ingredient_id_key",),
        ("group_ingredients_pkey",),
        ("idx_group_ingredients_ingredient_id",),
        ("idx_user_group_members_group_id",),
        ("user_group_members_cognito_user_id_key",),
        ("user_group_members_pkey",),
        ("user_groups_invite_code_key",),
        ("user_groups_pkey",),
    ]
    assert _fetchall(
        pg_db_with_schema,
        "SELECT tgname FROM pg_trigger WHERE tgrelid = 'user_groups'::regclass AND NOT tgisinternal",
    ) == [("update_user_groups_updated_at",)]
