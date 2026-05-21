# -*- coding: utf-8 -*-

from logging import getLogger, Logger
from logging.config import dictConfig
from flask import Flask


app: Flask | None = None
_logger: Logger | None = None


def create_app():
    global app
    app = Flask(__name__)

    _init_logging()
    _init_api(app)
    (_logger.info if _logger else print)('app initiated successfully')

    return app


def _init_logging():
    # noinspection SpellCheckingInspection
    dictConfig({
        'version': 1,
        'formatters': {
            'simple': {
                'format': '[%(asctime)s] %(levelname)s %(name)s: %(message)s',
            },
            'colored': {
                '()': 'colorlog.ColoredFormatter',
                'format': '[%(asctime)s] '
                          '%(log_color)s%(levelname)s%(reset)s '
                          '%(name)s: %(message)s'
            }
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'colored',
                'level': 'DEBUG',
                'stream': 'ext://sys.stdout'
            }
        },
        'loggers': {
            'app': {
                'level': 'INFO',
                'handlers': ['console'],
                'propagate': False
            }
        },
        'disable_existing_loggers': False
    })
    # make sure flask `app.name == 'app'`
    # so we can use `current_app.logger` to get `_logger`
    global _logger
    _logger = getLogger(__name__)


def _init_api(_app):
    from app.api import init_app
    init_app(_app)
    from app.ws import init_app
    init_app(_app)
