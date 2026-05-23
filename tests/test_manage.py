# -*- coding: utf-8 -*-

import pytest
from click import ClickException
from click.testing import CliRunner
from unittest.mock import patch

from app.audio import ALSAAudioCard, ALSAAudioEndpoint, AudioProbeResult
from app.main import GSMCenter, GSMStore

from manage import (_format_call_ended_by, _preferred_audio_sample_rate,
                    _recommended_audio_card, cli, _resolve_single_call_id)

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


class TestManageAudio:

    def test_preferred_audio_sample_rate_uses_telephony_when_available(self):
        assert _preferred_audio_sample_rate([48000, 8000]) == 8000

    def test_preferred_audio_sample_rate_falls_back_to_working_rate(self):
        assert _preferred_audio_sample_rate([48000]) == 48000

    def test_probe_audio_device_can_suggest_default_name(self):
        probe_result = AudioProbeResult(
            48000, ['ffmpeg'], True, 0, '', '')
        with patch('app.audio.probe_audio_input',
                   return_value=[probe_result]):
            result = CliRunner().invoke(
                cli,
                [
                    'probe-audio-device',
                    '--input', 'plughw:3,0',
                    '--rates', '48000',
                ])

        assert result.exit_code == 0
        assert 'audio_device:' in result.output
        assert 'sample_rate: 48000' in result.output

    def test_discover_audio_devices_lists_suggestions(self):
        endpoint = ALSAAudioEndpoint(
            3, 'Device', 'USB-Audio - USB Audio Device', 0, 'USB Audio',
            'USB Audio', 'plughw:3,0', 'input')
        card = ALSAAudioCard(
            3, 'Device', 'USB-Audio - USB Audio Device',
            'C-Media Electronics Inc. USB Audio Device',
            [endpoint], [endpoint._replace(kind='output')])

        with patch('app.audio.discover_alsa_audio_cards',
                   return_value=[card]):
            result = CliRunner().invoke(
                cli, ['discover-audio-devices', '--name', 'gsm_usb'])

        assert result.exit_code == 0
        assert 'recommended card: 3' in result.output
        assert 'card 3*: Device | USB-Audio - USB Audio Device' in result.output
        assert 'input: "plughw:3,0"' in result.output
        assert 'output: "plughw:3,0"' in result.output
        assert 'gsm_usb:' in result.output

    def test_recommended_audio_card_prefers_usb_duplex_card(self):
        input_endpoint = ALSAAudioEndpoint(
            2, 'Generic', 'Analog', 0, 'Analog', 'Analog',
            'plughw:2,0', 'input')
        output_endpoint = input_endpoint._replace(kind='output')
        usb_input = input_endpoint._replace(
            card_index=3, card_id='Device', card_name='USB Audio Device',
            alsa_device='plughw:3,0')
        usb_output = usb_input._replace(kind='output')
        cards = [
            ALSAAudioCard(2, 'Generic', 'Analog', '', [input_endpoint],
                          [output_endpoint]),
            ALSAAudioCard(3, 'Device', 'USB Audio Device', '',
                          [usb_input], [usb_output]),
        ]

        assert _recommended_audio_card(cards).index == 3
