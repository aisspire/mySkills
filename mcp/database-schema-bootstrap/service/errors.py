from __future__ import annotations


class GatewayError(RuntimeError):
    """Base class for errors safe to handle at the service boundary."""


class ConfigError(GatewayError):
    """A strict v2 runtime or project configuration is unavailable."""


class PolicyError(GatewayError):
    """A service input violates the metadata-only policy."""


class MetadataError(GatewayError):
    """PostgreSQL metadata access failed without exposing driver details."""


class ConnectionUnavailableError(GatewayError):
    """The requested connection is not usable by the current project."""
