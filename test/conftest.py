from os import environ
from unittest.mock import MagicMock

import flask
from factory.alchemy import SQLAlchemyModelFactory
from marshmallow import fields, Schema
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
import sqlalchemy_utils as sa_utils

from thunderstorm.flask.headers import deprecated
from thunderstorm.flask.schemas import PaginationSchema
from thunderstorm.kafka_messaging import TSKafka, Event
from test import models
import test.fixtures


@pytest.fixture
def TestSchema():
    class TestSchema(Schema):
        int_1 = fields.Integer()
        int_2 = fields.Integer()

    return TestSchema


@pytest.fixture
def TestException():
    class TestException(Exception):
        def __init__(self, message):
            self.message = message

    return TestException


@pytest.fixture
def flask_app(mock_query):
    app = flask.Flask('test_app')

    @app.route('/past')
    @deprecated(deadline='2012-12-12')
    def past():
        return 'ok'

    @app.route('/future')
    @deprecated(deadline='2050-05-05')
    def future():
        return 'ok'

    @app.route('/none')
    @deprecated
    def none():
        return 'ok'

    return app


@pytest.fixture
def celery(celery_app):
    celery_app.conf.broker_transport_options = {
        'confirm_publish': True,  # optional, not affecting celery hang up
        'max_retries': 3,
        'interval_start': 0,
        'interval_step': 0.1,
        'interval_max': 0.2,
    }

    # set as current so the current_app proxy works
    celery_app.set_current()

    return celery_app


@pytest.fixture
def mock_query():
    query = MagicMock()
    query.count.return_value = 50

    def query_maker(num_items):
        return [
            {'int_1': 1, 'int_2': 2} for _ in range(num_items)
        ]

    query.offset.return_value.limit = query_maker

    return query


@pytest.fixture
def TestSchemaList(TestSchema):
    class TestSchemaList(PaginationSchema):
        data = fields.List(fields.Nested(TestSchema))

    return TestSchemaList


#############################################################
# DB FIXTURES
#############################################################


@pytest.fixture(scope='session')
def db_uri():
    db_name = environ['DB_NAME']
    db_host = environ['DB_HOST']
    db_user = environ['DB_USER']
    db_pass = environ['DB_PASS']
    return 'postgresql://{}:{}@{}:5432/{}'.format(db_user, db_pass, db_host, db_name)


@pytest.fixture(scope='session')
def test_database(db_uri):
    if sa_utils.database_exists(db_uri):
        sa_utils.drop_database(db_uri)

    sa_utils.create_database(db_uri)

    engine = create_engine(db_uri)
    models.Base.metadata.create_all(engine)

    return engine


@pytest.fixture
def db_connection(test_database):
    with test_database.connect() as connection:
        transaction = connection.begin()
        yield connection
        transaction.rollback()


@pytest.fixture
def db_session(db_connection):
    session = scoped_session(sessionmaker(bind=db_connection))
    yield session
    session.close()


@pytest.fixture
def fixtures(db_session):
    for item in dir(test.fixtures):
        item = getattr(test.fixtures, item)
        if isinstance(item, type) and issubclass(item, SQLAlchemyModelFactory):
            item._meta.sqlalchemy_session = db_session

    return test.fixtures


#############################################################
# KAFKA FIXTURES
#############################################################

@pytest.fixture
def kafka_app():
    return TSKafka(
        'test-service',
        debug=False,
        broker="kafka-1:9092,kafka-2:9092,kafka-3:9092"
    )


@pytest.fixture
def TestEvent(TestSchema):
    return Event(topic='test-topic', schema=TestSchema)


@pytest.fixture
def app_config():
    return {
        'TS_SERVICE_NAME': 'foo-service',
        'TS_LOG_LEVEL': 'INFO',
        'DEBUG': False
    }
