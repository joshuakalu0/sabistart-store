"""Custom exceptions for store settings."""


class SettingsError(Exception):
    """Base exception for settings-related errors."""
    pass


class SettingsNotFoundError(SettingsError):
    """Raised when settings record doesn't exist."""
    pass


class SettingsValidationError(SettingsError):
    """Raised when settings validation fails."""
    pass


class SettingsPermissionError(SettingsError):
    """Raised when user lacks permission to modify settings."""
    pass
