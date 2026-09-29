"""Reusable platform operations: callers own sessions and ordinary commits.

Services may flush but never commit, except existing atomic DB transition
primitives invoked by a service. HTTP binding and error mapping stay in routes.
"""


class ServiceError(Exception):
    """A domain operation cannot be completed."""


class NotFoundError(ServiceError):
    """A requested domain record does not exist."""


class ConflictError(ServiceError):
    """The requested mutation conflicts with stored state."""


class InvalidOperationError(ServiceError):
    """A domain input or operation is invalid."""
