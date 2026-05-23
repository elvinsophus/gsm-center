# -*- coding: utf-8 -*-

from subprocess import CompletedProcess
from subprocess import TimeoutExpired
from unittest.mock import Mock, patch

import pytest

from app.audio import (AudioPipeline, discover_alsa_audio_cards,
                       pcm_frame_bytes, play_audio_sample,
                       play_pcm_command, probe_audio_input,
                       record_audio_sample,
                       record_pcm_command, start_audio_input_command,
                       start_audio_output_command, stop_audio_pipeline)
from app.main import GSMCenter


def audio_device(input_='plughw:3,0', output='plughw:3,0'):
    return GSMCenter.AudioDeviceOptions(
        'gsm_usb', input_, output, 8000, 1, 's16le', 20)


class TestRecordAudioSample:

    def test_runs_arecord_with_configured_input(self):
        completed = CompletedProcess([], 0, stdout='ok', stderr='')
        with patch('app.audio.subprocess.run',
                   return_value=completed) as run:
            result = record_audio_sample(
                audio_device(), '/tmp/sample.wav', seconds=2)

        assert result.command == [
            'arecord',
            '-D', 'plughw:3,0',
            '-f', 'S16_LE',
            '-r', '8000',
            '-c', '1',
            '-d', '2',
            '-t', 'wav',
            '/tmp/sample.wav',
        ]
        run.assert_called_once_with(
            result.command, capture_output=True, check=True, text=True,
            timeout=7)
        assert result.stdout == 'ok'

    def test_requires_input(self):
        with pytest.raises(ValueError, match='no input'):
            record_audio_sample(audio_device(input_=''), '/tmp/sample.wav')

    def test_limits_seconds(self):
        with pytest.raises(ValueError, match='no greater than 60'):
            record_audio_sample(audio_device(), '/tmp/sample.wav', seconds=61)


class TestPlayAudioSample:

    def test_runs_aplay_with_configured_output(self):
        completed = CompletedProcess([], 0, stdout='', stderr='')
        with patch('app.audio.subprocess.run',
                   return_value=completed) as run:
            result = play_audio_sample(audio_device(), '/tmp/sample.wav')

        assert result.command == [
            'aplay', '-D', 'plughw:3,0', '/tmp/sample.wav']
        run.assert_called_once_with(
            result.command, capture_output=True, check=True, text=True,
            timeout=None)

    def test_requires_output(self):
        with pytest.raises(ValueError, match='no output'):
            play_audio_sample(audio_device(output=''), '/tmp/sample.wav')


class TestProbeAudioInput:

    def test_probes_each_rate(self):
        completed = CompletedProcess([], 0, stdout='', stderr='')
        with patch('app.audio.subprocess.run',
                   return_value=completed) as run:
            results = probe_audio_input(
                'plughw:3,0', sample_rates=[8000, 48000],
                backend='arecord')

        assert [r.sample_rate for r in results] == [8000, 48000]
        assert [r.ok for r in results] == [True, True]
        assert run.call_args_list[0].args[0] == [
            'arecord',
            '-D', 'plughw:3,0',
            '-f', 'S16_LE',
            '-r', '8000',
            '-c', '1',
            '-d', '1',
            '-t', 'raw',
            '/dev/null',
        ]
        assert run.call_args_list[1].args[0][6] == '48000'

    def test_records_failed_rate(self):
        completed = CompletedProcess([], 1, stdout='', stderr='nope')
        with patch('app.audio.subprocess.run', return_value=completed):
            result = probe_audio_input(
                'plughw:3,0', sample_rates=[8000], backend='arecord')[0]

        assert result.ok is False
        assert result.return_code == 1
        assert result.stderr == 'nope'

    def test_timeout_output_is_normalised_to_text(self):
        error = TimeoutExpired(['arecord'], 1)
        error.stdout = b'partial'
        error.stderr = b''
        with patch('app.audio.subprocess.run', side_effect=error):
            result = probe_audio_input(
                'plughw:3,0', sample_rates=[8000], backend='arecord')[0]

        assert result.ok is False
        assert result.stdout == 'partial'
        assert result.stderr == 'timed out'

    def test_ffmpeg_backend_is_default(self):
        completed = CompletedProcess([], 0, stdout='', stderr='')
        with patch('app.audio.subprocess.run',
                   return_value=completed) as run:
            result = probe_audio_input(
                'plughw:3,0', sample_rates=[48000])[0]

        assert result.ok is True
        assert run.call_args.args[0] == [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-y',
            '-f', 'alsa',
            '-acodec', 'pcm_s16le',
            '-ac', '1',
            '-ar', '48000',
            '-i', 'plughw:3,0',
            '-t', '1',
            '-f', 'null',
            '-',
        ]


class TestDiscoverALSAAudioCards:

    def test_groups_capture_and_playback_by_card(self):
        cards_text = (
            ' 3 [Device         ]: USB-Audio - USB Audio Device\n'
            '                      C-Media Electronics Inc. USB Audio Device\n'
        )
        capture = CompletedProcess([], 0, stdout=(
            'card 3: Device [USB Audio Device], device 0: USB Audio '
            '[USB Audio]\n'
        ), stderr='')
        playback = CompletedProcess([], 0, stdout=(
            'card 3: Device [USB Audio Device], device 0: USB Audio '
            '[USB Audio]\n'
        ), stderr='')

        with patch('app.audio.Path.read_text', return_value=cards_text), \
                patch('app.audio.subprocess.run',
                      side_effect=[capture, playback]):
            cards = discover_alsa_audio_cards()

        assert len(cards) == 1
        card = cards[0]
        assert card.index == 3
        assert card.id == 'Device'
        assert card.name == 'USB-Audio - USB Audio Device'
        assert card.description == (
            'C-Media Electronics Inc. USB Audio Device')
        assert card.inputs[0].alsa_device == 'plughw:3,0'
        assert card.outputs[0].alsa_device == 'plughw:3,0'


class TestPCMStreamCommands:

    def test_record_pcm_command_uses_raw_configured_input(self):
        assert record_pcm_command(audio_device()) == [
            'arecord',
            '-D', 'plughw:3,0',
            '-f', 'S16_LE',
            '-r', '8000',
            '-c', '1',
            '-t', 'raw',
        ]

    def test_play_pcm_command_uses_raw_configured_output(self):
        assert play_pcm_command(audio_device()) == [
            'aplay',
            '-D', 'plughw:3,0',
            '-f', 'S16_LE',
            '-r', '8000',
            '-c', '1',
            '-t', 'raw',
        ]

    def test_pcm_frame_bytes_uses_configured_frame_duration(self):
        assert pcm_frame_bytes(audio_device()) == 320

    def test_pcm_frame_bytes_rejects_unknown_format(self):
        with pytest.raises(ValueError, match='unsupported audio format'):
            pcm_frame_bytes(audio_device()._replace(format='ulaw'))


class TestAudioCommandPipelines:

    def test_input_command_receives_raw_capture_on_stdin(self):
        source = Mock()
        source.stdout = Mock()
        sink = Mock()

        with patch('app.audio.subprocess.Popen',
                   side_effect=[source, sink]) as popen:
            pipeline = start_audio_input_command(
                audio_device(), './stt --raw', env={'MODE': 'stt'})

        assert pipeline == AudioPipeline(source, sink)
        assert popen.call_args_list[0].args[0][0] == 'arecord'
        assert popen.call_args_list[1].args[0] == ['./stt', '--raw']
        assert popen.call_args_list[1].kwargs['stdin'] is source.stdout
        assert popen.call_args_list[1].kwargs['env']['MODE'] == 'stt'
        source.stdout.close.assert_called_once()

    def test_output_command_feeds_raw_playback_from_stdout(self):
        source = Mock()
        source.stdout = Mock()
        sink = Mock()

        with patch('app.audio.subprocess.Popen',
                   side_effect=[source, sink]) as popen:
            pipeline = start_audio_output_command(
                audio_device(), './tts --raw', env={'MODE': 'tts'})

        assert pipeline == AudioPipeline(source, sink)
        assert popen.call_args_list[0].args[0] == ['./tts', '--raw']
        assert popen.call_args_list[1].args[0][0] == 'aplay'
        assert popen.call_args_list[1].kwargs['stdin'] is source.stdout
        assert popen.call_args_list[0].kwargs['env']['MODE'] == 'tts'
        source.stdout.close.assert_called_once()

    def test_stop_audio_pipeline_terminates_sink_and_source(self):
        source = Mock()
        source.poll.return_value = None
        source.returncode = 0
        sink = Mock()
        sink.poll.return_value = None
        sink.returncode = 0

        assert stop_audio_pipeline(AudioPipeline(source, sink)) == (0, 0)

        sink.terminate.assert_called_once()
        source.terminate.assert_called_once()
