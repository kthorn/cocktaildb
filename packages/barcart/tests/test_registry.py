"""Tests for Registry class."""

import warnings

import numpy as np
import pytest

from barcart.registry import Registry


class TestRegistryInit:
    """Test Registry initialization and validation."""

    def test_basic_construction(self):
        """Test basic registry construction with valid data."""
        entities = [(0, "123", "Gin"), (1, "456", "Vodka"), (2, "789", "Rum")]
        registry = Registry(entities)
        assert len(registry) == 3

    def test_empty_entities_raises(self):
        """Test that empty entity list raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            Registry([])

    def test_non_contiguous_indices_raises(self):
        """Test that non-contiguous indices raise ValueError."""
        entities = [(0, "123", "Gin"), (2, "456", "Vodka")]  # Missing index 1
        with pytest.raises(ValueError, match="contiguous"):
            Registry(entities)

    def test_indices_not_starting_at_zero_raises(self):
        """Test that indices not starting at 0 raise ValueError."""
        entities = [(1, "123", "Gin"), (2, "456", "Vodka")]
        with pytest.raises(ValueError, match="contiguous"):
            Registry(entities)

    def test_duplicate_ids_raises(self):
        """Test that duplicate IDs raise ValueError."""
        entities = [(0, "123", "Gin"), (1, "123", "Vodka")]
        with pytest.raises(ValueError, match="Duplicate entity IDs"):
            Registry(entities)

    def test_duplicate_names_warns(self):
        """Test that duplicate names trigger a warning."""
        entities = [(0, "123", "Gin"), (1, "456", "Gin")]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            Registry(entities)
            assert len(w) == 1
            assert "Duplicate entity names" in str(w[0].message)

    def test_out_of_order_indices_sorted(self):
        """Test that out-of-order entities are sorted by index."""
        entities = [(2, "789", "Rum"), (0, "123", "Gin"), (1, "456", "Vodka")]
        registry = Registry(entities)
        assert registry[0] == ("123", "Gin")
        assert registry[1] == ("456", "Vodka")
        assert registry[2] == ("789", "Rum")


class TestRegistryGetName:
    """Test get_name method."""

    @pytest.fixture
    def registry(self):
        """Create a test registry."""
        entities = [(0, "123", "Gin"), (1, "456", "Vodka"), (2, "789", "Rum")]
        return Registry(entities)

    def test_get_name_by_index(self, registry):
        """Test getting name by matrix index."""
        assert registry.get_name(index=0) == "Gin"
        assert registry.get_name(index=1) == "Vodka"
        assert registry.get_name(index=2) == "Rum"

    def test_get_name_by_id(self, registry):
        """Test getting name by ingredient ID."""
        assert registry.get_name(id="123") == "Gin"
        assert registry.get_name(id="456") == "Vodka"
        assert registry.get_name(id="789") == "Rum"

    def test_get_name_no_args_raises(self, registry):
        """Test that providing no arguments raises ValueError."""
        with pytest.raises(ValueError, match="Exactly one"):
            registry.get_name()

    def test_get_name_both_args_raises(self, registry):
        """Test that providing both arguments raises ValueError."""
        with pytest.raises(ValueError, match="Exactly one"):
            registry.get_name(index=0, id="123")

    def test_get_name_index_out_of_range_raises(self, registry):
        """Test that out-of-range index raises IndexError."""
        with pytest.raises(IndexError, match="out of range"):
            registry.get_name(index=5)
        with pytest.raises(IndexError, match="out of range"):
            registry.get_name(index=-1)

    def test_get_name_unknown_id_raises(self, registry):
        """Test that unknown ID raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            registry.get_name(id="999")


class TestRegistryGetId:
    """Test get_id method."""

    @pytest.fixture
    def registry(self):
        """Create a test registry."""
        entities = [(0, "123", "Gin"), (1, "456", "Vodka"), (2, "789", "Rum")]
        return Registry(entities)

    def test_get_id_by_index(self, registry):
        """Test getting ID by matrix index."""
        assert registry.get_id(index=0) == "123"
        assert registry.get_id(index=1) == "456"
        assert registry.get_id(index=2) == "789"

    def test_get_id_by_name(self, registry):
        """Test getting ID by ingredient name."""
        assert registry.get_id(name="Gin") == "123"
        assert registry.get_id(name="Vodka") == "456"
        assert registry.get_id(name="Rum") == "789"

    def test_get_id_no_args_raises(self, registry):
        """Test that providing no arguments raises ValueError."""
        with pytest.raises(ValueError, match="Exactly one"):
            registry.get_id()

    def test_get_id_both_args_raises(self, registry):
        """Test that providing both arguments raises ValueError."""
        with pytest.raises(ValueError, match="Exactly one"):
            registry.get_id(index=0, name="Gin")

    def test_get_id_index_out_of_range_raises(self, registry):
        """Test that out-of-range index raises IndexError."""
        with pytest.raises(IndexError, match="out of range"):
            registry.get_id(index=5)

    def test_get_id_unknown_name_raises(self, registry):
        """Test that unknown name raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            registry.get_id(name="Tequila")


class TestRegistryGetIndex:
    """Test get_index method."""

    @pytest.fixture
    def registry(self):
        """Create a test registry."""
        entities = [(0, "123", "Gin"), (1, "456", "Vodka"), (2, "789", "Rum")]
        return Registry(entities)

    def test_get_index_by_id(self, registry):
        """Test getting index by ingredient ID."""
        assert registry.get_index(id="123") == 0
        assert registry.get_index(id="456") == 1
        assert registry.get_index(id="789") == 2

    def test_get_index_by_name(self, registry):
        """Test getting index by ingredient name."""
        assert registry.get_index(name="Gin") == 0
        assert registry.get_index(name="Vodka") == 1
        assert registry.get_index(name="Rum") == 2

    def test_get_index_no_args_raises(self, registry):
        """Test that providing no arguments raises ValueError."""
        with pytest.raises(ValueError, match="Exactly one"):
            registry.get_index()

    def test_get_index_both_args_raises(self, registry):
        """Test that providing both arguments raises ValueError."""
        with pytest.raises(ValueError, match="Exactly one"):
            registry.get_index(id="123", name="Gin")

    def test_get_index_unknown_id_raises(self, registry):
        """Test that unknown ID raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            registry.get_index(id="999")

    def test_get_index_unknown_name_raises(self, registry):
        """Test that unknown name raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            registry.get_index(name="Tequila")


class TestRegistryConvenience:
    """Test convenience methods."""

    @pytest.fixture
    def registry(self):
        """Create a test registry."""
        entities = [(0, "123", "Gin"), (1, "456", "Vodka"), (2, "789", "Rum")]
        return Registry(entities)

    def test_len(self, registry):
        """Test __len__ method."""
        assert len(registry) == 3

    def test_getitem(self, registry):
        """Test __getitem__ method."""
        assert registry[0] == ("123", "Gin")
        assert registry[1] == ("456", "Vodka")
        assert registry[2] == ("789", "Rum")

    def test_getitem_out_of_range_raises(self, registry):
        """Test that out-of-range index raises IndexError."""
        with pytest.raises(IndexError):
            registry[5]
        with pytest.raises(IndexError):
            registry[-1]

    def test_validate_matrix_valid(self, registry):
        """Test validate_matrix with compatible matrix."""
        matrix = np.zeros((3, 3))
        registry.validate_matrix(matrix)  # Should not raise

    def test_validate_matrix_wrong_shape_raises(self, registry):
        """Test validate_matrix with incompatible matrix."""
        matrix = np.zeros((4, 4))
        with pytest.raises(ValueError, match="incompatible"):
            registry.validate_matrix(matrix)

    def test_validate_matrix_non_square_raises(self, registry):
        """Test validate_matrix with non-square matrix."""
        matrix = np.zeros((3, 4))
        with pytest.raises(ValueError, match="incompatible"):
            registry.validate_matrix(matrix)

    def test_validate_matrix_1d_raises(self, registry):
        """Test validate_matrix with 1D array."""
        array = np.zeros(3)
        with pytest.raises(ValueError, match="2-dimensional"):
            registry.validate_matrix(array)

    def test_to_id_to_index(self, registry):
        """Test to_id_to_index export."""
        id_to_index = registry.to_id_to_index()
        assert id_to_index == {"123": 0, "456": 1, "789": 2}
        # Verify it's a copy, not the internal dict
        id_to_index["999"] = 99
        assert "999" not in registry.to_id_to_index()


class TestRegistryLazyNameIndex:
    """Test lazy initialization of name-to-index mapping."""

    def test_name_index_built_on_first_use(self):
        """Test that name index is built lazily."""
        entities = [(0, "123", "Gin"), (1, "456", "Vodka")]
        registry = Registry(entities)

        # Name index should be None initially
        assert registry._name_to_idx is None

        # First name-based lookup should build the index
        registry.get_index(name="Gin")
        assert registry._name_to_idx is not None
        assert registry._name_to_idx == {"Gin": 0, "Vodka": 1}

        # Subsequent lookups should reuse the same index
        registry.get_id(name="Vodka")
        assert registry._name_to_idx == {"Gin": 0, "Vodka": 1}


class TestRegistryTypeNormalization:
    """Test that various input types are normalized to strings."""

    def test_int_ids_converted_to_strings(self):
        """Test that integer IDs are converted to strings."""
        entities = [(0, 123, "Gin"), (1, 456, "Vodka")]
        registry = Registry(entities)
        assert registry.get_id(index=0) == "123"
        assert registry.get_name(id="123") == "Gin"

    def test_mixed_type_ids_normalized(self):
        """Test that mixed ID types are normalized."""
        entities = [(0, "123", "Gin"), (1, 456, "Vodka")]
        registry = Registry(entities)
        assert registry.get_id(index=1) == "456"
        assert registry.get_index(id="456") == 1
