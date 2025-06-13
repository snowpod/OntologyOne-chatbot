# utils/exceptions.py or just inline

class TooManyRequestsError(Exception):
    """Raised when the AI API returns a 429 Too Many Requests error."""
    pass
