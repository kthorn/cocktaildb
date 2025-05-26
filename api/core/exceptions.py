"""Custom exceptions for the CocktailDB API"""

from typing import Optional, Any, Dict


class CocktailDBException(Exception):
    """Base exception for CocktailDB API"""
    
    def __init__(self, message: str, status_code: int = 500, detail: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)


class DatabaseException(CocktailDBException):
    """Database-related exceptions"""
    
    def __init__(self, message: str = "Database operation failed", detail: Optional[str] = None):
        super().__init__(message, status_code=500, detail=detail)


class ValidationException(CocktailDBException):
    """Validation-related exceptions"""
    
    def __init__(self, message: str = "Validation failed", detail: Optional[str] = None):
        super().__init__(message, status_code=400, detail=detail)


class NotFoundException(CocktailDBException):
    """Resource not found exceptions"""
    
    def __init__(self, message: str = "Resource not found", detail: Optional[str] = None):
        super().__init__(message, status_code=404, detail=detail)


class AuthenticationException(CocktailDBException):
    """Authentication-related exceptions"""
    
    def __init__(self, message: str = "Authentication failed", detail: Optional[str] = None):
        super().__init__(message, status_code=401, detail=detail)


class AuthorizationException(CocktailDBException):
    """Authorization-related exceptions"""
    
    def __init__(self, message: str = "Access denied", detail: Optional[str] = None):
        super().__init__(message, status_code=403, detail=detail)


class ConflictException(CocktailDBException):
    """Resource conflict exceptions"""
    
    def __init__(self, message: str = "Resource conflict", detail: Optional[str] = None):
        super().__init__(message, status_code=409, detail=detail)