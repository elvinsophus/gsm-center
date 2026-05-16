# -*- coding: utf-8 -*-

import pytest
from unittest.mock import patch


VALID_SMS_BODY = {
    'sender': '+8613500000001',
    'recipient': '+8613500000002',
    'content': 'Hello!',
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
