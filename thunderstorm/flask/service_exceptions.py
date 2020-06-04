from thunderstorm.flask.exceptions import AppException


class ServiceException(AppException):
    def __init__(self, code, message):
        self.code = code
        self.message = message


class CheckFeatureDependenceFail(ServiceException):
    def __init__(self, message, code=400):
        super().__init__(code, message)


class ResourceNotFound(ServiceException):
    def __init__(self, message, code=404):
        super().__init__(code, message)


class CheckFeatureInOrgFail(ServiceException):
    def __init__(self, message, code=403):
        super().__init__(code, message)


class ResourceConflict(ServiceException):
    def __init__(self, message, code=409):
        super().__init__(code, message)


class Invalid(ServiceException):
    def __init__(self, message, code=400):
        super().__init__(code, message)
