class LocalModelError(Exception):
    """Base class for local LLM failures."""

    pass


class ModelLoadError(LocalModelError):
    """Raised by :meth:`LocalRunner.load` when binary or model cannot be found."""
    pass


class ModelNotReadyError(LocalModelError):
    """Raised when an operation requires a loaded model but it is not ready."""
    pass


class ModelTimeoutError(LocalModelError):
    """Raised when :meth:`LocalRunner.call` exceeds the configured timeout."""
    pass


class ModelCallError(LocalModelError):
    """Raised for non‑zero exit status of the model binary."""
    pass
