"""End-to-end tests for the analytics regeneration batch job."""

import json

import psycopg2
import pytest
from analytics import analytics_refresh
from analytics.analytics_refresh import (
    enrich_tree_with_recipe_counts,
    regenerate_analytics,
)
from utils.analytics_cache import AnalyticsStorage

ANALYTICS_TYPES = (
    "ingredient-usage",
    "recipe-complexity",
    "cocktail-space",
    "cocktail-space-em",
    "ingredient-tree",
)


def _query(params, sql):
    conn = psycopg2.connect(**params)
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        conn.close()


def _tree_ids(node):
    ids = [] if node["id"] == "root" else [int(node["id"])]
    for child in node.get("children", []):
        ids.extend(_tree_ids(child))
    return ids


def test_regenerate_analytics_stores_every_artifact(
    test_db_with_data, tmp_path, monkeypatch
):
    monkeypatch.setenv("ANALYTICS_PATH", str(tmp_path))

    result = regenerate_analytics()

    storage = AnalyticsStorage(str(tmp_path))
    stored = {kind: storage.get_analytics(kind) for kind in ANALYTICS_TYPES}
    assert all(stored[kind] is not None for kind in ANALYTICS_TYPES), stored.keys()

    root_ids = {
        row[0]
        for row in _query(
            test_db_with_data, "SELECT id FROM ingredients WHERE parent_id IS NULL"
        )
    }
    usage = stored["ingredient-usage"]["data"]
    assert {row["ingredient_id"] for row in usage} == root_ids
    assert result["ingredient_stats_count"] == len(root_ids)

    all_ids = {
        row[0] for row in _query(test_db_with_data, "SELECT id FROM ingredients")
    }
    tree = stored["ingredient-tree"]["data"]
    assert tree["id"] == "root"
    assert set(_tree_ids(tree)) == all_ids
    assert result["ingredient_tree_nodes"] == len(all_ids)

    recipe_ids = {
        row[0]
        for row in _query(
            test_db_with_data, "SELECT DISTINCT recipe_id FROM recipe_ingredients"
        )
    }
    assert result["cocktail_space_em_count"] == len(recipe_ids)
    similarity_rows = _query(
        test_db_with_data, "SELECT recipe_id FROM recipe_similarity"
    )
    assert {row[0] for row in similarity_rows} == recipe_ids


def test_regenerate_analytics_requires_storage_path(monkeypatch):
    monkeypatch.delenv("ANALYTICS_PATH", raising=False)

    with pytest.raises(ValueError, match="ANALYTICS_PATH"):
        regenerate_analytics()


def test_cli_reports_success_as_json(monkeypatch, capsys):
    monkeypatch.setattr(
        analytics_refresh, "regenerate_analytics", lambda: {"cocktail_space_count": 3}
    )

    with pytest.raises(SystemExit) as exit_info:
        analytics_refresh.main()

    assert exit_info.value.code == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "success"
    assert output["cocktail_space_count"] == 3


def test_cli_reports_failure_as_json(monkeypatch, capsys):
    monkeypatch.delenv("ANALYTICS_PATH", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        analytics_refresh.main()

    assert exit_info.value.code == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "error"
    assert "ANALYTICS_PATH" in output["details"]


def test_enrich_tree_adds_counts_and_zeroes_unknown_nodes():
    tree = {
        "id": "root",
        "children": [{"id": 1, "children": [{"id": 2}]}, {"id": 3}],
    }
    counts = {
        "1": {"direct": 2, "hierarchical": 5},
        "2": {"direct": 3, "hierarchical": 3},
    }

    enriched = enrich_tree_with_recipe_counts(tree, counts)

    assert (enriched["recipe_count"], enriched["hierarchical_recipe_count"]) == (0, 0)
    spirit, unknown = enriched["children"]
    assert (spirit["recipe_count"], spirit["hierarchical_recipe_count"]) == (2, 5)
    assert spirit["children"][0]["recipe_count"] == 3
    assert (unknown["recipe_count"], unknown["hierarchical_recipe_count"]) == (0, 0)
