"""Module for integrating logging with Celery

Usage:
    >>> from celery import Celery
    >>> from thunderstorm.logging.celery import init_app as init_logging
    >>>
    >>> app = Celery('ts-service-name', broker=broker_cnx)
    >>> init_logging(app)
"""
import celery
import logging
from celery import Task as CeleryTask
from celery.signals import setup_logging
from celery._state import get_current_task

from . import (
    _register_id_getter, get_log_level, get_request_id,
    setup_ts_logger, ts_json_handler, ts_stream_handler, TS_REQUEST_ID
)

__all__ = ['init_app', 'TSCeleryTask']


class TSCeleryTask(CeleryTask):
    """Celery Task that adds request ID header
    This adds the request ID as a celery header so that it can be logged
    in celery task logs. Use it by setting it to the `Task` attribute of
    your celery app.
    """
    def apply_async(self, *args, **kwargs):
        kwargs.setdefault('headers', {})
        if kwargs['headers'] is None:
            kwargs['headers'] = {}
        kwargs['headers'][TS_REQUEST_ID] = get_request_id()

        return super().apply_async(*args, **kwargs)


class CeleryTaskFilter(logging.Filter):
    """Celery logging filter
    This adds in the task name and ID and also the request ID if it was
    added by the `CeleryRequestIDTask'
    """
    def filter(self, record):
        record.traceId = get_request_id()

        return record


def get_celery_request_id():
    """Return the request ID from the current Celery request

    If there is no request then return None.

    Importing this module will register this getter with ``get_request_id``.

    Returns:
        str or None: the current request ID
    """
    task = get_current_task()
    if task and task.request:
        return task.request.get(TS_REQUEST_ID)

    return None


def init_app(
    celery_app: celery.Celery, init_ts_logger: bool = False, add_json_handler: bool = True
):
    ts_service = celery_app.conf['TS_SERVICE_NAME']
    ts_service = ts_service.replace('-', '_')
    log_level = get_log_level(celery_app.conf['TS_LOG_LEVEL'])

    log_filter = CeleryTaskFilter()
    if init_ts_logger:
        logger = setup_ts_logger(ts_service, log_level)
        if add_json_handler:
            logger.addHandler(ts_json_handler('celery', ts_service, log_filter))
        else:
            logger.addHandler(ts_stream_handler(log_filter))

        logger.info('setting up ts_logger')

    def _setup_logger():
        def do_setup_logging(**kwargs):
            stream_handler = ts_stream_handler(log_filter)
            json_handler = ts_json_handler('celery', ts_service, log_filter) if add_json_handler else None

            celery.utils.log.task_logger = logger
            celery.utils.log.worker_logger = logger

        return do_setup_logging
    setup_logging.connect(_setup_logger(), weak=False)


_register_id_getter(get_celery_request_id)
