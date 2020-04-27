import base64
import collections
import logging
import zlib
import json
import marshmallow  # TODO: @will-norris backwards compat - remove
import sentry_sdk

from faust.sensors.monitor import Monitor
from faust.sensors.statsd import StatsdMonitor
from faust.types import StreamT, TP, Message
from faust import current_event, App
from kafka import KafkaProducer
from kafka.errors import MessageSizeTooLargeError
from marshmallow import Schema, fields
from marshmallow.exceptions import ValidationError
from typing import Any

from thunderstorm.logging import get_request_id
from thunderstorm.shared import SchemaError, ts_task_name
from thunderstorm.logging.kafka import KafkaRequestIDFilter
from thunderstorm.logging import get_log_level, setup_ts_logger

MARSHMALLOW_2 = int(marshmallow.__version__[0]) < 3

# Keep topic names and schemas together
Event = collections.namedtuple('Event', ['topic', 'schema'])


class TSMessageSizeTooLargeError(MessageSizeTooLargeError):
    pass


class TSKafkaSendException(Exception):
    pass


class TSKafkaConnectException(Exception):
    pass


class TSStatsdMonitor(StatsdMonitor):
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 8125,
        prefix: str = 'x.faust',
        rate: float = 1.0,
        **kwargs: Any
    ) -> None:
        super().__init__(host=host, port=port, prefix=f'{prefix}.faust', rate=rate, **kwargs)

    def _stream_label(self, stream: StreamT) -> str:
        """
        Enhance original _stream_label function
        it converts "topic_pos-week.fetch" -> "pos-week_fetch"
        """
        label = super()._stream_label(stream=stream)
        return label.replace('topic_', '').replace('.', '_')

    def on_message_in(self, tp: TP, offset: int, message: Message) -> None:
        """Call before message is delegated to streams."""
        super(Monitor, self).on_message_in(tp, offset, message)

        topic = tp.topic.replace('.', '_')
        self.client.incr('messages_received', rate=self.rate)
        self.client.incr('messages_active', rate=self.rate)
        self.client.incr(f'topic.{topic}.messages_received', rate=self.rate)
        self.client.gauge(f'read_offset.{topic}.{tp.partition}', offset)


class TSKafka(App):
    """
    Wrapper class for combining features of faust and Kafka-Python. The broker
    argument can be passed as a string of the form 'kafka-1:9092,kafka-2:9092'
    and the construcor will format the string as required by faust.
    """

    def __init__(self, *args, **kwargs):
        self.broker = kwargs['broker']
        self.kafka_producer = None
        self.max_request_size = kwargs.get('max_request_size', 10485760)  # default 10M
        kwargs['broker'] = ';'.join([f'kafka://{broker}' for broker in kwargs['broker'].split(',')])
        # overriding default value of 40.0 to make it bigger that the broker_session_timeout
        # see https://github.com/robinhood/faust/issues/259#issuecomment-487907514
        kwargs['broker_request_timeout'] = 90.0

        ts_service = kwargs.get('ts_service_name')
        self._ts_service = ts_service
        if not ts_service:
            logging.warning('ts_service_name is not given, logger will not be unified.')
        else:
            ts_service = ts_service.replace('-', '_')
            self._ts_service = ts_service

            ts_log_level = kwargs.get('ts_log_level')

            if not ts_log_level:
                ts_log_level = 'INFO'
                logging.warning('ts_log_level is not given, set to INFO as default.')

            try:
                get_log_level(ts_log_level)  # for verify
                log_level = ts_log_level.upper()
            except ValueError as vex:
                log_level = 'INFO'
                logging.warning(f'{log_level} {vex}')

            if kwargs.get('init_ts_logger'):
                setup_ts_logger(ts_service, log_level)

            log_filter = KafkaRequestIDFilter()
            logger = logging.getLogger(ts_service)
            logger.addFilter(log_filter)

        # sentry config
        dsn, environment, release = [
            kwargs.pop(kwarg, None) for kwarg in ['sentry_dsn', 'environment', 'release']
        ]
        self.sentry = self._init_sentry(dsn, environment, release)

        super().__init__(*args, **kwargs)

    def _init_sentry(self, dsn, environment=None, release=None):
        if dsn is None:
            return None
        return sentry_sdk.init(dsn=dsn, environment=environment, release=release)

    def validate_data(self, data, event, compression=False):
        """
        Validate message data by dumping to a string and loading it back

        Args:
            data (dict): Message to be serialized
            event (namedtuple): Contains topic and schema
            compression (boolean): Whether or not to compress a message

        Returns:
            bytes: Serialized message

        Raises:
            SchemaError: If message validation fails for any reason
        """
        if compression:
            data = self._compress(data, event.schema)

        class TSMessageSchema(Schema):
            if compression:
                data = fields.String(required=True)
            else:
                data = fields.Nested(event.schema)
            trace_id = fields.String(required=False, default=None)
            compressed = fields.Boolean(required=False, default=False)

        schema = TSMessageSchema()

        # Marshmallow 2 compatibility - remove when no longer needed
        trace_id = get_request_id()
        dumps_data = {'data': data, 'trace_id': trace_id, "compressed": compression}
        if MARSHMALLOW_2:
            serialized_data, errors = schema.dumps(dumps_data)

            if errors:
                error_msg = 'Error serializing queue message data.'
                logging.error(error_msg, extra={'errors': errors, 'data': data, 'trace_id': trace_id})
                raise SchemaError(error_msg, errors=errors, data=data)
            else:
                data = serialized_data

            errors = schema.loads(data).errors

            if errors:
                error_msg = f'Outbound schema validation error for event {event.topic}'
                logging.error(error_msg, extra={'errors': errors, 'data': data})
                raise SchemaError(error_msg, errors=errors, data=data)
        else:
            try:
                data = schema.dumps(dumps_data)
            except ValidationError as vex:
                error_msg = 'Error serializing queue message data'
                logging.error(error_msg, extra={'errors': vex.messages, 'data': data, 'trace_id': trace_id})
                raise SchemaError(error_msg, errors=vex.messages, data=data)

            try:
                schema.loads(data)
            except ValidationError as vex:
                error_msg = f'Outbound schema validation error for event {event.topic}'
                logging.error(error_msg, extra={'errors': vex.messages, 'data': data})
                raise SchemaError(error_msg, errors=vex.messages, data=data)

        return data.encode('utf-8')

    def send_ts_event(self, data, event, key=None, compression=False, log_payload=True):
        """
        Send a message to a kafka broker. We only connect to kafka when first
        sending a message.

        Args:
            event (namedtuple): Has attributes schema and topic
            data (dict): Message you want to send via the message bus
            key (str): Key to use when routing messages to a partition - It is
            compression (boolean): Whether or not to compress a message
            log_payload (boolean): switch of log the whole message

            recommended you use the resource identifier so all messages relating
            to a particular resource get routed to the same partition. A value of
            None will cause messages to randomly sent to different partitions
        """
        serialized = self.validate_data(data, event, compression)
        topic_name = event.topic.replace('.', '_')

        if not self.kafka_producer:
            self.kafka_producer = self.get_kafka_producer()

        try:
            self.kafka_producer.send(event.topic, value=serialized, key=key)  # send takes raw bytes
            logger = logging.getLogger(self._ts_service)
            msg = f'sent ts_event:{event.topic} '
            msg = msg + f',message:{data}' if log_payload else msg
            logger.info(msg)
            if hasattr(self.monitor, 'client'):
                self.monitor.client.incr(f'stream.{topic_name}.messages.sent')
        except MessageSizeTooLargeError as msex:
            raise TSMessageSizeTooLargeError(
                f"The message is bytes when serialized which is larger than"
                f" the total memory buffer you have configured with the"
                f" buffer_memory configuration. {msex}"
            )
        except Exception as ex:
            raise TSKafkaSendException(f'Exception while pushing message to broker: {ex}')

    def get_kafka_producer(self):
        """
        Return a KafkaProducer instance with sensible defaults
        """
        try:
            return KafkaProducer(
                bootstrap_servers=self.broker,
                connections_max_idle_ms=60000,
                max_in_flight_requests_per_connection=25,
                max_request_size=self.max_request_size,
                key_serializer=lambda x: x.encode() if x else None
            )
        except Exception as ex:
            raise TSKafkaConnectException(f'Exception while connecting to Kafka: {ex}')

    def ts_event(self, event, catch_exc=(), log_payload=True, *args, **kwargs):
        """Decorator for Thunderstorm messaging events

        Examples:
            @ts_event(Event('domain.action.request', DomainActionRequestSchema))
            async def handle_domain_action_request(message):
                # do something with validated message

        Args:
            topic (str): The topic name
            schema (marshmallow.Schema): The schema class expected by this task
            catch_exc (tuple): Tuple of exception classes which can be
                logged as errors and then ignored
            log_payload (boolean): Whether or not log the payload received

        Returns:
            A decorator function
        """
        topic = event.topic
        schema = event.schema()
        topic_name = topic.replace('.', '_')

        def decorator(func):
            async def event_handler(stream):
                # stream handling done in here, no need to do it inside the func
                async for message in stream:
                    logger = logging.getLogger(self._ts_service)
                    try:
                        event_meta = current_event().message
                        logger.info(f'received event:{topic}, meta: {event_meta}')
                        ts_message = message.pop('data') or message
                        compression = message.pop('compressed', False)
                        if compression:
                            ts_message = zlib.decompress(base64.b64decode(ts_message.encode()))
                            load_func = schema.loads
                        else:
                            load_func = schema.load
                        if MARSHMALLOW_2:
                            deserialized_data, errors = load_func(ts_message)
                            if errors:
                                if hasattr(self.monitor, 'client'):
                                    self.monitor.client.incr(f'stream.{topic_name}.schema.errors')
                                error_msg = f'Inbound schema validation error for event {topic}'
                                logging.error(error_msg, extra={'errors': errors, 'data': ts_message})
                                raise SchemaError(error_msg, errors=errors, data=ts_message)
                        else:
                            try:
                                deserialized_data = load_func(ts_message)
                            except ValidationError as vex:
                                if hasattr(self.monitor, 'client'):
                                    self.monitor.client.incr(f'stream.{topic_name}.schema.errors')
                                error_msg = f'Inbound schema validation error for event {topic}'
                                logging.error(error_msg, extra={'errors': vex.messages, 'data': ts_message})
                                raise SchemaError(error_msg, errors=vex.messages, data=ts_message)

                        msg_meta = f'ts_event:{event.topic}, meta:{event_meta}'
                        msg = f'received {msg_meta}' + (f',message:{deserialized_data}' if log_payload else '')
                        logger.info(msg)
                        yield await func(deserialized_data)
                        logger.info(f'finished consumer {msg_meta}')
                    except catch_exc as ex:
                        if hasattr(self.monitor, 'client'):
                            self.monitor.client.incr(f'stream.{topic_name}.execution.errors')
                        logging.error(ex, exc_info=ex)
                        if self.sentry:
                            sentry_sdk.capture_exception(ex)
                        yield
                    except Exception as ex:  # catch all exceptions to avoid worker failure and restart
                        if hasattr(self.monitor, 'client'):
                            self.monitor.client.incr(f'stream.{topic_name}.critical.errors')
                        logging.critical(ex, exc_info=ex)
                        if self.sentry:
                            sentry_sdk.capture_exception(ex)
                        raise ex
                        # yield

            return self.agent(topic, name=f'thunderstorm.messaging.{ts_task_name(topic)}')(event_handler)

        return decorator

    @classmethod
    def _compress(cls, data, schema):
        if MARSHMALLOW_2:
            compress_data = zlib.compress(json.dumps(data).encode())
        else:
            compress_data = zlib.compress(schema().dumps(data).encode())
        return base64.b64encode(compress_data).decode()
