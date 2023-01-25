# -*- coding: utf-8 -*-

from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Any
from logging import getLogger
from .utils import load_yaml


_logger = getLogger(__name__)
_config = {}
config: Mapping[str, Any] = MappingProxyType(_config)


CONFIG_FILE = 'config.yaml'


def _load_from_file() -> dict:
    try:
        conf = load_yaml(Path(CONFIG_FILE).read_text())
    except Exception:
        _logger.exception(f'failed to load {CONFIG_FILE!r}')
        raise
    else:
        return conf or {}


def _reload_all():
    conf = _load_from_file()
    old_keys = set(_config)
    _config.update(conf)
    for key in old_keys.difference(conf):
        _config.pop(key)


def _init():
    _reload_all()


def reload_all() -> Mapping[str, Any]:
    _reload_all()
    return config


def reload_one(key: str):
    conf = _load_from_file()
    try:
        value = conf[key]
    except KeyError:
        _logger.error(f'key {key!r} not found')
        return
    _config[key] = value
    return value


_init()
