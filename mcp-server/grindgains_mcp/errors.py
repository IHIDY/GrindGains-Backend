class GrindGainsError(Exception):
    """Base class; messages are safe to show to the user (they never contain tokens)."""


class LoginError(GrindGainsError):
    pass


class NotLoggedInError(GrindGainsError):
    pass


class ReLoginRequiredError(GrindGainsError):
    pass


class ApiError(GrindGainsError):
    pass


class CognitoError(GrindGainsError):
    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
