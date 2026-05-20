# -*- coding: utf-8 -*-

from functools import wraps
from decimal import Decimal
from json import dumps as json_dumps
from enum import EnumMeta, Enum, IntFlag
from datetime import datetime, date, tzinfo
from re import compile as re_compile
from typing import Any
from collections.abc import Callable
from logging import getLogger
from dateutil.tz import UTC
from ruamel.yaml import YAML
import subprocess
import shlex


_logger = getLogger(__name__)


def safe(func: Callable, *,
         default: Any = None,
         catch_exc: bool = False,
         raise_exc: type[Exception] | tuple[type[Exception], ...] | None = None,
         mute_exc: bool | type[Exception] | tuple[type[Exception], ...] = False
         ):
    """
    Decorator to silence exceptions from a function call.
    :param func: any callable
    :param default: default return when any exception is raised
    :param catch_exc: whether to catch exception and return it if raised
    :param raise_exc: whether to raise specific exceptions
    :param mute_exc: whether to mute specific exceptions (`True` to mute all)
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # noinspection PyBroadException
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if catch_exc:
                return e
            if raise_exc is not None and isinstance(e, raise_exc):
                raise
            if not (mute_exc if isinstance(mute_exc, bool)
                    else isinstance(e, mute_exc)):
                _logger.exception(
                    f'failed to execute {func!r} with {args} and {kwargs}')
            return default
    return wrapper


def timestamp_to_datetime(timestamp: float, tz: tzinfo | None = None
                          ) -> datetime:
    return datetime.fromtimestamp(timestamp, tz or UTC)


_EMPTY = object()


def json_serializable(obj, fail_safe=_EMPTY):
    if isinstance(obj, (list, tuple, set, frozenset)):
        return list(map(json_serializable, obj))
    if isinstance(obj, dict):
        return {k: json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return f'{obj.normalize():f}'
    if isinstance(obj, IntFlag):
        return obj.value
    if isinstance(obj, Enum):
        return obj.name
    if isinstance(obj, EnumMeta):
        return {e.name: e.value for e in obj}
    if isinstance(obj, datetime):
        return int(obj.timestamp())
    if isinstance(obj, date):
        dt = datetime(obj.year, obj.month, obj.day)
        return int(dt.timestamp())
    try:
        json_dumps(obj)
    except TypeError:
        return fail_safe if fail_safe is not _EMPTY else str(obj)
    return obj


def compact_json_dumps(data, **kwargs) -> str:
    if kwargs.get('cls') is None:
        data = json_serializable(data)
    return json_dumps(data, separators=(',', ':'), **kwargs)


def load_yaml(text: str):
    # YAML 1.2
    return YAML(typ='safe').load(text)


_RE_CAMEL = re_compile(r'((?<=[a-z0-9])[A-Z]|(?!^)(?<!_)[A-Z](?=[a-z]))')


def camel_to_underscore(text: str) -> str:
    return _RE_CAMEL.sub(r'_\1', text).lower()


def run_system_command(cmd: list[str] | str, user: str | None = None, *,
                       env: dict[str, str] | None = None,
                       detached: bool = False,
                       log_output: bool = False) -> str:
    _logger.info(f'executing command: {cmd}, {user=}, {detached=}')
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    if detached:
        # noinspection PyArgumentList
        subprocess.Popen(cmd, user=user, env=env, start_new_session=True)
        return ''
    try:
        # noinspection PyArgumentList
        r = subprocess.run(cmd, user=user, env=env,
                           check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f'command {cmd!r} failed with status code {e.returncode}: '
            f'{e.stderr.decode(errors="replace")}')
    else:
        output = r.stdout.decode()
    if log_output:
        _logger.info(output)
    return output
