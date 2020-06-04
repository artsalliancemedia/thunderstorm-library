class DeserializationError(Exception):
    def __init__(self, message):
        self.message = message


class SerializationError(Exception):
    def __init__(self, message):
        self.message = message


class AppException(Exception):
    """
    Base exception for application that accepts text or an exception inherited from this class
    """
    def __init__(self, message=None):
        self.message = str(message)
        self.error_params = dict()

    def __str__(self):
        return self.message
