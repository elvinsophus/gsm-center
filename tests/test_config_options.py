# -*- coding: utf-8 -*-

from app.main import GSMCenter


class TestDeviceOptions:

    def test_legacy_sms_and_call_options(self):
        options = GSMCenter.DeviceOptions.from_dict({
            'sms_enabled': True,
            'call_enabled': True,
            'on_sms_received': './sms.sh',
            'on_sms_received_env': {'A': '1'},
            'on_call_received': './call.sh',
            'on_call_received_env': {'B': '2'},
            'on_call_answered': './answered.sh',
            'on_call_answered_env': {'C': '3'},
        })

        assert options.sms_enabled is True
        assert options.call_enabled is True
        assert options.on_sms_received == './sms.sh'
        assert options.on_sms_received_env == {'A': '1'}
        assert options.on_call_received == './call.sh'
        assert options.on_call_received_env == {'B': '2'}
        assert options.on_call_answered == './answered.sh'
        assert options.on_call_answered_env == {'C': '3'}

    def test_grouped_sms_and_call_options(self):
        options = GSMCenter.DeviceOptions.from_dict({
            'sms': {
                'enabled': True,
                'on_received': {
                    'command': './sms.sh',
                    'env': {'A': '1'},
                },
            },
            'calls': {
                'enabled': True,
                'outgoing': {
                    'answer_timeout': 45,
                },
                'audio_device': 'gsm_usb',
                'audio': {
                    'command': './call-audio.sh',
                    'env': {'D': '4'},
                    'input': {
                        'command': './stt.sh',
                        'env': {'STT': '1'},
                    },
                    'output': {
                        'command': './tts.sh',
                        'env': {'TTS': '1'},
                    },
                },
                'recording': {
                    'enabled': True,
                    'directory': 'recordings',
                    'command': './record-call.sh',
                    'env': {'E': '5'},
                    'format': 'mp3',
                    'hooks': {
                        'completed': {
                            'command': './recording-completed.sh',
                            'env': {'RC': '1'},
                        },
                        'failed': {
                            'command': './recording-failed.sh',
                        },
                    },
                },
                'hooks': {
                    'received': {
                        'command': './call.sh',
                        'env': {'B': '2'},
                    },
                    'dialing': {
                        'command': './dialing.sh',
                    },
                    'answered': {
                        'command': './answered.sh',
                        'env': {'C': '3'},
                    },
                    'ended': {
                        'command': './ended.sh',
                    },
                    'failed': {
                        'command': './failed.sh',
                    },
                },
            },
        })

        assert options.sms_enabled is True
        assert options.call_enabled is True
        assert options.outgoing_answer_timeout == 45
        assert options.audio_device == 'gsm_usb'
        assert options.on_sms_received == './sms.sh'
        assert options.on_sms_received_env == {'A': '1'}
        assert options.on_call_received == './call.sh'
        assert options.on_call_received_env == {'B': '2'}
        assert options.on_call_dialing == './dialing.sh'
        assert options.on_call_answered == './answered.sh'
        assert options.on_call_answered_env == {'C': '3'}
        assert options.on_call_ended == './ended.sh'
        assert options.on_call_failed == './failed.sh'
        assert options.call_audio_command == './call-audio.sh'
        assert options.call_audio_env == {'D': '4'}
        assert options.call_audio_input_command == './stt.sh'
        assert options.call_audio_input_env == {'STT': '1'}
        assert options.call_audio_output_command == './tts.sh'
        assert options.call_audio_output_env == {'TTS': '1'}
        assert options.call_recording_enabled is True
        assert options.call_recording_directory == 'recordings'
        assert options.call_recording_command == './record-call.sh'
        assert options.call_recording_env == {'E': '5'}
        assert options.call_recording_format == 'mp3'
        assert options.call_recording_completed_command == (
            './recording-completed.sh')
        assert options.call_recording_completed_env == {'RC': '1'}
        assert options.call_recording_failed_command == './recording-failed.sh'

    def test_grouped_options_take_precedence_over_legacy_options(self):
        options = GSMCenter.DeviceOptions.from_dict({
            'sms_enabled': False,
            'call_enabled': False,
            'on_sms_received': './legacy-sms.sh',
            'on_call_received': './legacy-call.sh',
            'sms': {
                'enabled': True,
                'on_received': {'command': './grouped-sms.sh'},
            },
            'calls': {
                'enabled': True,
                'hooks': {
                    'received': {'command': './grouped-call.sh'},
                },
            },
        })

        assert options.sms_enabled is True
        assert options.call_enabled is True
        assert options.on_sms_received == './grouped-sms.sh'
        assert options.on_call_received == './grouped-call.sh'


class TestAudioDeviceOptions:

    def test_from_dict_uses_defaults(self):
        options = GSMCenter.AudioDeviceOptions.from_dict('gsm_usb', {})

        assert options.name == 'gsm_usb'
        assert options.input == ''
        assert options.output == ''
        assert options.sample_rate == 8000
        assert options.channels == 1
        assert options.format == 's16le'
        assert options.frame_ms == 20

    def test_from_dict_parses_configured_values(self):
        options = GSMCenter.AudioDeviceOptions.from_dict('gsm_usb', {
            'input': 'plughw:3,0',
            'output': 'plughw:3,0',
            'sample_rate': '16000',
            'channels': '2',
            'format': 's24le',
            'frame_ms': '40',
        })

        assert options.name == 'gsm_usb'
        assert options.input == 'plughw:3,0'
        assert options.output == 'plughw:3,0'
        assert options.sample_rate == 16000
        assert options.channels == 2
        assert options.format == 's24le'
        assert options.frame_ms == 40
