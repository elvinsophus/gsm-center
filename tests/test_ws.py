# -*- coding: utf-8 -*-

from unittest.mock import patch

from app.config import _config
from app.main import GSMCenter, GSMStore


class TestAudioWebSocketRoutes:

    def test_simple_websocket_server_supports_accept(self):
        from simple_websocket import Server

        assert hasattr(Server, 'accept')

    def test_missing_audio_device_returns_404(self, client):
        with patch('app.ws.AudioDeviceOptions.get', return_value=None):
            resp = client.get('/ws/audio/devices/missing/input')

        assert resp.status_code == 404

    def test_call_audio_requires_answered_call(self, client):
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', '+12025550111', '+12025550122', 'RINGING')

        resp = client.get(f'/ws/calls/{mid}/audio')

        assert resp.status_code == 409

    def test_call_audio_resolves_configured_audio_device(self, client):
        old_devices = _config.get('DEVICES')
        old_audio = _config.get('AUDIO_DEVICES')
        _config['DEVICES'] = {
            '/dev/ttyUSB0': {
                'own_number': '+12025550111',
                'calls': {'audio_device': 'gsm_usb'},
            },
        }
        _config['AUDIO_DEVICES'] = {
            'gsm_usb': {'input': 'plughw:3,0', 'output': 'plughw:3,0'},
        }
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', '+12025550111', '+12025550122', 'ANSWERED')
        try:
            with patch('app.ws._accept_audio_ws',
                       return_value='accepted') as accept:
                resp = client.get(f'/ws/calls/{mid}/audio')
        finally:
            if old_devices is None:
                _config.pop('DEVICES', None)
            else:
                _config['DEVICES'] = old_devices
            if old_audio is None:
                _config.pop('AUDIO_DEVICES', None)
            else:
                _config['AUDIO_DEVICES'] = old_audio

        assert resp.status_code == 200
        assert resp.data == b'accepted'
        accept.assert_called_once()

    def test_device_options_list_reads_configured_devices(self):
        old_devices = _config.get('DEVICES')
        _config['DEVICES'] = {
            '/dev/ttyUSB0': {
                'own_number': '+12025550111',
                'calls': {'audio_device': 'gsm_usb'},
            },
        }
        try:
            devices = GSMCenter.DeviceOptions.list()
        finally:
            if old_devices is None:
                _config.pop('DEVICES', None)
            else:
                _config['DEVICES'] = old_devices

        assert devices['/dev/ttyUSB0'].own_number == '+12025550111'
        assert devices['/dev/ttyUSB0'].audio_device == 'gsm_usb'
