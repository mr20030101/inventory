"""Domain errors, turned into consistent JSON API errors."""
from __future__ import annotations


class DomainError(Exception):
    """A business rule or validation failure that the user can act on."""

    status_code = 400

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.code = code


class NotFound(DomainError):
    status_code = 404

    def __init__(self, what: str):
        super().__init__(f"{what} not found.", "not_found")


class Conflict(DomainError):
    status_code = 409

    def __init__(self, message: str, code: str = "conflict"):
        super().__init__(message, code)


class PermissionDenied(DomainError):
    status_code = 403

    def __init__(self, permission: str):
        super().__init__(f"You do not have permission to do this ({permission}).", "forbidden")
        self.permission = permission


class AuthError(DomainError):
    status_code = 401

    def __init__(self, message: str = "Please sign in again.", code: str = "unauthenticated"):
        super().__init__(message, code)
