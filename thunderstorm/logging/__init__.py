import uuid
import logging
import datetime
from pythonjsonlogger.jsonlogger import JsonFormatter as BaseJSONFormatter
""" You probably do not want to use this directly.
See:
    thunderstorm.logging.flask
    thunderstorm.logging.celery
    thunderstorm.logging.kafka
"""

__all__ = [
    'get_request_id', 'ts_json_handler', 'ts_stream_handler', 'JSONFormatter'
]


_REQUEST_ID_GETTERS = []
TS_REQUEST_ID = 'TS-Request-ID'
TS_LOGGER_FORMAT_STR = '%(asctime)s %(levelname)s %(traceId)s %(process)d {}'.format(
    '%(thread)d %(pathname)s:%(lineno)d %(message)s'
)

LOGGING_LEVEL_MAPPER = {
    'INFO': logging.INFO, 'DEBUG': logging.DEBUG, 'NOTSET': logging.NOTSET,
    'CRITICAL': logging.CRITICAL, 'ERROR': logging.ERROR, 'WARNING': logging.WARNING
}


def get_log_level(level_str):
    if not level_str:
        raise ValueError('Invalid logging level')

    level_str = level_str.upper()
    if level_str not in LOGGING_LEVEL_MAPPER.keys():
        raise ValueError(f'The logging level {level_str} is not support')

    return LOGGING_LEVEL_MAPPER[level_str]


def _register_id_getter(getter):
    _REQUEST_ID_GETTERS.append(getter)


def gen_trace_id():
    """Return an unique trace id base on uuid4"""
    _trace_id = str(uuid.uuid4())

    return _trace_id.replace('-', '')


def get_request_id():
    """Return the current request ID

    Return the current request ID from whichever ID getters have been
    registered. An ID getter is registered when it's module is included.
    For example; if the ``thunderstorm.logging.flask`` module is imported
    the ``get_flask_request_id`` is registered.

    Returns:
        str the current request ID
    """
    for getter in _REQUEST_ID_GETTERS:
        request_id = getter()
        if request_id:
            return request_id

    return gen_trace_id()


def ts_json_handler(ts_filter):
    """Create an json handler"""
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(JSONFormatter(
        '%(levelname)s %(message)s',
    ))
    stream_handler.addFilter(ts_filter)

    return stream_handler


def ts_stream_handler(ts_filter):
    """Create an stream handler"""
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        logging.Formatter(TS_LOGGER_FORMAT_STR)
    )
    stream_handler.addFilter(ts_filter)
    return stream_handler


def setup_ts_logger(ts_service, log_level):
    logger = logging.getLogger(ts_service)
    logger.propagate = True

    logger.setLevel(log_level)
    return logger


class JSONFormatter(BaseJSONFormatter):
    """JSON logging Formatter for Thunderstorm apps

    Adds thunderstorm fields to JSON logging
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record = self._add_required_fields(log_record, record)
        log_record = self._add_request_id(log_record, record)
        log_record = self._add_timestamp(log_record, record)

    def _add_required_fields(self, log_record, record):
        required_fields = ['name', 'levelname', 'pathname', 'lineno']
        log_record.update({name: getattr(record, name) for name in required_fields})

        return log_record

    def _add_request_id(self, log_record, record):
        if getattr(record, 'traceId', None):
            log_record['request_id'] = record.traceId
            log_record.setdefault('data', {})
            log_record['data']['request_id'] = record.traceId

        return log_record

    def _add_timestamp(self, log_record, record):
        log_record['timestamp'] = datetime.datetime.utcnow().isoformat()

        return log_record
