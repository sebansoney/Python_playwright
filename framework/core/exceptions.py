"""Framework-specific exceptions.

Having our own types lets tests and hooks tell *framework/infrastructure* problems
apart from genuine product defects (which surface as AssertionError).
"""


class FrameworkError(Exception):
    """Base class for every error raised by the framework itself."""


class ConfigurationError(FrameworkError):
    """Configuration is missing, invalid or inconsistent."""


class AppNotReachableError(FrameworkError):
    """The application under test did not become available in time."""
