"""Generic registry for entity metadata, tracking IDs, names, and matrix indices."""

import warnings

import numpy as np


class Registry:
    """
    Central registry mapping matrix indices ↔ entity IDs ↔ names.

    Generic registry for any entity type (ingredients, recipes, etc.).

    This class provides a single source of truth for entity metadata,
    supporting any entity type (ingredients, recipes, etc.). It replaces
    the previous pattern of passing around separate id_to_index,
    index_to_id, and id_to_name dictionaries.

    Parameters
    ----------
    entities : list of tuple
        List of (matrix_index, entity_id, entity_name) tuples.
        Matrix indices must be contiguous integers starting at 0.

    Attributes
    ----------
    The class is immutable after construction. All lookups are O(1).

    Examples
    --------
    >>> entities = [(0, "123", "Gin"), (1, "456", "Vodka")]
    >>> registry = Registry(entities)
    >>> registry.get_name(index=0)
    'Gin'
    >>> registry.get_index(id="456")
    1
    >>> len(registry)
    2
    """

    def __init__(self, entities: list[tuple[int, str, str]]):
        """
        Initialize the registry with entity data.

        Parameters
        ----------
        entities : list of tuple
            List of (matrix_index, entity_id, entity_name) tuples.

        Raises
        ------
        ValueError
            If matrix indices are not contiguous 0..N-1, or if duplicate IDs found.
        """
        self._validate_entities(entities)

        # Sort by index to ensure arrays are in matrix order
        entities_sorted = sorted(entities, key=lambda x: x[0])

        # Store as parallel numpy arrays for fast index-based access
        self._indices = np.array([idx for idx, _, _ in entities_sorted], dtype=int)
        self._ids = np.array([str(id) for _, id, _ in entities_sorted], dtype=object)
        self._names = np.array(
            [str(name) for _, _, name in entities_sorted], dtype=object
        )

        # Build reverse lookup dicts
        self._id_to_idx = {str(id): idx for idx, id, _ in entities_sorted}
        self._name_to_idx: dict[str, int] | None = (
            None  # Lazy initialization on first use
        )

    def _validate_entities(self, entities: list[tuple[int, str, str]]) -> None:
        """
        Validate entity data quality.

        Parameters
        ----------
        entities : list of tuple
            List of (matrix_index, entity_id, entity_name) tuples.

        Raises
        ------
        ValueError
            If validation fails.
        """
        if not entities:
            raise ValueError("entities list cannot be empty")

        # Extract components
        indices = [idx for idx, _, _ in entities]
        ids = [str(id) for _, id, _ in entities]
        names = [str(name) for _, _, name in entities]

        # 1. Matrix indices must be contiguous 0..N-1
        if sorted(indices) != list(range(len(indices))):
            raise ValueError(
                f"Matrix indices must be contiguous 0..{len(indices) - 1}. "
                f"Got: {sorted(indices)}"
            )

        # 2. IDs must be unique
        if len(ids) != len(set(ids)):
            duplicates = {id for id in ids if ids.count(id) > 1}
            raise ValueError(f"Duplicate entity IDs found: {duplicates}")

        # 3. Names should be unique (warn if not, don't fail)
        if len(names) != len(set(names)):
            duplicates = {name for name in names if names.count(name) > 1}
            warnings.warn(f"Duplicate entity names found: {duplicates}", stacklevel=2)

    def get_name(self, index: int | None = None, id: str | int | None = None) -> str:
        """
        Get entity name from either index or id.

        Parameters
        ----------
        index : int, optional
            Matrix index (0-based). Mutually exclusive with `id`.
        id : str, optional
            Entity ID. Mutually exclusive with `index`.

        Returns
        -------
        str
            Entity name.

        Raises
        ------
        ValueError
            If both or neither argument is provided.
        IndexError
            If index is out of range.
        KeyError
            If id is not found.

        Examples
        --------
        >>> registry = Registry([(0, "123", "Gin")])
        >>> registry.get_name(index=0)
        'Gin'
        >>> registry.get_name(id="123")
        'Gin'
        """
        if (index is None) == (id is None):
            raise ValueError("Exactly one of 'index' or 'id' must be provided")
        if isinstance(id, int):
            id = str(id)
        if index is not None:
            if not 0 <= index < len(self):
                raise IndexError(f"Index {index} out of range [0, {len(self)})")
            return str(self._names[index])
        else:
            if id not in self._id_to_idx:
                raise KeyError(f"Entity ID '{id}' not found in registry")
            return str(self._names[self._id_to_idx[id]])

    def get_id(self, *, index: int | None = None, name: str | None = None) -> str:
        """
        Get entity ID from either index or name.

        Parameters
        ----------
        index : int, optional
            Matrix index (0-based). Mutually exclusive with `name`.
        name : str, optional
            Entity name. Mutually exclusive with `index`.

        Returns
        -------
        str
            Entity ID.

        Raises
        ------
        ValueError
            If both or neither argument is provided.
        IndexError
            If index is out of range.
        KeyError
            If name is not found.

        Examples
        --------
        >>> registry = Registry([(0, "123", "Gin")])
        >>> registry.get_id(index=0)
        '123'
        >>> registry.get_id(name="Gin")
        '123'
        """
        if (index is None) == (name is None):
            raise ValueError("Exactly one of 'index' or 'name' must be provided")

        if index is not None:
            if not 0 <= index < len(self):
                raise IndexError(f"Index {index} out of range [0, {len(self)})")
            return str(self._ids[index])
        else:
            # Lazy build name index on first name lookup
            if self._name_to_idx is None:
                self._name_to_idx = {
                    str(name): idx for idx, name in enumerate(self._names)
                }
            if name not in self._name_to_idx:
                raise KeyError(f"Entity name '{name}' not found in registry")
            return str(self._ids[self._name_to_idx[name]])

    def get_index(self, *, id: str | None = None, name: str | None = None) -> int:
        """
        Get matrix index from either id or name.

        Parameters
        ----------
        id : str, optional
            Entity ID. Mutually exclusive with `name`.
        name : str, optional
            Entity name. Mutually exclusive with `id`.

        Returns
        -------
        int
            Matrix index (0-based).

        Raises
        ------
        ValueError
            If both or neither argument is provided.
        KeyError
            If id or name is not found.

        Examples
        --------
        >>> registry = Registry([(0, "123", "Gin")])
        >>> registry.get_index(id="123")
        0
        >>> registry.get_index(name="Gin")
        0
        """
        if (id is None) == (name is None):
            raise ValueError("Exactly one of 'id' or 'name' must be provided")

        if id is not None:
            if id not in self._id_to_idx:
                raise KeyError(f"Entity ID '{id}' not found in registry")
            return int(self._id_to_idx[id])
        else:
            # Lazy build name index on first name lookup
            if self._name_to_idx is None:
                self._name_to_idx = {
                    str(name): idx for idx, name in enumerate(self._names)
                }
            if name not in self._name_to_idx:
                raise KeyError(f"Entity name '{name}' not found in registry")
            return int(self._name_to_idx[name])

    def __len__(self) -> int:
        """Return the number of entities in the registry."""
        return len(self._ids)

    def __getitem__(self, index: int) -> tuple[str, str]:
        """
        Get (id, name) tuple for a matrix index.

        Parameters
        ----------
        index : int
            Matrix index (0-based).

        Returns
        -------
        tuple of str
            (entity_id, entity_name)

        Examples
        --------
        >>> registry = Registry([(0, "123", "Gin")])
        >>> registry[0]
        ('123', 'Gin')
        """
        if not 0 <= index < len(self):
            raise IndexError(f"Index {index} out of range [0, {len(self)})")
        return (str(self._ids[index]), str(self._names[index]))

    def validate_matrix(self, matrix: np.ndarray) -> None:
        """
        Validate that a matrix has compatible dimensions.

        Parameters
        ----------
        matrix : np.ndarray
            Square matrix to validate.

        Raises
        ------
        ValueError
            If matrix shape is incompatible with entity count.

        Examples
        --------
        >>> registry = Registry([(0, "123", "Gin"), (1, "456", "Vodka")])
        >>> registry.validate_matrix(np.zeros((2, 2)))  # OK
        >>> registry.validate_matrix(np.zeros((3, 3)))  # Raises ValueError
        """
        if len(matrix.shape) != 2:
            raise ValueError(f"Matrix must be 2-dimensional, got shape {matrix.shape}")
        if matrix.shape[0] != len(self) or matrix.shape[1] != len(self):
            raise ValueError(
                f"Matrix shape {matrix.shape} incompatible with "
                f"{len(self)} entities (expected ({len(self)}, {len(self)}))"
            )

    def to_id_to_index(self) -> dict[str, int]:
        """
        Export as {entity_id: matrix_index} dict for legacy compatibility.

        Returns
        -------
        dict of str to int
            Copy of the ID to index mapping.
        """
        return self._id_to_idx.copy()
