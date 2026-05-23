# -*- coding: utf-8 -*-

from json import loads as json_loads
from unittest.mock import Mock, patch

from app.audio import AudioPipeline
from gsmmodem.modem import IncomingCall

from app.main import (GSMCenter, GSMStore, ReceivedSMSPartInfo,
                      ReceivedSMSPartStatus, ReceivedSMSStatus)

OWN_NUMBER = '+12025550111'
OTHER_NUMBER = '+12025550122'
THIRD_NUMBER = '+12025550133'


class TestPhoneCallRequests:

    def test_hangup_request_rejects_finished_call(self, fresh_db):
        db = GSMStore.phone_call_db
        mid = db.insert('INCOMING', OWN_NUMBER, OTHER_NUMBER, 'ENDED')

        assert GSMStore.request_phone_call_hangup(mid) is False
        assert db.get(mid)['status'] == 'ENDED'

    def test_hangup_request_is_idempotent(self, fresh_db):
        db = GSMStore.phone_call_db
        mid = db.insert('INCOMING', OWN_NUMBER, OTHER_NUMBER, 'HANGUP_REQUESTED')

        assert GSMStore.request_phone_call_hangup(mid) is True
        assert db.get(mid)['status'] == 'HANGUP_REQUESTED'

    def test_hangup_request_records_source_status(self, fresh_db):
        db = GSMStore.phone_call_db
        mid = db.insert('INCOMING', OWN_NUMBER, OTHER_NUMBER, 'RINGING')

        assert GSMStore.request_phone_call_hangup(mid) is True

        row = db.get(mid)
        assert row['status'] == 'HANGUP_REQUESTED'
        assert json_loads(row['extra']) == {
            'hangup_requested_from': 'RINGING'}

    def test_local_ringing_incoming_hangup_records_rejection(self, fresh_db):
        db = GSMStore.phone_call_db
        mid = db.insert('INCOMING', OWN_NUMBER, OTHER_NUMBER,
                        'HANGUP_REQUESTED')
        db.update_status(
            mid, 'HANGUP_REQUESTED',
            extra={'hangup_requested_from': 'RINGING'})
        center = object.__new__(GSMCenter)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._modem = Mock()
        call = IncomingCall(
            center._modem, OTHER_NUMBER, None, None, 1, 'VOICE')
        center._active_calls = {mid: call}
        center._call_ring_counts = {mid: 1}
        center._modem.activeCalls = {call.id: call}
        center._options = GSMCenter.DeviceOptions(call_enabled=True)
        center._call_audio_processes = {}
        center._call_audio_input_pipelines = {}
        center._call_audio_output_pipelines = {}
        center._call_recording_processes = {}
        center.logger = Mock()
        center._run_call_hook = Mock()

        center._hangup_phone_call(mid)

        row = db.get(mid)
        assert row['status'] == 'ENDED'
        assert json_loads(row['extra']) == {
            'ended_by': 'local',
            'ended_reason': 'local_rejected',
            'ended_role': 'dialee',
        }
        center._modem.write.assert_called_once_with('AT+CHUP')
        assert call.ringing is False
        assert call.active is False
        assert call.id not in center._modem.activeCalls

    def test_ringing_hangup_with_generic_call_falls_back_to_hangup(
            self, fresh_db):
        db = GSMStore.phone_call_db
        mid = db.insert('INCOMING', OWN_NUMBER, OTHER_NUMBER,
                        'HANGUP_REQUESTED')
        db.update_status(
            mid, 'HANGUP_REQUESTED',
            extra={'hangup_requested_from': 'RINGING'})
        call = Mock()

        center = object.__new__(GSMCenter)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._active_calls = {mid: call}
        center._call_ring_counts = {mid: 1}
        center._modem = Mock()
        center._options = GSMCenter.DeviceOptions(call_enabled=True)
        center._call_audio_processes = {}
        center._call_audio_input_pipelines = {}
        center._call_audio_output_pipelines = {}
        center._call_recording_processes = {}
        center.logger = Mock()
        center._run_call_hook = Mock()

        center._hangup_phone_call(mid)

        call.hangup.assert_called_once_with()
        center._modem.write.assert_not_called()

    def test_answer_with_generic_call_marks_failed(self, fresh_db):
        db = GSMStore.phone_call_db
        mid = db.insert('INCOMING', OWN_NUMBER, OTHER_NUMBER,
                        'ANSWER_REQUESTED')
        call = Mock()

        center = object.__new__(GSMCenter)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._active_calls = {mid: call}
        center._call_ring_counts = {mid: 1}
        center._modem = Mock()
        center._options = GSMCenter.DeviceOptions(call_enabled=True)
        center._call_audio_processes = {}
        center._call_audio_input_pipelines = {}
        center._call_audio_output_pipelines = {}
        center._call_recording_processes = {}
        center.logger = Mock()
        center._run_call_hook = Mock()

        center._answer_phone_call(mid)

        row = db.get(mid)
        assert row['status'] == 'FAILED'
        assert json_loads(row['extra']) == {
            'error': 'live call is not an incoming call'}
        call.answer.assert_not_called()

    def test_incoming_call_without_caller_id_is_stored(self, fresh_db):
        center = object.__new__(GSMCenter)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._active_calls = {}
        center._call_ring_counts = {}
        center._modem = Mock()
        center._modem.write.return_value = []
        center.logger = Mock()
        center._run_call_hook = Mock()
        call = Mock()
        call.number = None

        center._handle_incoming_call(call)

        calls = center._store.list_phone_calls()
        assert len(calls) == 1
        assert calls[0].other_number == ''
        assert calls[0].caller == ''
        assert center._active_calls[calls[0].id] is call
        assert center._call_ring_counts[calls[0].id] == 1
        center.logger.info.assert_called_once_with(
            f'received incoming call #{calls[0].id} '
            f'from an unknown number')
        center._run_call_hook.assert_called_once_with(calls[0].id, 'received')

    def test_incoming_call_without_caller_id_uses_clcc_fallback(
            self, fresh_db):
        center = object.__new__(GSMCenter)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._active_calls = {}
        center._call_ring_counts = {}
        center._modem = Mock()
        center._modem.write.return_value = [
            '+CLCC: 1,1,4,0,0,"12025550122",145',
            'OK',
        ]
        center.logger = Mock()
        center._run_call_hook = Mock()
        call = Mock()
        call.number = None

        center._handle_incoming_call(call)

        calls = center._store.list_phone_calls()
        assert len(calls) == 1
        assert calls[0].other_number == OTHER_NUMBER
        assert calls[0].caller == OTHER_NUMBER
        assert center._call_ring_counts[calls[0].id] == 1
        center._modem.write.assert_called_once_with('AT+CLCC')
        assert center.logger.info.call_args_list[-1].args[0] == (
            f'received incoming call #{calls[0].id} from {OTHER_NUMBER!r}')

    def test_repeated_incoming_call_callback_does_not_insert_duplicate(
            self, fresh_db):
        center = object.__new__(GSMCenter)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._active_calls = {}
        center._call_ring_counts = {}
        center._modem = Mock()
        center.logger = Mock()
        center._run_call_hook = Mock()
        call = Mock()
        call.number = OTHER_NUMBER
        call.ringCount = 2

        center._handle_incoming_call(call)
        center._handle_incoming_call(call)

        calls = center._store.list_phone_calls()
        assert len(calls) == 1
        assert center._active_calls[calls[0].id] is call
        assert center._call_ring_counts[calls[0].id] == 2
        center._run_call_hook.assert_called_once_with(calls[0].id, 'received')
        assert center.logger.info.call_args_list[-1].args[0] == (
            f'incoming call #{calls[0].id} is still ringing; ring_count=2')

    def test_repeated_incoming_call_callback_with_new_object_uses_number(
            self, fresh_db):
        center = object.__new__(GSMCenter)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._active_calls = {}
        center._call_ring_counts = {}
        center._modem = Mock()
        center._modem.write.return_value = [
            '+CLCC: 1,1,4,0,0,"12025550122",145',
            'OK',
        ]
        center.logger = Mock()
        center._run_call_hook = Mock()
        first = Mock()
        first.number = None
        first.ringCount = 1
        second = Mock()
        second.number = None
        second.ringCount = 2

        center._handle_incoming_call(first)
        center._handle_incoming_call(second)

        calls = center._store.list_phone_calls()
        assert len(calls) == 1
        assert calls[0].other_number == OTHER_NUMBER
        assert center._active_calls[calls[0].id] is second
        assert center._call_ring_counts[calls[0].id] == 2
        center._run_call_hook.assert_called_once_with(calls[0].id, 'received')
        assert center.logger.info.call_args_list[-1].args[0] == (
            f'incoming call #{calls[0].id} is still ringing; ring_count=2')


class TestPhoneCallStartupCleanup:

    def test_clear_stale_phone_calls_marks_in_flight_calls_ended(
            self, fresh_db):
        db = GSMStore.phone_call_db
        stale_id = db.insert('INCOMING', OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        finished_id = db.insert('INCOMING', OWN_NUMBER, THIRD_NUMBER, 'ENDED')

        center = object.__new__(GSMCenter)
        center._options = GSMCenter.DeviceOptions(call_enabled=True)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center.logger = Mock()

        center._clear_stale_phone_calls()

        stale = db.get(stale_id)
        finished = db.get(finished_id)
        assert stale['status'] == 'ENDED'
        assert stale['ended_at'] is not None
        assert 'loop restarted' in stale['extra']
        assert finished['status'] == 'ENDED'

    def test_refresh_active_phone_calls_marks_disappeared_calls_ended(
            self, fresh_db):
        db = GSMStore.phone_call_db
        mid = db.insert('INCOMING', OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        call = Mock()

        center = object.__new__(GSMCenter)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._active_calls = {mid: call}
        center._call_ring_counts = {mid: 1}
        center._modem = Mock()
        center._modem.write.return_value = ['OK']
        center.logger = Mock()
        center._run_call_hook = Mock()
        center._options = GSMCenter.DeviceOptions(call_enabled=True)
        center._call_audio_processes = {}
        center._call_audio_input_pipelines = {}
        center._call_audio_output_pipelines = {}
        center._call_recording_processes = {}

        center._refresh_active_phone_calls()

        row = db.get(mid)
        assert row['status'] == 'ENDED'
        assert row['ended_at'] is not None
        assert json_loads(row['extra']) == {
            'ended_reason': 'remote_hangup_or_modem_cleared_call'}
        assert mid not in center._active_calls
        assert mid not in center._call_ring_counts


class TestPhoneCallHooks:

    def make_center(self):
        center = object.__new__(GSMCenter)
        center._options = GSMCenter.DeviceOptions(
            call_enabled=True,
            audio_device='gsm_usb',
            on_call_answered='./answered {CALL_ID} {CALL_STATUS}',
            on_call_answered_env={'CUSTOM': 'yes'})
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center.logger = Mock()
        return center

    def test_status_transition_runs_matching_hook(self, fresh_db):
        center = self.make_center()
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        audio = GSMCenter.AudioDeviceOptions(
            'gsm_usb', 'plughw:3,0', 'plughw:3,0', 8000, 1, 's16le', 20)

        with patch('app.main.AudioDeviceOptions.get', return_value=audio), \
                patch('app.main.run_system_command') as run:
            center._update_phone_call_status(
                mid, GSMCenter.PhoneCallStatus.ANSWERED, started_at=1700000000)

        assert run.call_count == 1
        command = run.call_args.args[0]
        env = run.call_args.kwargs['env']
        assert command == f'./answered {mid} ANSWERED'
        assert env['CALL_ID'] == str(mid)
        assert env['CALL_DIRECTION'] == 'INCOMING'
        assert env['CALL_OWN_NUMBER'] == OWN_NUMBER
        assert env['CALL_OTHER_NUMBER'] == OTHER_NUMBER
        assert env['CALL_CALLER'] == OTHER_NUMBER
        assert env['CALL_RECIPIENT'] == OWN_NUMBER
        assert env['CALL_STATUS'] == 'ANSWERED'
        assert env['CALL_STARTED_AT'] == '1700000000'
        assert env['CALL_AUDIO_DEVICE'] == 'gsm_usb'
        assert env['CALL_AUDIO_INPUT'] == 'plughw:3,0'
        assert env['CUSTOM'] == 'yes'

    def test_same_status_update_does_not_rerun_hook(self, fresh_db):
        center = self.make_center()
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'ANSWERED')

        with patch('app.main.run_system_command') as run:
            center._update_phone_call_status(
                mid, GSMCenter.PhoneCallStatus.ANSWERED)

        run.assert_not_called()


class TestManagedCallAudio:

    def make_center(self):
        center = object.__new__(GSMCenter)
        center._options = GSMCenter.DeviceOptions(
            call_enabled=True,
            audio_device='gsm_usb',
            call_audio_command='./audio {CALL_ID} {CALL_AUDIO_INPUT}',
            call_audio_env={'MODE': 'test'},
            call_audio_input_command='./stt {CALL_ID}',
            call_audio_input_env={'MODE': 'stt'},
            call_audio_output_command='./tts {CALL_ID}',
            call_audio_output_env={'MODE': 'tts'})
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._call_audio_processes = {}
        center._call_audio_input_pipelines = {}
        center._call_audio_output_pipelines = {}
        center._call_recording_processes = {}
        center.logger = Mock()
        return center

    def test_answered_call_starts_managed_audio_process(self, fresh_db):
        center = self.make_center()
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        process = Mock()
        process.pid = 1234
        audio = GSMCenter.AudioDeviceOptions(
            'gsm_usb', 'plughw:3,0', 'plughw:3,0', 8000, 1, 's16le', 20)

        with patch('app.main.AudioDeviceOptions.get', return_value=audio), \
                patch('app.main.subprocess.Popen',
                      return_value=process) as popen, \
                patch('app.main.start_audio_input_command'), \
                patch('app.main.start_audio_output_command'):
            center._update_phone_call_status(
                mid, GSMCenter.PhoneCallStatus.ANSWERED, started_at=1700000000)

        assert center._call_audio_processes[mid] is process
        popen.assert_called_once()
        assert popen.call_args.args[0] == ['./audio', str(mid), 'plughw:3,0']
        assert popen.call_args.kwargs['env']['MODE'] == 'test'
        row = GSMStore.phone_call_db.get(mid)
        assert '"call_audio_pid":1234' in row['extra']

    def test_answered_call_starts_input_output_pipelines(self, fresh_db):
        center = self.make_center()
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        audio = GSMCenter.AudioDeviceOptions(
            'gsm_usb', 'plughw:3,0', 'plughw:3,0', 8000, 1, 's16le', 20)
        input_pipeline = AudioPipeline(Mock(pid=2221), Mock(pid=2222))
        output_pipeline = AudioPipeline(Mock(pid=3331), Mock(pid=3332))

        with patch('app.main.AudioDeviceOptions.get', return_value=audio), \
                patch('app.main.subprocess.Popen'), \
                patch('app.main.start_audio_input_command',
                      return_value=input_pipeline) as start_input, \
                patch('app.main.start_audio_output_command',
                      return_value=output_pipeline) as start_output:
            center._update_phone_call_status(
                mid, GSMCenter.PhoneCallStatus.ANSWERED, started_at=1700000000)

        assert center._call_audio_input_pipelines[mid] is input_pipeline
        assert center._call_audio_output_pipelines[mid] is output_pipeline
        assert start_input.call_args.args[:2] == (audio, f'./stt {mid}')
        assert start_input.call_args.kwargs['env']['MODE'] == 'stt'
        assert start_output.call_args.args[:2] == (audio, f'./tts {mid}')
        assert start_output.call_args.kwargs['env']['MODE'] == 'tts'

    def test_terminal_call_stops_managed_audio_process(self, fresh_db):
        center = self.make_center()
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'ANSWERED')
        process = Mock()
        process.poll.return_value = None
        process.returncode = 0
        center._call_audio_processes[mid] = process
        center._call_audio_input_pipelines[mid] = AudioPipeline(
            Mock(), Mock())
        center._call_audio_output_pipelines[mid] = AudioPipeline(
            Mock(), Mock())

        with patch('app.main.stop_audio_pipeline',
                   return_value=(0, 0)) as stop_pipeline:
            center._update_phone_call_status(
                mid, GSMCenter.PhoneCallStatus.ENDED, ended_at=1700000060)

        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=5)
        assert mid not in center._call_audio_processes
        assert mid not in center._call_audio_input_pipelines
        assert mid not in center._call_audio_output_pipelines
        assert stop_pipeline.call_count == 2
        row = GSMStore.phone_call_db.get(mid)
        assert '"call_audio_return_code":0' in row['extra']

    def test_stop_all_managed_audio_processes(self, fresh_db):
        center = self.make_center()
        first = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'ANSWERED')
        second = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, THIRD_NUMBER, 'ANSWERED')
        center._call_audio_processes[first] = Mock()
        center._call_audio_processes[second] = Mock()
        center._call_audio_input_pipelines[first] = AudioPipeline(
            Mock(), Mock())
        center._call_audio_output_pipelines[second] = AudioPipeline(
            Mock(), Mock())

        with patch('app.main.stop_audio_pipeline', return_value=(0, 0)):
            center._stop_all_call_audio_processes()
            center._stop_all_call_audio_input_pipelines()
            center._stop_all_call_audio_output_pipelines()

        assert center._call_audio_processes == {}
        assert center._call_audio_input_pipelines == {}
        assert center._call_audio_output_pipelines == {}


class TestCallRecording:

    def make_center(self, tmp_path):
        center = object.__new__(GSMCenter)
        center._options = GSMCenter.DeviceOptions(
            call_enabled=True,
            audio_device='gsm_usb',
            call_recording_enabled=True,
            call_recording_directory=str(tmp_path),
            call_recording_command='./record {CALL_RECORDING_FILE}',
            call_recording_env={'MODE': 'record'},
            call_recording_format='mp3')
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._call_audio_processes = {}
        center._call_audio_input_pipelines = {}
        center._call_audio_output_pipelines = {}
        center._call_recording_processes = {}
        center.logger = Mock()
        return center

    def test_answered_call_starts_recording_process(self, fresh_db, tmp_path):
        center = self.make_center(tmp_path)
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'RINGING')
        process = Mock()
        process.pid = 4321

        with patch('app.main.subprocess.Popen',
                   return_value=process) as popen:
            center._update_phone_call_status(
                mid, GSMCenter.PhoneCallStatus.ANSWERED, started_at=1700000000)

        recordings = center._store.list_phone_call_recordings(mid)
        assert len(recordings) == 1
        recording = recordings[0]
        assert recording.status is GSMCenter.PhoneCallRecordingStatus.RECORDING
        assert recording.path.endswith('.mp3')
        assert center._call_recording_processes[mid][0] == recording.id
        assert center._call_recording_processes[mid][1] is process
        popen.assert_called_once()
        assert popen.call_args.args[0][0] == './record'
        assert popen.call_args.kwargs['env']['MODE'] == 'record'
        assert popen.call_args.kwargs['env']['CALL_RECORDING_ID'] == str(
            recording.id)

    def test_terminal_call_completes_recording(self, fresh_db, tmp_path):
        center = self.make_center(tmp_path)
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'ANSWERED')
        rid = GSMStore.phone_call_recording_db.insert(
            mid, str(tmp_path / 'call.wav'), 'wav',
            GSMCenter.PhoneCallRecordingStatus.RECORDING,
            started_at=1700000000)
        process = Mock()
        process.poll.return_value = None
        process.returncode = 0
        center._call_recording_processes[mid] = (rid, process)

        center._update_phone_call_status(
            mid, GSMCenter.PhoneCallStatus.ENDED, ended_at=1700000060)

        process.terminate.assert_called_once()
        recording = center._store.get_phone_call_recording(rid)
        assert recording.status is GSMCenter.PhoneCallRecordingStatus.COMPLETED
        assert recording.extra['return_code'] == 0

    def test_completed_recording_runs_hook_with_metadata(
            self, fresh_db, tmp_path):
        center = self.make_center(tmp_path)
        center._options = center._options._replace(
            call_recording_completed_command=(
                './done {CALL_ID} {CALL_RECORDING_ID} '
                '{CALL_RECORDING_STATUS}'),
            call_recording_completed_env={'TARGET': 'archive'})
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'ANSWERED')
        rid = GSMStore.phone_call_recording_db.insert(
            mid, str(tmp_path / 'call.mp3'), 'mp3',
            GSMCenter.PhoneCallRecordingStatus.RECORDING,
            started_at=1700000000)
        process = Mock()
        process.poll.return_value = None
        process.returncode = 0
        center._call_recording_processes[mid] = (rid, process)

        with patch('app.main.time', return_value=1700000061), \
                patch('app.main.run_system_command') as run:
            center._update_phone_call_status(
                mid, GSMCenter.PhoneCallStatus.ENDED, ended_at=1700000060)

        run.assert_called_once()
        command = run.call_args.args[0]
        env = run.call_args.kwargs['env']
        assert command == f'./done {mid} {rid} COMPLETED'
        assert env['CALL_ID'] == str(mid)
        assert env['CALL_STATUS'] == 'ENDED'
        assert env['CALL_RECORDING_ID'] == str(rid)
        assert env['CALL_RECORDING_FILE'] == str(tmp_path / 'call.mp3')
        assert env['CALL_RECORDING_FORMAT'] == 'mp3'
        assert env['CALL_RECORDING_STATUS'] == 'COMPLETED'
        assert env['CALL_RECORDING_STARTED_AT'] == '1700000000'
        assert env['CALL_RECORDING_ENDED_AT'] == '1700000061'
        assert env['TARGET'] == 'archive'

    def test_early_recording_exit_is_marked_failed(self, fresh_db, tmp_path):
        center = self.make_center(tmp_path)
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'ANSWERED')
        rid = GSMStore.phone_call_recording_db.insert(
            mid, str(tmp_path / 'call.mp3'), 'mp3',
            GSMCenter.PhoneCallRecordingStatus.RECORDING,
            started_at=1700000000,
            extra={'pid': 1234, 'command': './record call.mp3'})
        process = Mock()
        process.poll.return_value = 1
        process.returncode = 1
        center._call_recording_processes[mid] = (rid, process)

        center._check_call_recording_processes()

        recording = center._store.get_phone_call_recording(rid)
        assert recording.status is GSMCenter.PhoneCallRecordingStatus.FAILED
        assert recording.ended_at is not None
        assert recording.extra['return_code'] == 1
        assert 'exited while call was active' in recording.extra['error']
        assert mid not in center._call_recording_processes

    def test_failed_recording_runs_hook_with_metadata(
            self, fresh_db, tmp_path):
        center = self.make_center(tmp_path)
        center._options = center._options._replace(
            call_recording_failed_command=(
                './failed {CALL_RECORDING_ID} {CALL_RECORDING_STATUS}'))
        mid = GSMStore.phone_call_db.insert(
            'INCOMING', OWN_NUMBER, OTHER_NUMBER, 'ANSWERED')
        rid = GSMStore.phone_call_recording_db.insert(
            mid, str(tmp_path / 'call.mp3'), 'mp3',
            GSMCenter.PhoneCallRecordingStatus.RECORDING,
            started_at=1700000000,
            extra={'pid': 1234, 'command': './record call.mp3'})
        process = Mock()
        process.poll.return_value = 1
        process.returncode = 1
        center._call_recording_processes[mid] = (rid, process)

        with patch('app.main.time', return_value=1700000062), \
                patch('app.main.run_system_command') as run:
            center._check_call_recording_processes()

        run.assert_called_once()
        command = run.call_args.args[0]
        env = run.call_args.kwargs['env']
        assert command == f'./failed {rid} FAILED'
        assert env['CALL_ID'] == str(mid)
        assert env['CALL_RECORDING_STATUS'] == 'FAILED'
        assert env['CALL_RECORDING_ENDED_AT'] == '1700000062'


class TestMultipartSMS:

    def test_add_received_sms_waits_for_missing_parts(self, fresh_db):
        store = GSMStore(OWN_NUMBER)

        mid = store.add_received_sms(
            OTHER_NUMBER, 'world', ReceivedSMSStatus.UNREAD, 1700000001,
            ReceivedSMSPartInfo('abc', 2, 2))

        assert mid is None
        assert store.list_received_smss(sender=OTHER_NUMBER) == []

    def test_add_received_sms_assembles_out_of_order_parts(self, fresh_db):
        store = GSMStore(OWN_NUMBER)
        store.add_received_sms(
            OTHER_NUMBER, 'world', ReceivedSMSStatus.UNREAD, 1700000001,
            ReceivedSMSPartInfo('abc', 2, 2))

        mid = store.add_received_sms(
            OTHER_NUMBER, 'hello ', ReceivedSMSStatus.UNREAD, 1700000000,
            ReceivedSMSPartInfo('abc', 2, 1))

        sms = store.get_received_sms(mid)
        parts = GSMStore.received_sms_part_db.list_group(
            OWN_NUMBER, OTHER_NUMBER, 'abc')
        assert sms.content == 'hello world'
        assert sms.status is ReceivedSMSStatus.UNREAD
        assert all(
            p['status'] == ReceivedSMSPartStatus.ASSEMBLED.name
            for p in parts)
        assert all(p['sms_id'] == mid for p in parts)

    def test_assemble_all_received_sms_parts_handles_restart_state(
            self, fresh_db):
        store = GSMStore(OWN_NUMBER)
        part_db = GSMStore.received_sms_part_db
        part_db.insert(
            OWN_NUMBER, OTHER_NUMBER, 'hello ', 'abc', 2, 1,
            ReceivedSMSPartStatus.RECEIVED, time_=1700000000)
        part_db.insert(
            OWN_NUMBER, OTHER_NUMBER, 'world', 'abc', 2, 2,
            ReceivedSMSPartStatus.RECEIVED, time_=1700000001)

        count = store.assemble_all_received_sms_parts()

        messages = store.list_received_smss(sender=OTHER_NUMBER)
        assert count == 1
        assert len(messages) == 1
        assert messages[0].content == 'hello world'
        assert int(messages[0].time.timestamp()) == 1700000000

    def test_parse_8_bit_concat_udh(self):
        assert GSMCenter._parse_concat_udh(bytes.fromhex('0500032a0201')) == (
            '42', 2, 1)

    def test_parse_8_bit_concat_udh_without_length_prefix(self):
        assert GSMCenter._parse_concat_udh(bytes.fromhex('00032a0201')) == (
            '42', 2, 1)

    def test_parse_16_bit_concat_udh(self):
        assert GSMCenter._parse_concat_udh(bytes.fromhex('06080401020302')) == (
            '258', 3, 2)

    def test_parse_concat_udh_from_information_elements(self):
        ie = Mock()
        ie.encode.return_value = bytes.fromhex('00032a0201')

        assert GSMCenter._parse_concat_udh([ie]) == ('42', 2, 1)

    def test_received_hook_uses_integer_timestamp_for_assembled_sms(
            self, fresh_db):
        center = object.__new__(GSMCenter)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._options = GSMCenter.DeviceOptions(
            sms_enabled=True,
            on_sms_received='./sms {SMS_CONTENT} {SMS_TIMESTAMP}',
        )
        center.logger = Mock()

        first = Mock()
        first.number = OTHER_NUMBER
        first.text = 'hello '
        first.status = object()
        first.time.timestamp.return_value = 1700000000
        first.concat_reference = 'abc'
        first.concat_total = 2
        first.concat_sequence = 1

        second = Mock()
        second.number = OTHER_NUMBER
        second.text = 'world'
        second.status = object()
        second.time.timestamp.return_value = 1700000001
        second.concat_reference = 'abc'
        second.concat_total = 2
        second.concat_sequence = 2

        with patch('app.main.run_system_command') as run:
            center._handle_received_sms(first)
            center._handle_received_sms(second)

        run.assert_called_once()
        command = run.call_args.args[0]
        assert command == './sms hello world 1700000000'

    def test_multipart_receive_logs_parts_then_complete_sms(self, fresh_db):
        center = object.__new__(GSMCenter)
        center._own_number = OWN_NUMBER
        center._store = GSMStore(OWN_NUMBER)
        center._options = GSMCenter.DeviceOptions(sms_enabled=True)
        center.logger = Mock()

        first = Mock()
        first.number = OTHER_NUMBER
        first.text = 'hello '
        first.status = object()
        first.time.timestamp.return_value = 1700000000
        first.concat_reference = 'abc'
        first.concat_total = 2
        first.concat_sequence = 1

        second = Mock()
        second.number = OTHER_NUMBER
        second.text = 'world'
        second.status = object()
        second.time.timestamp.return_value = 1700000001
        second.concat_reference = 'abc'
        second.concat_total = 2
        second.concat_sequence = 2

        center._handle_received_sms(first)
        center._handle_received_sms(second)

        logs = [call.args[0] for call in center.logger.info.call_args_list]
        assert logs == [
            "received multipart SMS part from '+12025550122', length=6, "
            "sequence=1/2, reference='abc'; awaiting more",
            "received a new SMS from '+12025550122', length=11, "
            "assembled_from=2 multipart parts",
        ]
