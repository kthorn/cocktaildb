"""Custom exceptions for the CocktailDB API"""


class CocktailDBException(Exception):
    """Base exception for CocktailDB API"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        detail: str | list[str] | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)


class DatabaseException(CocktailDBException):
    """Database-related exceptions"""

    def __init__(
        self, message: str = "Database operation failed", detail: str | None = None
    ):
        super().__init__(message, status_code=500, detail=detail)


class ValidationException(CocktailDBException):
    """Validation-related exceptions"""

    def __init__(self, message: str = "Validation failed", detail: str | None = None):
        super().__init__(message, status_code=400, detail=detail)


class NotFoundException(CocktailDBException):
    """Resource not found exceptions"""

    def __init__(self, message: str = "Resource not found", detail: str | None = None):
        super().__init__(message, status_code=404, detail=detail)


class ConflictException(CocktailDBException):
    """Resource conflict exceptions"""

    def __init__(
        self,
        message: str = "Resource conflict",
        detail: str | list[str] | None = None,
    ):
        super().__init__(message, status_code=409, detail=detail)
