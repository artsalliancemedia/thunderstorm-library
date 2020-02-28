# -*- coding: utf-8 -*-
import pytest
import logging

from flask import Flask
from thunderstorm.logging.flask import init_app


@pytest.mark.parametrize('json_handler', [(True), (False)])
def test_flask_init_logging_with_json_handler(json_handler, app_config):
    # arrange
    app = Flask(__name__)
    app.config = app_config
    # act
    init_app(app, json_handler)
    logger = logging.getLogger(__name__)
    logger.info('test log')
