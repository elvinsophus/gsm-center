# -*- coding: utf-8 -*-

import pytest
from click import ClickException

from app.main import GSMCenter, GSMStore
from manage import _format_call_ended_by, _resolve_single_call_id

OWN_NUMBER = '+12025550111'
OTHER_NUMBER = '+12025550122'
THIRD_NUMBER = '+12025550133'


class TestManagePhoneCalls:

    def test_resolve_single_call_id_returns_only_matching_call(self, fresh_db):
        ringing_id = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, THIRD_NUMBER, 'ENDED')

        assert _resolve_single_call_id(
            GSMCenter, [GSMCenter.PhoneCallStatus.RINGING], 'answer'
        ) == ringing_id

    def test_resolve_single_call_id_rejects_ambiguous_calls(self, fresh_db):
        GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, THIRD_NUMBER, 'RINGING')

        with pytest.raises(ClickException, match='multiple phone calls'):
            _resolve_single_call_id(
                GSMCenter, [GSMCenter.PhoneCallStatus.RINGING], 'answer')

    def test_format_call_ended_by_shows_local_rejection(self, fresh_db):
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'ENDED')
        GSMStore.phone_call_db.update_status(
            mid, 'ENDED', extra={
                'ended_by': 'local',
                'ended_reason': 'local_rejected',
                'ended_role': 'dialee',
            })
        call = GSMStore(OWN_NUMBER).get_phone_call(mid)

        assert _format_call_ended_by(call, GSMCenter.PhoneCallType) == (
            'rejected by local dialee')
