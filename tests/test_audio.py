# -*- coding: utf-8 -*-

from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from app.audio import (pcm_frame_bytes, play_audio_sample, play_pcm_command,
                       record_audio_sample, record_pcm_command)
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
