import pytest

# Import the standalone helper functions
from api.db import extract_all_ingredient_ids, assemble_ingredient_full_names

# REMOVED: Unnecessary fixture
# @pytest.fixture
# def db_instance():
#     return None # No instance needed for these tests

# --- Tests for extract_all_ingredient_ids ---


def test_extract_ids_empty_list():
    assert extract_all_ingredient_ids([]) == set()


def test_extract_ids_no_paths():
    ingredients = [
        {"ingredient_id": 1, "ingredient_path": "/1/"},
        {"ingredient_id": 2, "ingredient_path": "/2/"},
    ]
    assert extract_all_ingredient_ids(ingredients) == {1, 2}


def test_extract_ids_simple_paths():
    ingredients = [
        {"ingredient_id": 10, "ingredient_path": "/1/10/"},  # Ancestor 1
        {"ingredient_id": 20, "ingredient_path": "/2/20/"},  # Ancestor 2
    ]
    assert extract_all_ingredient_ids(ingredients) == {1, 2, 10, 20}


def test_extract_ids_complex_paths():
    ingredients = [
        {"ingredient_id": 100, "ingredient_path": "/1/10/100/"},  # Ancestors 1, 10
        {"ingredient_id": 200, "ingredient_path": "/1/20/200/"},  # Ancestors 1, 20
    ]
    # Should include 1, 10, 20, 100, 200
    assert extract_all_ingredient_ids(ingredients) == {1, 10, 20, 100, 200}


def test_extract_ids_duplicates():
    ingredients = [
        {"ingredient_id": 100, "ingredient_path": "/1/10/100/"},
        {"ingredient_id": 101, "ingredient_path": "/1/10/101/"},  # Same ancestors 1, 10
        {"ingredient_id": 200, "ingredient_path": "/2/20/200/"},
    ]
    # Should only contain unique IDs: 1, 10, 100, 101, 2, 20, 200
    assert extract_all_ingredient_ids(ingredients) == {
        1,
        2,
        10,
        20,
        100,
        101,
        200,
    }


def test_extract_ids_none_path():
    ingredients = [
        {"ingredient_id": 5, "ingredient_path": None},
        {"ingredient_id": 6, "ingredient_path": "/6/"},
    ]
    assert extract_all_ingredient_ids(ingredients) == {5, 6}


def test_extract_ids_missing_keys():
    # Test robustness if keys are missing (though type hints suggest they shouldn't be)
    ingredients = [
        {"ingredient_id": 1},  # Missing path
        {"ingredient_path": "/2/20/"},  # Missing id
    ]
    # Current implementation handles missing 'path', handles missing 'ingredient_id' gracefully
    assert extract_all_ingredient_ids(ingredients) == {
        1,
        2,  # Extracts 2 from path
        20,  # Extracts 20 from path
    }


# --- Tests for assemble_ingredient_full_names ---


def test_assemble_names_empty_list():
    ingredients = []
    names_map = {}
    assemble_ingredient_full_names(ingredients, names_map)
    assert ingredients == []


def test_assemble_names_no_ancestors():
    ingredients = [
        {"ingredient_id": 1, "ingredient_name": "Gin", "ingredient_path": "/1/"},
        {"ingredient_id": 2, "ingredient_name": "Tonic", "ingredient_path": None},
    ]
    names_map = {1: "Gin", 2: "Tonic Water"}
    assemble_ingredient_full_names(ingredients, names_map)
    assert ingredients[0]["full_name"] == "Gin"
    assert ingredients[1]["full_name"] == "Tonic Water"


def test_assemble_names_with_ancestors():
    ingredients = [
        {
            "ingredient_id": 10,
            "ingredient_name": "Lime Juice",
            "ingredient_path": "/1/5/10/",
        },  # Citrus -> Lime -> Lime Juice
        {
            "ingredient_id": 20,
            "ingredient_name": "Simple Syrup",
            "ingredient_path": "/2/20/",
        },  # Sweetener -> Simple Syrup
    ]
    names_map = {
        1: "Citrus",
        5: "Lime",
        10: "Lime Juice",
        2: "Sweetener",
        20: "Simple Syrup",
    }
    assemble_ingredient_full_names(ingredients, names_map)
    assert (
        ingredients[0]["full_name"] == "Lime Juice [Lime;Citrus]"
    )  # Note reversed order
    assert ingredients[1]["full_name"] == "Simple Syrup [Sweetener]"


def test_assemble_names_missing_ancestor_name():
    ingredients = [
        {
            "ingredient_id": 10,
            "ingredient_name": "Lime Juice",
            "ingredient_path": "/1/5/10/",
        },
    ]
    names_map = {1: "Citrus", 10: "Lime Juice"}  # Missing name for ID 5
    assemble_ingredient_full_names(ingredients, names_map)
    # Should only include names found in the map
    assert ingredients[0]["full_name"] == "Lime Juice [Citrus]"


def test_assemble_names_missing_base_name_in_map():
    ingredients = [
        # Base name 'Orange Juice' not in map, should use 'ingredient_name'
        {"ingredient_id": 15, "ingredient_name": "OJ", "ingredient_path": "/1/7/15/"},
    ]
    names_map = {1: "Citrus", 7: "Orange"}  # Missing name for ID 15
    assemble_ingredient_full_names(ingredients, names_map)
    # Falls back to 'ingredient_name' field
    assert ingredients[0]["full_name"] == "OJ [Orange;Citrus]"


def test_assemble_names_empty_map():
    ingredients = [
        {
            "ingredient_id": 10,
            "ingredient_name": "Lime Juice",
            "ingredient_path": "/1/5/10/",
        },
    ]
    names_map = {}
    assemble_ingredient_full_names(ingredients, names_map)
    # Falls back to ingredient_name, no ancestors found in map
    assert ingredients[0]["full_name"] == "Lime Juice"


def test_assemble_names_path_only_self():
    ingredients = [
        {"ingredient_id": 1, "ingredient_name": "Vodka", "ingredient_path": "/1/"},
    ]
    names_map = {1: "Vodka"}
    assemble_ingredient_full_names(ingredients, names_map)
    assert ingredients[0]["full_name"] == "Vodka"
