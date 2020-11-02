from unittest.mock import MagicMock, patch

import pytest
from marshmallow import fields, Schema

from test.models import Random
from thunderstorm.flask.exceptions import DeserializationError
from thunderstorm.flask.request_utils import (
    get_pagination_info, paginate, get_request_filters, get_request_pagination,
    make_paginated_response, sync_all_data
)
from thunderstorm.flask.schemas import PaginationSchema


@pytest.mark.parametrize('page,page_size,num_records,ceiling,prev_page,next_page,url', [
    (1, 20, 40, None, None, '/foo/bar?page_size=20&page=2', '/foo/bar'),
    (2, 20, 60, None, '/foo/bar?page_size=20&page=1', '/foo/bar?page_size=20&page=3', '/foo/bar'),
    (1, 20, 3, None, None, None, '/foo/bar'),
    (1, 20, 40, None, None, '/foo/bar?page_size=20&page=2', '/foo/bar'),
    (1, 20, 40, None, None, '/foo/bar?page_size=20&page=2', '/foo/bar'),
    (1, 20, 40, None, None, '/foo/bar?page_size=20&page=2', '/foo/bar?page_size=1000&page=50'),
    (1, 20, 40, 20, None, '/foo/bar?page_size=20&page=2', '/foo/bar?page_size=1000&page=50'),
    (1, 20, 20, 20, None, '/foo/bar?page_size=20&page=2', '/foo/bar?page_size=1000&page=50'),
])
def test_get_pagination_info(page, page_size, num_records, ceiling, prev_page, next_page, url):
    res = get_pagination_info(page, page_size, num_records, url, ceiling=ceiling)
    assert res.get('prev_page') == prev_page
    assert res.get('next_page') == next_page
    assert res['total_records'] == num_records


@pytest.mark.parametrize('page,page_size,num_records,prev_page,next_page,url', [
    (1, 20, 40, None, '/foo/bar?page_size=20&page=2', '/foo/bar',),
    (2, 20, 60, '/foo/bar?page_size=20&page=1', '/foo/bar?page_size=20&page=3', '/foo/bar',),
    (2, 20, 60, '/foo/bar?id=5&jezoo=ovp&page_size=20&page=1', '/foo/bar?id=5&jezoo=ovp&page_size=20&page=3', '/foo/bar?id=5&jezoo=ovp',),
    (1, 20, 3, None, None, '/foo/bar',),
    (1, 20, 40, None, '/foo/bar?page_size=20&page=2', '/foo/bar',),
    (1, 20, 40, None, '/foo/bar?page_size=20&page=2', '/foo/bar',),
    (1, 20, 40, None, '/foo/bar?page_size=20&page=2', '/foo/bar?page_size=1000&page=50',),
])
def test_paginate(page, page_size, num_records, prev_page, next_page, url):
    m_query = MagicMock()
    m_query.offset.return_value = m_query
    m_query.limit.return_value = m_query
    m_query.count.return_value = num_records

    res_query, res_page_info = paginate(m_query, page, page_size, url)

    assert res_page_info.get('prev_page') == prev_page
    assert res_page_info.get('next_page') == next_page
    assert res_page_info['total_records'] == num_records

    res_query.offset.assert_called_with((page - 1) * page_size)
    res_query.limit.assert_called_with(page_size)
    assert res_query == m_query


@patch('thunderstorm.flask.request_utils.request')
def test_get_request_filters_raises_with_bad_data(mock_request, TestSchema, TestException):
    # arrange
    data = {'int_1': 'notinteger', 'int_2': 2}
    mock_request.args = data

    # act/assert
    with pytest.raises(TestException):
        get_request_filters(TestSchema, TestException)


@patch('thunderstorm.flask.request_utils.request')
def test_get_request_filters_success(mock_request, TestSchema, TestException):
    # arrange
    data = {'int_1': 1, 'int_2': 2}
    mock_request.args = data

    # act/assert
    assert get_request_filters(TestSchema, TestException) == {'int_1': 1, 'int_2': 2}


def test_get_request_pagination_success_with_dict():
    # arrange
    data = {'page': 1, 'page_size': 2}

    # act/assert
    assert get_request_pagination(data) == {'page': 1, 'page_size': 2}


def test_get_request_pagination_failure_raises_KeyError_with_missing_key():
    # arrange
    data = {'page': 1, 'wrong': 2}

    # act/assert
    with pytest.raises(KeyError):
        assert get_request_pagination(data)


@patch('thunderstorm.flask.request_utils.request')
def test_get_request_pagination_raises_exc_when_provided_and_request_args_invalid(
    mock_request, TestException
):
    # arrange
    data = {'page': 1, 'page_size': 'word'}
    mock_request.args = data

    # act/assert
    with pytest.raises(TestException):
        get_request_pagination(exc=TestException)


@patch('thunderstorm.flask.request_utils.request')
def test_get_request_pagination_raises_DeserializationError_when_no_exc_provided_and_request_args_invalid(mock_request):
    # arrange
    data = {'page': 1, 'page_size': 'word'}
    mock_request.args = data

    # act/assert
    with pytest.raises(DeserializationError):
        get_request_pagination()


@patch('thunderstorm.flask.request_utils.request')
def test_get_request_pagination_success_with_request_args(mock_request, TestException):
    # arrange
    data = {'page': 1, 'page_size': 1}
    mock_request.args = data

    # act/assert
    assert get_request_pagination(exc=TestException) == data


def test_make_response_success(mock_query, TestSchemaList, flask_app):
    # arrange
    with flask_app.test_request_context():

        # act
        resp = make_paginated_response(mock_query, '/some/fake/path', TestSchemaList, 1, 20)

        # assert
        assert len(resp['data']) == 20
        resp.pop('data')
        assert resp == {
            'next_page': '/some/fake/path?page_size=20&page=2',
            'total_records': 50,
            'prev_page': None
        }


@pytest.mark.parametrize('total_records, ceiling, result', [
    (100, 150, 100),
    (100, 15, 15),
    (10000, 100, 100),
    (10000, None, 10000)
])
def test_paginate_with_ceiling(total_records, ceiling, result, db_session, fixtures):
    [fixtures.Random() for _ in range(total_records)] # noqa

    res_query, res_page_info = paginate(db_session.query(Random), 1, 50, '/foo/bar', ceiling=ceiling)

    assert not res_page_info.get('prev_page')
    assert res_page_info.get('next_page')
    assert res_page_info['total_records'] == result

    assert res_query.all() == db_session.query(Random).limit(50).all()


@pytest.mark.parametrize('total_records, ceiling, result', [
    (100, 150, 100),
    (100, 15, 15),
    (10000, 100, 100),
    (10000, None, 10000)
])
def test_make_paginated_response_with_ceiling(total_records, ceiling, result, db_session, fixtures, flask_app):
    [fixtures.Random() for _ in range(total_records)] # noqa

    class ApiSchema(PaginationSchema):
        class RandomSchema(Schema):
            uuid = fields.UUID()
            name = fields.String()

        data = fields.List(fields.Nested(RandomSchema))

    with flask_app.test_request_context():
        resp = make_paginated_response(db_session.query(Random), '/foo/bar', ApiSchema, 1, 50, ceiling=ceiling)

    # assert
    assert len(resp['data']) == 50
    resp.pop('data')
    assert resp == {
        'next_page': '/foo/bar?page_size=50&page=2',
        'total_records': result,
        'prev_page': None
    }


@patch('thunderstorm.flask.request_utils.request_session.get')
def test_sync_all_data_paging_v2(mock_http):
    # arrange
    total = set()

    def handler(item):
        total.add(item['id'])

    items = [i for i in range(19)]
    mock_http.return_value = MagicMock(spec_set=('status_code', 'content', 'json', 'raise_for_status'))
    mock_http.return_value.status_code = 200
    mock_http.return_value.json.side_effect = [
        {
            'data': [
                {
                    'id': i
                } for i in items[:10]
            ]
        },
        {
            'data': [
                {
                    'id': i
                } for i in items[10:]
            ]
        }
    ]

    # act
    sync_all_data('http://www.abc.abc', handler, page_size=10)

    # assert
    assert len(total) == 19
    assert total == set(items)
