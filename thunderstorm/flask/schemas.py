from marshmallow import Schema, fields, EXCLUDE
from marshmallow.validate import Range

from thunderstorm.flask.headers import rewrite_path


class PaginationSchema(Schema):
    """
    Schema for describing the structure of the dict containing pagination info.
    """
    next_page = fields.Function(
        lambda obj: rewrite_path(obj['next_page']) if obj.get('next_page') else None,
        required=False, dump_only=True, default=None, description='Next page uri'
    )
    prev_page = fields.Function(
        lambda obj: rewrite_path(obj['prev_page']) if obj.get('prev_page') else None,
        required=False, dump_only=True, default=None, description='Previous page uri'
    )
    total_records = fields.Integer(required=False, dump_only=True, description='Total number of entries')


class PaginationRequestSchema(Schema):
    """
    Validate pagination params on listing endpoints.
    """
    page = fields.Integer(
        validate=Range(min=1), missing=1, description='Page number, minimum value is 1, defaults to 1.'
    )
    page_size = fields.Integer(
        validate=Range(min=1, max=100),
        missing=20,
        description='Number of resources per page to display in the result. Defaults to 20'
    )


class HttpErrorResponseSchema(Schema):
    """
    Schema for standard HTTP errors (4XX,5XX)
    """
    message = fields.String(
        description='Description of the error happened during the response')
    code = fields.Integer(description='HTTP code of the response')


class PaginationRequestSchemaV2(Schema):
    """
    Validate pagination params on listing endpoints. version 2
    """
    page_num = fields.Integer(
        validate=Range(min=1), missing=1, description='Page number, minimum value is 1, defaults to 1.'
    )
    page_size = fields.Integer(
        validate=Range(min=1, max=1000),
        missing=20,
        description='Number of resources per page to display in the result. Defaults to 20'
    )


class PaginationSchemaV2(PaginationRequestSchemaV2):
    """
    Schema for describing the structure of the dict containing pagination info. Version 2
    """
    items = fields.Integer(required=True, dump_only=True, description='Total number of entries')
    total_page = fields.Integer(required=True, dump_only=True, description='Total number of pages')


#  ##################### API SPEC 3.0 ###########
class HTTPRequestSchemaV3(Schema):
    class Meta:
        unknown = EXCLUDE


class HTTPResponseSchemaV3(Schema):

    class Meta:
        unknown = EXCLUDE

    code = fields.Integer(request=False, default=200, description="The return code")
    message = fields.String(required=False, default='success', description='The message from API')
    debug_message = fields.String(required=False, description='The debug message from API, just for dev')


# ## PAGINATION ###
class PaginationSchemaV3(Schema):
    page = fields.Integer(required=True)
    limit = fields.Integer(required=True)
    items = fields.Integer(required=True)


class HTTPRequestWithPaginationSchemaV3(HTTPRequestSchemaV3):
    page = fields.Integer(missing=1, min=1)
    limit = fields.Integer(missing=100, min=1, max=1000)


class HTTPResponseWithPaginationSchemaV3(HTTPResponseSchemaV3):
    pagination = fields.Nested(PaginationSchemaV3)


class ListSplitByComma(fields.List):
    """
    Usage:

        data = ListSplitByComma(fields.UUID()) # 用逗号分割的UUID   例如： eca13d46-9c4b-480a-b1f0-b328c550f72f,eca13d46-9c4b-480a-b1f0-b328c550f72f,eca13d46-9c4b-480a-b1f0-b328c550f72f
        data = ListSplitByComma(Integer) # 用逗号分隔的整型数字 例如: 1,2,3,4

    """

    def _serialize(self, value, attr, obj, **kwargs):
        result = super()._serialize(value, attr, obj)
        return ','.join(result)

    def _deserialize(self, value, attr, data, **kwargs):
        new_value = value.split(',')
        return super()._deserialize(new_value, attr, data, **kwargs)


class SortKeys(ListSplitByComma):
    """
        Usage:
         test/flask/test_schema.py
    """
    def _serialize(self, value, attr, obj, **kwargs):
        str_array = [f'-{r[0]}' if r[1] == '-' else r[0] for r in value]
        result = super()._serialize(str_array, attr, obj)
        return result

    def _deserialize(self, value, attr, data, **kwargs):
        keys = [k.strip() for k in super()._deserialize(value, attr, data, **kwargs)]
        return [(s[1:], '-') if s[0] == '-' else (s, '+') for s in keys]
