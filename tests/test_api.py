# -*- coding: utf-8 -*-

import pytest
from app.audio import AudioCommandResult
from unittest.mock import patch


class TestGetAudioDevices:

    def test_list_audio_devices_returns_configured_devices(self, client):
        from app.main import GSMCenter
        devices = {
            'gsm_usb': GSMCenter.AudioDeviceOptions(
                'gsm_usb', 'plughw:3,0', 'plughw:3,0', 8000, 1, 's16le', 20),
        }

        with patch('app.api.AudioDeviceOptions.list', return_value=devices):
            resp = client.get('/audio/devices')

        assert resp.status_code == 200
        assert resp.json == {
            'gsm_usb': {
                'name': 'gsm_usb',
                'input': 'plughw:3,0',
                'output': 'plughw:3,0',
                'sample_rate': 8000,
                'channels': 1,
                'format': 's16le',
                'frame_ms': 20,
            },
        }

    def test_get_audio_device_returns_configured_device(self, client):
        from app.main import GSMCenter
        device = GSMCenter.AudioDeviceOptions(
            'gsm_usb', 'plughw:3,0', 'plughw:3,0', 8000, 1, 's16le', 20)

        with patch('app.api.AudioDeviceOptions.get', return_value=device):
            resp = client.get('/audio/devices/gsm_usb')

        assert resp.status_code == 200
        assert resp.json['name'] == 'gsm_usb'
        assert resp.json['input'] == 'plughw:3,0'

    def test_get_audio_device_missing_returns_404(self, client):
        with patch('app.api.AudioDeviceOptions.get', return_value=None):
            resp = client.get('/audio/devices/missing')

        assert resp.status_code == 404


class TestAudioSmokeTests:

    def test_record_audio_device_runs_smoke_test(self, client):
        from app.main import GSMCenter
        device = GSMCenter.AudioDeviceOptions(
            'gsm_usb', 'plughw:3,0', 'plughw:3,0', 8000, 1, 's16le', 20)
        result = AudioCommandResult(['arecord'], 0, 'ok', '')

        with patch('app.api.AudioDeviceOptions.get', return_value=device), \
                patch('app.api.record_audio_sample',
                      return_value=result) as record:
            resp = client.post('/audio/devices/gsm_usb/test-record', json={
                'path': '/tmp/sample.wav',
                'seconds': 2,
            })

        assert resp.status_code == 200
        record.assert_called_once_with(device, '/tmp/sample.wav', 2)
        assert resp.json == {
            'command': ['arecord'],
            'return_code': 0,
            'stdout': 'ok',
            'stderr': '',
        }

    def test_record_audio_device_requires_path(self, client):
        from app.main import GSMCenter
        device = GSMCenter.AudioDeviceOptions(
            'gsm_usb', 'plughw:3,0', 'plughw:3,0', 8000, 1, 's16le', 20)

        with patch('app.api.AudioDeviceOptions.get', return_value=device):
            resp = client.post('/audio/devices/gsm_usb/test-record', json={})

        assert resp.status_code == 400

    def test_play_audio_device_runs_smoke_test(self, client):
        from app.main import GSMCenter
        device = GSMCenter.AudioDeviceOptions(
            'gsm_usb', 'plughw:3,0', 'plughw:3,0', 8000, 1, 's16le', 20)
        result = AudioCommandResult(['aplay'], 0, '', '')

        with patch('app.api.AudioDeviceOptions.get', return_value=device), \
                patch('app.api.play_audio_sample',
                      return_value=result) as play:
            resp = client.post('/audio/devices/gsm_usb/test-play', json={
                'path': '/tmp/sample.wav',
            })

        assert resp.status_code == 200
        play.assert_called_once_with(device, '/tmp/sample.wav')
        assert resp.json['command'] == ['aplay']

    def test_play_audio_device_missing_returns_404(self, client):
        with patch('app.api.AudioDeviceOptions.get', return_value=None):
            resp = client.post('/audio/devices/missing/test-play', json={
                'path': '/tmp/sample.wav',
            })

        assert resp.status_code == 404

    def test_play_audio_device_requires_path(self, client):
        from app.main import GSMCenter
        device = GSMCenter.AudioDeviceOptions(
            'gsm_usb', 'plughw:3,0', 'plughw:3,0', 8000, 1, 's16le', 20)

        with patch('app.api.AudioDeviceOptions.get', return_value=device):
            resp = client.post('/audio/devices/gsm_usb/test-play', json={})

        assert resp.status_code == 400


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

class TestGetContacts:

    def test_returns_configured_contacts(self, client, monkeypatch):
        from app.config import _config
        monkeypatch.setitem(_config, 'CONTACTS', {
            'Alice': '+8613500000001',
        })

        resp = client.get('/contacts')

        assert resp.status_code == 200
        assert resp.json == {'Alice': '+8613500000001'}

    def test_post_creates_contact(self, client):
        resp = client.post('/contacts', json={
            'alias': 'Alice',
            'phone_number': '+8613500000001',
        })

        assert resp.status_code == 200
        assert resp.json == {
            'alias': 'Alice',
            'phone_number': '+8613500000001',
        }
        assert client.get('/contacts').json == {
            'Alice': '+8613500000001',
        }

    def test_delete_removes_contact(self, client):
        client.post('/contacts', json={
            'alias': 'Alice',
            'phone_number': '+8613500000001',
        })

        resp = client.delete('/contacts/alice')

        assert resp.status_code == 200
        assert client.get('/contacts').json == {}


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

    def test_aliases_are_resolved_before_inserting(
            self, client, monkeypatch):
        from app.config import _config
        from app.main import GSMStore
        monkeypatch.setitem(_config, 'CONTACTS', {
            'Own': '+8613500000001',
            'Alice': '+8613500000002',
        })
        GSMStore.sim_card_db.update(
            '/dev/ttyUSB0', '+8613500000001',
            call_enabled=True, sms_enabled=True)

        resp = client.post('/sms', json={
            'sender': 'own',
            'recipient': 'alice',
            'content': 'Hello!',
        })

        assert resp.status_code == 200
        row = GSMStore.pending_sms_db.get(resp.json['id'])
        assert row['sender'] == '+8613500000001'
        assert row['recipient'] == '+8613500000002'


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

    def test_aliases_are_resolved_before_inserting(
            self, client, monkeypatch):
        from app.config import _config
        from app.main import GSMStore
        monkeypatch.setitem(_config, 'CONTACTS', {
            'Own': '+8613500000001',
            'Alice': '+8613500000002',
        })
        GSMStore.sim_card_db.update(
            '/dev/ttyUSB0', '+8613500000001',
            call_enabled=True, sms_enabled=True)

        resp = client.post('/calls', json={
            'caller': 'own',
            'recipient': 'alice',
        })

        assert resp.status_code == 200
        row = GSMStore.phone_call_db.get(resp.json['id'])
        assert row['own_number'] == '+8613500000001'
        assert row['other_number'] == '+8613500000002'


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

    def test_list_calls_includes_alias_fields(self, client, monkeypatch):
        from app.config import _config
        from app.main import GSMStore
        monkeypatch.setitem(_config, 'CONTACTS', {
            'Own': '+8613500000001',
            'Alice': '+8613500000002',
        })
        GSMStore.phone_call_db.insert(
            'OUTGOING', '+8613500000001', '+8613500000002', 'CREATED')

        resp = client.get('/calls', query_string={'own_number': 'own'})

        assert resp.status_code == 200
        assert resp.json[0]['own_number_alias'] == 'Own'
        assert resp.json[0]['other_number_alias'] == 'Alice'
        assert resp.json[0]['caller_alias'] == 'Own'
        assert resp.json[0]['recipient_alias'] == 'Alice'

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

    def test_list_call_recordings_returns_recording_json(self, client):
        from app.main import GSMCenter, GSMStore
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', '+8613500000001', '+8613500000002', 'ANSWERED')
        rid = GSMStore.phone_call_recording_db.insert(
            mid, 'recordings/call.wav', 'wav',
            GSMCenter.PhoneCallRecordingStatus.RECORDING,
            started_at=1700000000)

        resp = client.get(f'/calls/{mid}/recordings')

        assert resp.status_code == 200
        assert resp.json[0]['id'] == rid
        assert resp.json[0]['call_id'] == mid
        assert resp.json[0]['path'] == 'recordings/call.wav'
        assert resp.json[0]['status'] == 'RECORDING'

    def test_list_call_recordings_missing_call_returns_404(self, client):
        resp = client.get('/calls/9999/recordings')

        assert resp.status_code == 404

    def test_list_call_recordings_invalid_status_returns_400(self, client):
        from app.main import GSMStore
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', '+8613500000001', '+8613500000002', 'ANSWERED')

        resp = client.get(
            f'/calls/{mid}/recordings', query_string={'status': 'NOPE'})

        assert resp.status_code == 400


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
