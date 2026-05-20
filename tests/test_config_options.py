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
        })

        assert options.sms_enabled is True
        assert options.call_enabled is True
        assert options.on_sms_received == './sms.sh'
        assert options.on_sms_received_env == {'A': '1'}
        assert options.on_call_received == './call.sh'
        assert options.on_call_received_env == {'B': '2'}

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
                'hooks': {
                    'received': {
                        'command': './call.sh',
                        'env': {'B': '2'},
                    },
                },
            },
        })

        assert options.sms_enabled is True
        assert options.call_enabled is True
        assert options.on_sms_received == './sms.sh'
        assert options.on_sms_received_env == {'A': '1'}
        assert options.on_call_received == './call.sh'
        assert options.on_call_received_env == {'B': '2'}

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
