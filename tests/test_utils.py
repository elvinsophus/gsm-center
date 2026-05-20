# -*- coding: utf-8 -*-

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from app.utils import (
    camel_to_underscore, safe, json_serializable, compact_json_dumps, load_yaml
)
from app.db import _enum_name


# ── camel_to_underscore ───────────────────────────────────────────────────────

class TestCamelToUnderscore:
    def test_simple_camel(self):
        assert camel_to_underscore('CamelCase') == 'camel_case'

    def test_acronym_prefix(self):
        assert camel_to_underscore('SIMCard') == 'sim_card'

    def test_trailing_acronym(self):
        assert camel_to_underscore('PendingSMS') == 'pending_sms'

    def test_already_lower(self):
        assert camel_to_underscore('sms') == 'sms'

    def test_mixed_acronym_and_camel(self):
        assert camel_to_underscore('SmsDB') == 'sms_db'


# ── _enum_name ────────────────────────────────────────────────────────────────

class _Color(Enum):
    RED = 1
    GREEN = 2


class TestEnumName:
    def test_enum_value_returns_name(self):
        assert _enum_name(_Color.RED) == 'RED'

    def test_string_passes_through(self):
        assert _enum_name('PENDING') == 'PENDING'


# ── safe ──────────────────────────────────────────────────────────────────────

class TestSafe:
    def test_returns_value_on_success(self):
        assert safe(lambda: 42)() == 42

    def test_swallows_exception_returns_none(self):
        assert safe(lambda: 1 / 0)() is None

    def test_custom_default(self):
        assert safe(lambda: 1 / 0, default=-1)() == -1

    def test_catch_exc_returns_exception(self):
        result = safe(lambda: 1 / 0, catch_exc=True)()
        assert isinstance(result, ZeroDivisionError)

    def test_raise_exc_reraises_matching(self):
        def boom():
            raise ValueError('bad')
        with pytest.raises(ValueError):
            safe(boom, raise_exc=ValueError)()

    def test_raise_exc_swallows_non_matching(self):
        assert safe(lambda: 1 / 0, raise_exc=ValueError)() is None

    def test_mute_exc_true_silences_all(self):
        assert safe(lambda: 1 / 0, mute_exc=True)() is None

    def test_mute_exc_type_silences_matching(self):
        assert safe(lambda: 1 / 0, mute_exc=ZeroDivisionError)() is None


# ── json_serializable ─────────────────────────────────────────────────────────

class TestJsonSerializable:
    def test_passthrough_primitives(self):
        assert json_serializable(1) == 1
        assert json_serializable('hi') == 'hi'
        assert json_serializable(None) is None
        assert json_serializable(True) is True

    def test_decimal_to_str(self):
        assert json_serializable(Decimal('3.14')) == '3.14'

    def test_enum_to_name(self):
        assert json_serializable(_Color.RED) == 'RED'

    def test_list_recursed(self):
        assert json_serializable([Decimal('1')]) == ['1']

    def test_set_to_list(self):
        assert sorted(json_serializable({1, 2})) == [1, 2]

    def test_dict_recursed(self):
        assert json_serializable({'k': Decimal('2')}) == {'k': '2'}

    def test_datetime_to_timestamp(self):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        assert json_serializable(dt) == int(dt.timestamp())

    def test_unserializable_falls_back_to_repr(self):
        class Opaque:
            def __repr__(self): return 'Opaque()'
        assert json_serializable(Opaque()) == 'Opaque()'


# ── compact_json_dumps ────────────────────────────────────────────────────────

class TestCompactJsonDumps:
    def test_no_spaces(self):
        result = compact_json_dumps({'a': 1, 'b': 2})
        assert ' ' not in result

    def test_correct_output(self):
        assert compact_json_dumps({'x': 1}) == '{"x":1}'

    def test_serializes_enum(self):
        assert compact_json_dumps({'s': _Color.GREEN}) == '{"s":"GREEN"}'


# ── load_yaml ─────────────────────────────────────────────────────────────────

class TestLoadYaml:
    def test_simple_dict(self):
        assert load_yaml('foo: bar\nbaz: 42\n') == {'foo': 'bar', 'baz': 42}

    def test_empty_returns_none(self):
        assert load_yaml('') is None

    def test_null_value(self):
        assert load_yaml('key:\n') == {'key': None}

    def test_boolean(self):
        assert load_yaml('enabled: true\n') == {'enabled': True}

    def test_nested(self):
        result = load_yaml('outer:\n  inner: 1\n')
        assert result == {'outer': {'inner': 1}}
