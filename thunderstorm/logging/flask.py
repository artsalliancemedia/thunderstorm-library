"""Module for integrating logging with Flask

Usage:
    >>> from flask import Flask
    >>> from thunderstorm.logging.flask import init_app as init_logging
    >>>
    >>> app = Flask(__init__)
    >>> init_logging(app)
"""
import logging
from flask import g, request, Flask
from flask.ctx import has_request_context

from . import (
    _register_id_getter, get_log_level, get_request_id,
    setup_ts_logger, ts_json_handler, ts_stream_handler, TS_REQUEST_ID
)

__all__ = ['init_app']


class FlaskRequestIDFilter(logging.Filter):
    def filter(self, record):
        record.traceId = get_request_id()

        return record


def get_flask_request_id():
    """Return the request ID from the Flask request context

    If there is a Flask request context but there is no ``request_id``
    then first we look for a ``TS-Request-ID`` header. If that is also
    not there we generate a new string uuid4.

    Importing this module will register this getter with ``get_request_id``.

    Returns:
        str: the current request ID
    """
    if has_request_context():
        if TS_REQUEST_ID in request.headers:
            return request.headers[TS_REQUEST_ID]

        if 'request_id' in g:
            return g.request_id

    return None


def init_app(
        flask_app: Flask, add_json_handler: bool = True
):
    """Initialise logging request handler on a Flask app
    This handler adds a Flask access log
    """
    ts_service = flask_app.config['TS_SERVICE_NAME']
    ts_service = ts_service.replace('-', '_')
    log_level = get_log_level(flask_app.config['TS_LOG_LEVEL'])

    log_filter = FlaskRequestIDFilter()

    del flask_app.logger.handlers[:]
    flask_app.logger.name = ts_service
    flask_app.logger.setLevel(log_level)

    logger = setup_ts_logger(ts_service, log_level)
    if add_json_handler:
        json_handler = ts_json_handler(
            'flask', ts_service, log_filter
        )
        logger.addHandler(json_handler)

    else:
        stream_handler = ts_stream_handler(log_filter)
        logger.addHandler(stream_handler)
    flask_app.logger = logger

    @flask_app.before_request
    def before_request():
        g.request_id = get_request_id()

    @flask_app.after_request
    def after_request(response):
        level = logging.ERROR if response.status_code // 100 == 5 else logging.INFO
        extra = {
            'method': request.method, 'url': request.url, 'status': response.status_code
        }
        logger.log(
            level, '{method} {url} {status}'.format(**extra)
        )
        response.headers[TS_REQUEST_ID] = g.request_id

        return response


_register_id_getter(get_flask_request_id)
