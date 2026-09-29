"""Transport-independent errors shared by platform services."""


class ServiceError(Exception):
    """A domain operation cannot be completed."""


class NotFoundError(ServiceError):
    """A requested domain record does not exist."""


class ConflictError(ServiceError):
    """The requested mutation conflicts with stored state."""


class InvalidOperationError(ServiceError):
    """A domain input or operation is invalid."""
