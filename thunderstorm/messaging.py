"""Thunderstorm messaging helpers"""
from functools import wraps
import collections

from marshmallow.exceptions import ValidationError
from celery.utils.log import get_task_logger
from celery import current_app, shared_task
from statsd.defaults.env import statsd

from thunderstorm.shared import SchemaError, ts_task_name


logger = get_task_logger(__name__)


class TSMessage(collections.abc.Mapping):
    def __init__(self, data, metadata):
        self.data = data
        self.metadata = metadata

    def __getitem__(self, key):
        return self.data[key]

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        return iter(self.data)


def ts_shared_task(*options, **kwoptions):
    """ wrapper function for celery.shared_task with statsd timer to calculate task time

    use as celery.shared_task

    Example:
        @ts_shared_task()
        def add(a, b):
            pass

        @ts_shared_task(bind=True)
        def mul(self, a, b):
            pass

    """
    def decorator(func):

        @wraps(func)
        def _timing_wrapper(*args, **kwargs):
            with statsd.timer(f"consumer.celery.{func.__name__}.time"):
                return func(*args, **kwargs)

        return shared_task(*options, **kwoptions)(_timing_wrapper)

    return decorator


def ts_task(event_name, schema, bind=False, **options):
    """Decorator for Thunderstorm messaging tasks

    The task name is derived from the event name.

    See: ts_task_name

    Example:
        @ts_task('domain.action.request', schema=DomainActionRequestSchema())
        def handle_domain_action_request(message):
            # do something with validated message

    Args:
        event_name (str): The event name (this is also the routing key)
        schema (marshmallow.Schema): The schema instance expected by this task
        bind (bool): if the task is bound
        options (dict): extra options to be passed to the shared_task decorator

    Returns:
        A decorator function
    """
    def decorator(task_func):
        task_name = ts_task_name(event_name)

        def task_handler(*args):
            """
            args can contain up to 2 items:
            * if a bound task the first arg will be self and the second will be message
            * if an unbound task, only one arg will be present and that will be the message

            @ts_task(bind=True)
            def task_a(self, message):
                return message

            @ts_task
            def task_b(message):
                return message
            """
            # if only one argument then it's not a bound task, if two then it is
            # more than 2 args are not allowed
            if len(args) == 1:
                return _task_handler(message=args[0])
            elif len(args) == 2:
                return _task_handler(self=args[0], message=args[1])
            else:
                raise NotImplementedError('Maximum 2 parameters allowed for ts_task decorator')

        def _task_handler(self=None, message=None):
            ts_message = TSMessage(message.pop('data'), message)
            try:
                deserialized_data = schema.load(ts_message)
            except ValidationError as vex:
                statsd.incr(f'counter.parse.{task_name}.error')
                error_msg = 'inbound schema validation error for event {}'.format(event_name)
                logger.error(error_msg, extra={'errors': vex.messages, 'data': ts_message})
                raise SchemaError(error_msg, errors=vex.messages, data=ts_message)
            else:
                logger.info('received ts_task on {}'.format(event_name))
                ts_message.data = deserialized_data
                # passing task_func instead of passing self - @will-norris
                with statsd.timer(f"consumer.celery.{event_name}.time"):
                    return task_func(self, ts_message) if bind else task_func(ts_message)

        return shared_task(bind=bind, name=task_name, **options)(task_handler)

    return decorator


def send_ts_task(event_name, schema, data, **kwargs):
    """Send a Thunderstorm messaging event

    The correct task name is derived from the event name.

    Example:
        send_ts_task(
            'domain.action.request', DomainActionRequestSchema(),
            payload
        )

    Args:
        event_name (str): The event name (this is also the routing key)
        schema (marshmallow.Schema): The schema instance the payload must
                                     comply to
        data (dict or list): The event data to be emitted (does not need to be serialized yet)

    Raises:
        SchemaError If schema validation fails.

    Returns:
        The result of the send_task call.
    """

    if {'name', 'args', 'exchange', 'routing_key'} & set(kwargs.keys()):
        raise ValueError('Cannot override name, args, exchange or routing_key')
    task_name = ts_task_name(event_name)

    try:
        data = schema.dump(data)
    except ValidationError as vex:
        error_msg = 'Error serializing queue message data'
        raise SchemaError(error_msg, errors=vex.messages, data=data)

    try:
        schema.load(data)
    except ValidationError as vex:
        error_msg = 'Outbound schema validation error for event {}'.format(event_name)
        logger.error(error_msg, extra={'errors': vex.messages, 'data': data})
        statsd.incr(f'counter.kafka_write.{task_name}.schema_error')
        raise SchemaError(error_msg, errors=vex.messages, data=data)

    logger.info('send_ts_task on {}'.format(event_name))
    event = {
        'data': data
    }
    return current_app.send_task(
        task_name,
        (event,),
        exchange='ts.messaging',
        routing_key=event_name,
        **kwargs
    )
