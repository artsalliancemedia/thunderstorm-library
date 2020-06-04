from thunderstorm.flask.exceptions import AppException


class HTTPError(AppException):
    def __init__(self, message='Error', code=None):
        super().__init__(message)
        self.code = code

    def to_dict(self):
        return dict(message=self.message, status=self.code)


class BadRequest(HTTPError):
    def __init__(self, message='Bad Request'):
        super().__init__(message, code=400)


class Forbidden(HTTPError):
    def __init__(self, message='Forbidden'):
        super().__init__(message, code=403)


class NotFound(HTTPError):
    def __init__(self, message='Resource not found'):
        super().__init__(message, code=404)


class Conflict(HTTPError):
    def __init__(self, message='Resource conflict'):
        super().__init__(message, code=409)


class ServerError(HTTPError):
    def __init__(self, message='Internal Server Error'):
        super().__init__(message, code=500)
