import json
from unittest.mock import patch, MagicMock

import pytest
from faust import App as faust_app

from thunderstorm.kafka_messaging import (
    TSKafka, TSKafkaSendException, TSKafkaConnectException
)
from thunderstorm.shared import SchemaError


def test_TSKafka_init_raises_KeyError_for_missing_broker():
    # act
    with pytest.raises(KeyError) as exc:
        TSKafka('test-service')
    # assert
    assert "KeyError: 'broker'" in str(exc)


def test_TSKafka_init_sets_kafka_producer_to_None(kafka_app):
    assert isinstance(kafka_app, faust_app)
    assert kafka_app.kafka_producer is None


@patch('thunderstorm.kafka_messaging.get_request_id')
def test_TSKafka_validate_data_returns_data(get_request_id, kafka_app, TestEvent):
    # arrange
    data = {'int_1': 3, 'int_2': 6}
    get_request_id.return_value = 'abcd_trace_id'

    # act
    validated_data = kafka_app.validate_data(data, TestEvent)

    # assert
    assert json.loads(validated_data) == {'data': data, 'trace_id': 'abcd_trace_id', "compressed": False}


def test_TSKafka_send_ts_event_gets_kafka_producer_and_calls_send(kafka_app, TestEvent):  # noqa
    # arrange
    test_kafka_producer = MagicMock()

    data = {'int_1': 3, 'int_2': 6}

    # act
    with patch.object(
        kafka_app, 'get_kafka_producer', return_value=test_kafka_producer
    ) as mock_get_kafka_producer:
        kafka_app.send_ts_event(data, TestEvent)

    # assert
    mock_get_kafka_producer.assert_called_once()
    assert test_kafka_producer.send.called


def test_TSKafka_send_ts_event_if_send_raises_error_throw_TSKafkaSendException(
    kafka_app, TestEvent, TestException
):
    # arrange
    test_kafka_producer = MagicMock()
    test_kafka_producer.send.side_effect = TestException

    data = {'int_1': 3, 'int_2': 6}

    # act
    with patch.object(
        kafka_app, 'get_kafka_producer', return_value=test_kafka_producer
    ) as mock_get_kafka_producer:
        with pytest.raises(TSKafkaSendException):
            kafka_app.send_ts_event(data, TestEvent)

    # assert
    mock_get_kafka_producer.assert_called_once()


def test_TSKafka_send_ts_event_gets_kafka_producer_and_calls_send_with_compress(kafka_app, TestEvent):  # noqa
    # arrange
    test_kafka_producer = MagicMock()

    data = {'int_1': 3, 'int_2': 6}

    # act
    with patch.object(
        kafka_app, 'get_kafka_producer', return_value=test_kafka_producer
    ) as mock_get_kafka_producer:
        kafka_app.send_ts_event(data, TestEvent, compression=True)

    # assert
    mock_get_kafka_producer.assert_called_once()
    assert test_kafka_producer.send.called


def test_TSKafka_send_ts_event_if_send_raises_error_throw_TSKafkaSendException_with_compress(
    kafka_app, TestEvent, TestException
):
    # arrange
    test_kafka_producer = MagicMock()
    test_kafka_producer.send.side_effect = TestException

    data = {'int_1': 3, 'int_2': 6}

    # act
    with patch.object(
        kafka_app, 'get_kafka_producer', return_value=test_kafka_producer
    ) as mock_get_kafka_producer:
        with pytest.raises(TSKafkaSendException):
            kafka_app.send_ts_event(data, TestEvent, compression=True)

    # assert
    mock_get_kafka_producer.assert_called_once()


def test_TSKafka_get_kafka_producer_raises_TSKafkaConnectException_if_no_real_brokers(kafka_app):  # noqa
    # act/assert
    with pytest.raises(TSKafkaConnectException):
        kafka_app.get_kafka_producer()


@pytest.mark.asyncio
async def test_TSKafka_ts_event_calls_wrapped_function(kafka_app, TestEvent):
    # arrange
    message = {'data': {'int_1': 3, 'int_2': 6}}

    # decorated agent
    @kafka_app.ts_event(TestEvent)
    async def test_function(message):
        return message

    # act
    async with test_function.test_context() as agent:
        event = await agent.put(message.copy())

    # assert
    assert agent.results[event.message.offset] == message.pop('data')


@pytest.mark.asyncio
async def test_TSKafka_ts_event_does_not_raise_if_catch_exc_set_and_logs_error(kafka_app, TestEvent):
    # arrange
    message = {'data': {'int_1': 3, 'int_2': 6}}

    # decorated agent
    @kafka_app.ts_event(TestEvent, catch_exc=ValueError)
    async def test_function(message):
        raise ValueError()

    # act
    async with test_function.test_context() as agent:
        with patch('thunderstorm.kafka_messaging.logging') as m_logging:
            await agent.put(message.copy())

    assert m_logging.error.called


@pytest.mark.asyncio
async def test_TSKafka_ts_event_increases_metric_count_and_raises_SchemaError_for_bad_data(kafka_app, TestEvent):
    # arrange
    kafka_app.monitor = MagicMock()

    message = {'data': {'int_1': 'not_an_int', 'int_2': 6}}

    # decorated agent
    @kafka_app.ts_event(TestEvent)
    async def test_function(message):
        return message

    # act
    with patch("thunderstorm.kafka_messaging.statsd") as mock_statsd:
        with pytest.raises(SchemaError):
            async with test_function.test_context() as agent:
                await agent.put(message.copy())

    assert mock_statsd.incr.called


@pytest.mark.asyncio
async def test_TSKafka_ts_event_with_compress(kafka_app, TestEvent):
    # arrange
    data = {'int_1': 3, 'int_2': 6}
    message = {'data': data}

    # decorated agent
    @kafka_app.ts_event(TestEvent)
    async def test_function(message):
        return message

    # act
    async with test_function.test_context() as agent:
        msg = {"data": TSKafka._compress(data, TestEvent.schema), "compressed": True}
        event = await agent.put(msg)

    # assert
    assert agent.results[event.message.offset] == message.pop('data')
