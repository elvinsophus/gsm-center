# -*- coding: utf-8 -*-

import pytest
from unittest.mock import patch


VALID_SMS_BODY = {
    'sender': '+8613500000001',
    'recipient': '+8613500000002',
    'content': 'Hello!',
}

VALID_CALL_BODY = {
    'caller': '+8613500000001',
    'recipient': '+8613500000002',
}


# ── GET /own-numbers ──────────────────────────────────────────────────────────

class TestGetOwnNumbers:

    def test_returns_json_list(self, client):
        with patch('app.main.GSMStore.list_active_own_numbers',
                   return_value=['+8613500000001', '+8613500000002']):
            resp = client.get('/own-numbers')
        assert resp.status_code == 200
        assert resp.json == ['+8613500000001', '+8613500000002']

    def test_empty_list_when_no_active_devices(self, client):
        with patch('app.main.GSMStore.list_active_own_numbers', return_value=[]):
            resp = client.get('/own-numbers')
        assert resp.status_code == 200
        assert resp.json == []

    def test_response_content_type_is_json(self, client):
        with patch('app.main.GSMStore.list_active_own_numbers', return_value=[]):
            resp = client.get('/own-numbers')
        assert resp.content_type == 'application/json'


# ── POST /sms ─────────────────────────────────────────────────────────────────

class TestPostSms:

    def test_valid_request_returns_id(self, client):
        with patch('app.main.GSMStore.add_pending_sms', return_value=7):
            resp = client.post('/sms', json=VALID_SMS_BODY)
        assert resp.status_code == 200
        assert resp.json == {'id': 7}

    def test_no_body_returns_4xx(self, client):
        resp = client.post('/sms')
        assert resp.status_code in (400, 415)

    def test_non_json_body_returns_4xx(self, client):
        resp = client.post('/sms', data='not json',
                           content_type='text/plain')
        assert resp.status_code in (400, 415)

    def test_missing_sender_returns_400(self, client):
        body = {k: v for k, v in VALID_SMS_BODY.items() if k != 'sender'}
        resp = client.post('/sms', json=body)
        assert resp.status_code == 400
        assert b'sender' in resp.data

    def test_missing_recipient_returns_400(self, client):
        body = {k: v for k, v in VALID_SMS_BODY.items() if k != 'recipient'}
        resp = client.post('/sms', json=body)
        assert resp.status_code == 400
        assert b'recipient' in resp.data

    def test_missing_content_returns_400(self, client):
        body = {k: v for k, v in VALID_SMS_BODY.items() if k != 'content'}
        resp = client.post('/sms', json=body)
        assert resp.status_code == 400
        assert b'content' in resp.data

    def test_inactive_sender_returns_400(self, client):
        with patch('app.main.GSMStore.add_pending_sms',
                   side_effect=ValueError('sender not active')):
            resp = client.post('/sms', json=VALID_SMS_BODY)
        assert resp.status_code == 400
        assert b'sender not active' in resp.data

    def test_internal_error_returns_500(self, client):
        with patch('app.main.GSMStore.add_pending_sms',
                   side_effect=RuntimeError('modem unavailable')):
            resp = client.post('/sms', json=VALID_SMS_BODY)
        assert resp.status_code == 500


class TestPostCalls:

    def test_valid_request_returns_id(self, client):
        with patch('app.main.GSMStore.add_phone_call', return_value=9):
            resp = client.post('/calls', json=VALID_CALL_BODY)
        assert resp.status_code == 200
        assert resp.json == {'id': 9}

    def test_no_body_returns_4xx(self, client):
        resp = client.post('/calls')
        assert resp.status_code in (400, 415)

    def test_missing_caller_returns_400(self, client):
        body = {k: v for k, v in VALID_CALL_BODY.items() if k != 'caller'}
        resp = client.post('/calls', json=body)
        assert resp.status_code == 400
        assert b'caller' in resp.data

    def test_missing_recipient_returns_400(self, client):
        body = {k: v for k, v in VALID_CALL_BODY.items()
                if k != 'recipient'}
        resp = client.post('/calls', json=body)
        assert resp.status_code == 400
        assert b'recipient' in resp.data

    def test_inactive_caller_returns_400(self, client):
        with patch('app.main.GSMStore.add_phone_call',
                   side_effect=ValueError('caller not active')):
            resp = client.post('/calls', json=VALID_CALL_BODY)
        assert resp.status_code == 400
        assert b'caller not active' in resp.data

    def test_internal_error_returns_500(self, client):
        with patch('app.main.GSMStore.add_phone_call',
                   side_effect=RuntimeError('modem unavailable')):
            resp = client.post('/calls', json=VALID_CALL_BODY)
        assert resp.status_code == 500


class TestGetCalls:

    def test_list_calls_returns_call_json(self, client):
        from app.main import GSMStore
        GSMStore.phone_call_db.insert(
            'OUTGOING', '+8613500000001', '+8613500000002', 'CREATED')

        resp = client.get('/calls', query_string={
            'own_number': '+8613500000001',
        })

        assert resp.status_code == 200
        assert len(resp.json) == 1
        assert resp.json[0]['type'] == 'OUTGOING'
        assert resp.json[0]['status'] == 'CREATED'
        assert resp.json[0]['caller'] == '+8613500000001'
        assert resp.json[0]['recipient'] == '+8613500000002'

    def test_list_calls_filters_by_status(self, client):
        from app.main import GSMStore
        db = GSMStore.phone_call_db
        db.insert('OUTGOING', '+8613500000001', '+8613500000002', 'CREATED')
        db.insert('INCOMING', '+8613500000001', '+8613500000003', 'RINGING')

        resp = client.get('/calls', query_string={
            'own_number': '+8613500000001',
            'status': 'RINGING',
        })

        assert resp.status_code == 200
        assert len(resp.json) == 1
        assert resp.json[0]['other_number'] == '+8613500000003'

    def test_list_calls_invalid_status_returns_400(self, client):
        resp = client.get('/calls', query_string={'status': 'NOPE'})

        assert resp.status_code == 400
        assert b'invalid PhoneCallStatus' in resp.data

    def test_get_call_returns_call_json(self, client):
        from app.main import GSMStore
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', '+8613500000001', '+8613500000002', 'RINGING')

        resp = client.get(f'/calls/{mid}')

        assert resp.status_code == 200
        assert resp.json['id'] == mid
        assert resp.json['type'] == 'INCOMING'
        assert resp.json['caller'] == '+8613500000002'
        assert resp.json['recipient'] == '+8613500000001'

    def test_get_call_missing_returns_404(self, client):
        resp = client.get('/calls/9999')

        assert resp.status_code == 404


class TestPostCallActions:

    def test_answer_returns_requested_status(self, client):
        with patch('app.main.GSMStore.request_phone_call_answer',
                   return_value=True):
            resp = client.post('/calls/7/answer')
        assert resp.status_code == 200
        assert resp.json == {'id': 7, 'status': 'ANSWER_REQUESTED'}

    def test_answer_missing_call_returns_404(self, client):
        with patch('app.main.GSMStore.request_phone_call_answer',
                   return_value=False):
            resp = client.post('/calls/7/answer')
        assert resp.status_code == 404

    def test_hangup_returns_requested_status(self, client):
        with patch('app.main.GSMStore.request_phone_call_hangup',
                   return_value=True):
            resp = client.post('/calls/7/hangup')
        assert resp.status_code == 200
        assert resp.json == {'id': 7, 'status': 'HANGUP_REQUESTED'}

    def test_hangup_missing_call_returns_404(self, client):
        with patch('app.main.GSMStore.request_phone_call_hangup',
                   return_value=False):
            resp = client.post('/calls/7/hangup')
        assert resp.status_code == 404
