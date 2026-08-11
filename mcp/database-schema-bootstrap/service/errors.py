from __future__ import annotations


class GatewayError(RuntimeError):
    """Base class for errors safe to handle at the service boundary."""


class ConfigError(GatewayError):
    """The project profile is missing, invalid, or unsupported."""


class CredentialError(GatewayError):
    """The operating-system credential could not be read."""


class PolicyError(GatewayError):
    """A service input violates the metadata-only policy."""


class MetadataError(GatewayError):
    """PostgreSQL metadata access failed without exposing driver details."""

