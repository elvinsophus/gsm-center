# -*- coding: utf-8 -*-

from functools import wraps
from decimal import Decimal, ROUND_DOWN, Context
from collections import deque
from json import dumps as json_dumps
from enum import EnumMeta, Enum, IntFlag
from datetime import datetime, date, tzinfo, timedelta, timezone
from re import compile as re_compile, I as RE_I
from typing import Any
from collections.abc import Callable, Iterator
from logging import getLogger
from dateutil.tz import UTC
from dateutil.relativedelta import relativedelta
from ruamel.yaml import YAML
import subprocess
import shlex


_logger = getLogger(__name__)


AmountType = Decimal | str | int


def amount_to_str(amount: AmountType, decimals: int = None,
                  rounding: str = ROUND_DOWN, *,
                  with_separator: bool = False) -> str:
    amount = Decimal(amount)
    if decimals is not None:
        amount = quantize_amount(amount, decimals, rounding)
    return f'{amount.normalize():{",f" if with_separator else "f"}}'


def quantize_amount(amount: AmountType, decimals: int,
                    rounding: str = ROUND_DOWN,
                    *, precision: int = None
                    ) -> Decimal:
    context = Context(prec=precision) if precision is not None else None
    return Decimal(amount).quantize(Decimal(10) ** -decimals, rounding,
                                    context=context)


_SIZE_UNITS = '', 'K', 'M', 'G', 'T'
_RE_SIZE = re_compile(''.join([
    r'(\d+(?:\.\d*)?)([',
    ''.join(_SIZE_UNITS),
    r'])?'
]), flags=RE_I)


def remove_prefix(text: str, prefix: str) -> str:
    if text.startswith(prefix):
        text = text[len(prefix):]
    return text


def remove_suffix(text: str, suffix: str) -> str:
    if text.endswith(suffix):
        text = text[:len(text)-len(suffix)]
    return text


def safe(func: Callable, *,
         default: Any = None,
         catch_exc: bool = False,
         raise_exc: type[Exception] | tuple[type[Exception], ...] = None,
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


def exhaust(iterator: Iterator):
    """Exhausts an interator, in a space-efficient way."""
    deque(iterator, maxlen=0)


def datetime_to_str(dt: datetime, offset_minutes: int = 0,
                    fmt: str = '%Y-%m-%d %H:%M:%S') -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    dt = dt.astimezone(timezone(timedelta(minutes=offset_minutes)))
    return dt.strftime(fmt)


def timestamp_to_datetime(timestamp: float, tz: tzinfo = None) -> datetime:
    return datetime.fromtimestamp(timestamp, tz or UTC)


_UNIT_ATTRS = 'days', 'hours', 'minutes', 'seconds'
_UNITS = 'day', 'hour', 'minute', 'second'
_UNITS_PL = _UNIT_ATTRS
_UNITS_ABBR = 'd', 'h', 'm', 's'


def timedelta_to_str(delta: timedelta | float | int, *,
                     abbr: bool = False) -> str:
    """
    Presents a delta of time as a human-readable string. Units range from day
    to second, plural forms supported.
    :param delta: delta of time as `timedelta` or number
    :param abbr: whether to use abbreviated units to shorten the presentation
    e.g.
    >>> timedelta_to_str(0)
    '0 seconds'
    >>> timedelta_to_str(1)
    '1 second'
    >>> timedelta_to_str(2)
    '2 seconds'
    >>> timedelta_to_str(100)
    '1 minute 40 seconds'
    >>> timedelta_to_str(timedelta(seconds=100))
    '1 minute 40 seconds'
    >>> timedelta_to_str(1024)
    '17 minutes 4 seconds'
    >>> timedelta_to_str(123456)
    '1 day 10 hours 17 minutes 36 seconds'
    >>> timedelta_to_str(123456, abbr=True)
    '1d10h17m36s'
    """
    if isinstance(delta, timedelta):
        if delta.total_seconds() < 0:
            raise ValueError(f'negative time delta is not supported: {delta!r}')
        s, ms = divmod(delta.total_seconds(), 1)
        delta = relativedelta(seconds=int(s), microseconds=int(ms * 1000000))
    elif isinstance(delta, (float, int)):
        if delta < 0:
            raise ValueError(f'negative time delta is not supported: {delta!r}')
        s, ms = divmod(delta, 1)
        delta = relativedelta(seconds=int(s))
    else:
        raise TypeError(f'unsupported time delta: {delta!r}')

    if not delta:
        return f'0{_UNITS_ABBR[-1]}' if abbr else f"0 {_UNITS_PL[-1]}"

    return ('' if abbr else ' ').join(
        f'{v}{ua}' if abbr else f'{v} {up if v > 1 else u}'
        for u, up, ua, attr in zip(_UNITS, _UNITS_PL, _UNITS_ABBR, _UNIT_ATTRS)
        if (v := getattr(delta, attr)) > 0
    )


class NamedObject:

    """Like `x = object()`, but now `x` has a name."""

    def __init__(self, name: str, *, is_null: bool = False):
        self._name = name
        self._is_null = is_null

    def __repr__(self):
        return f'<{self._name}>'

    def __bool__(self):
        return not self._is_null


_EMPTY = NamedObject('Empty')


def json_serializable(obj, fail_safe=_EMPTY):
    if isinstance(obj, (list, tuple, set, frozenset)):
        return list(map(json_serializable, obj))
    if isinstance(obj, dict):
        return {k: json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, Decimal):
        return amount_to_str(obj)
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
    return YAML(typ='safe', pure=True).load(text)


_RE_CAMEL = re_compile(r'((?<=[a-z0-9])[A-Z]|(?!^)(?<!_)[A-Z](?=[a-z]))')


def camel_to_underscore(text: str) -> str:
    return _RE_CAMEL.sub(r'_\1', text).lower()


def run_system_command(cmd: list[str] | str, user: str = None, *,
                       env: dict[str, str] = None,
                       detached: bool = False, log_output: bool = False
                       ) -> str:
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
            f'{e.stderr}')
    else:
        output = r.stdout.decode()
    if log_output:
        _logger.info(output)
    return output
