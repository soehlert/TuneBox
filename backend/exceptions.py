"""Custom exceptions for the backend application."""


class PlexConnectionError(Exception):
    """Exception raised for Plex connection errors.

    Attributes:
        original_error (Optional[Exception]): The original exception that caused this error
    """

    default_message = "Failed to connect to Plex server"

    def __init__(self, original_error: Exception | None = None) -> None:
        """Initialize the PlexConnectionError.

        Args:
            original_error (Optional[Exception], optional): The original exception that caused this error.
                Defaults to None.
        """
        self.original_error = original_error
        super().__init__(self.default_message)
