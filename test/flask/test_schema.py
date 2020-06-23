import pytest

from marshmallow import Schema, fields
from uuid import uuid4
from unittest.mock import ANY

from thunderstorm.flask import schemas as schema


class UserData(Schema):
    name = fields.String(required=True, allow_none=False)
    age = fields.Integer(required=False, default=0)
    uuid = fields.UUID(required=True)


def test_HTTPResponseSchemaV2_success():
    # arrange

    class TestHttpResponseV1(schema.HTTPResponseSchemaV3):
        data = fields.Nested(UserData)

    user_uuid = uuid4()
    response = {
        'code': 100,
        'message': 'success',
        'data': {
            'name': 'foo',
            'age': 18,
            'uuid': str(user_uuid)
        }
    }

    # act
    dump_resp = TestHttpResponseV1().dump(response)
    load_resp = TestHttpResponseV1().load(dump_resp)

    assert dump_resp == {
        'code': 100,
        'message': 'success',
        'data': {
            'name': 'foo',
            'uuid': str(user_uuid),
            'age': 18

        }
    }
    assert load_resp == {
        'code': 100,
        'message': 'success',
        'data': {
            'name': 'foo',
            'uuid': user_uuid,
            'age': 18
        }
    }


def test_HTTPResponseWithPaginationSchema_success():
    # arrange
    class TestGetUsersResponseV1(schema.HTTPResponseWithPaginationSchemaV3):
        data = fields.List(fields.Nested(UserData))

    users = [
        {
            'name': 'foo',
            'age': 12,
            'uuid': uuid4()
        },
        {
            'name': 'zoo',
            'age': 30,
            'uuid': uuid4()
        },

    ]

    data = {
        'data': users,
        'pagination': {
            'page': 10,
            'limit': 200,
            'items': 2
        }
    }

    #  act
    load_resp = TestGetUsersResponseV1().load(data)
    assert load_resp == {
        'data': [
            {'name': 'foo', 'age': 12, 'uuid': ANY},
            {'name': 'zoo', 'age': 30, 'uuid': ANY}
        ],
        'pagination': {
            'page': 10,
            'limit': 200,
            'items': 2
        }
    }


def test_HTTPRequestWithPaginationSchema_without_pagination_info():
    # arrange
    class TestGetUsersRequestV1(schema.HTTPRequestWithPaginationSchemaV3):
        name = fields.String()
    param = {
        'name': 'hi'
    }
    # act
    format_param = TestGetUsersRequestV1().load(param)
    assert format_param == {
        'name': 'hi',
        'page': 1,
        'limit': 100,
    }


@pytest.mark.parametrize('param, result, dump_resp', [
    ({"sort": "name,-age"}, [("name", "+"), ("age", "-")], None),
    ({"sort": "name"}, [("name", "+")], None),
    ({"sort": "-name, age"}, [("name", "-"), ("age", "+")], {"sort": "-name,age"}),
    ({"sort": "-name"}, [("name", "-")], None)
])
def test_SortKey(param, result, dump_resp):
    # arrange
    class MySchema(schema.HTTPRequestSchemaV3):
        sort = schema.SortKeys(fields.String())

    scm = MySchema
    # act
    key = scm().load(param)
    resp = scm().dump(key)

    # assert
    assert key['sort'] == result
    assert resp == param if not dump_resp else dump_resp


@pytest.mark.parametrize('param, result', [
    ({'uuids': None}, None),
    ({'uuids': ''}, []),
])
def test_ListSplitByComma(param, result):
    # arrange
    class MySchema(schema.HTTPRequestSchemaV3):
        uuids = schema.ListSplitByComma(fields.UUID, required=False, allow_none=True)

    # act
    param = MySchema().load(param)

    # assert
    assert param['uuids'] == result
