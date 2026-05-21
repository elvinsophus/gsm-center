# Phone Calls, Audio Streams, and Recording Roadmap

This document describes how gsm-center should grow from SMS-only modem control
into generic phone-call and audio-session orchestration.

The guiding rule is the same one used for SMS: gsm-center should provide
interfaces and lifecycle signals, while deployments decide behavior through API
calls, WebSocket clients, and configured hooks.

## Design Principles

- Keep modem control and audio handling separate.
- Let the loop process own serial modems and live call objects.
- Let the API process create requests and expose state, not own hardware.
- Treat audio devices as reusable resources, not as GSM-only internals.
- Prefer hooks and managed commands over built-in business behavior.
- Store enough call and recording metadata to audit what happened.
- Avoid assuming a specific downstream use case such as voicemail, SIP, STT,
  TTS, AI agents, or human operators.

## Deployment Model

The current supervisor deployment runs two programs:

```text
gsm-center-api   -> HTTP API, writes requests to SQLite
gsm-center-loop  -> modem owner, executes call/SMS work
```

This model should remain the default. The API should not instantiate
`GSMCenter` or open serial ports. Call actions such as dial, answer, and hangup
are queued in the database and executed by the loop process.

Audio devices should be opened by the component currently responsible for a
specific audio session. For managed call audio, that should be the loop process
or a child command started by the loop process.

## Audio Device Model

Add top-level audio device configuration:

```yaml
AUDIO_DEVICES:
  gsm_usb:
    input: "plughw:3,0"
    output: "plughw:3,0"
    sample_rate: 8000
    channels: 1
    format: s16le
    frame_ms: 20
```

Then bind a GSM modem to an audio device:

```yaml
DEVICES:
  /dev/ttyUSB0:
    calls:
      enabled: yes
      audio_device: gsm_usb
```

For the current USB sound card, ALSA exposes:

```text
/dev/snd/pcmC3D0p  playback/output
/dev/snd/pcmC3D0c  capture/input
```

Both are addressable as `hw:3,0` or `plughw:3,0`; `plughw` is preferred for
generic integrations because ALSA can perform format conversion.

## Call Lifecycle

Phone calls should use explicit lifecycle states:

```text
Outgoing: CREATED -> DIALING -> ANSWERED -> ENDED
Incoming: RINGING -> ANSWER_REQUESTED -> ANSWERED -> HANGUP_REQUESTED -> ENDED
Failure:  any active operation can become FAILED
```

Calls should emit hooks when significant lifecycle events happen:

```yaml
DEVICES:
  /dev/ttyUSB0:
    calls:
      hooks:
        received:
          command:
          env: {}
        dialing:
          command:
          env: {}
        answered:
          command:
          env: {}
        ended:
          command:
          env: {}
        failed:
          command:
          env: {}
```

Every call hook should receive environment variables equivalent to:

```text
CALL_ID
CALL_DIRECTION
CALL_OWN_NUMBER
CALL_OTHER_NUMBER
CALL_STATUS
CALL_STARTED_AT
CALL_ENDED_AT
CALL_AUDIO_DEVICE
CALL_AUDIO_INPUT
CALL_AUDIO_OUTPUT
```

## Managed Call Audio Command

For live audio, event hooks are not enough because the process is long-lived.
`calls.audio.command` starts when a call becomes `ANSWERED` and stops when the
call reaches `ENDED` or `FAILED`:

```yaml
DEVICES:
  /dev/ttyUSB0:
    calls:
      audio:
        command: "./scripts/call-audio-session.sh"
        env: {}
```

The command receives call and audio environment variables and decides what to
do. Examples include recording, bridging, playback, STT, TTS, or custom
operator workflows.

gsm-center tracks the child process and terminates it during:

- call hangup,
- remote call end,
- call failure,
- loop shutdown,
- loop restart cleanup.

## Recording Model

Call recording should be implemented as a generic media session, not as special
call behavior.

Recommended config:

```yaml
DEVICES:
  /dev/ttyUSB0:
    calls:
      recording:
        enabled: yes
        directory: "recordings"
        command: "ffmpeg -y -f alsa -ac 1 -ar 8000 -i {CALL_AUDIO_INPUT} -codec:a libmp3lame -b:a 32k {CALL_RECORDING_FILE}"
        format: mp3
        env: {}
```

The recording command can use ALSA, ffmpeg, arecord, sox, or another tool. A
compact, broadly compatible default records the capture side as mono MP3:

```bash
ffmpeg -y -f alsa -ac 1 -ar 8000 -i "$CALL_AUDIO_INPUT" \
  -codec:a libmp3lame -b:a 32k "$CALL_RECORDING_FILE"
```

At 32 kbps mono, recording size is roughly 240 KB per minute.

Later, duplex recording can be added by recording both capture and playback
streams and muxing them into one file.

Recording metadata should be stored separately from the call row:

```text
phone_call_recording
  id
  call_id
  created_at
  started_at
  ended_at
  path
  format
  status
  extra
```

Suggested recording statuses:

```text
CREATED -> RECORDING -> COMPLETED
FAILED
```

## HTTP API Roadmap

Current call control and inspection:

```text
GET /calls
GET /calls/<id>
POST /calls
POST /calls/<id>/answer
POST /calls/<id>/hangup
```

Call recording inspection:

```text
GET /calls/<id>/recordings
```

Add audio device inspection:

```text
GET /audio/devices
GET /audio/devices/<name>
```

Audio smoke tests:

```text
POST /audio/devices/<name>/test-record
POST /audio/devices/<name>/test-play
```

The matching CLI commands are:

```bash
python manage.py test-audio-record NAME PATH --seconds 3
python manage.py test-audio-play NAME PATH
```

Here, `NAME` is an `AUDIO_DEVICES` key such as `gsm_usb`. For recording,
`PATH` is the output WAV file. For playback, `PATH` is the input WAV file.

Add recording control:

```text
POST /calls/<id>/recordings
POST /calls/<id>/recordings/<recording_id>/stop
```

These APIs should expose capabilities and state. They should not decide what
the recorded call is for.

## WebSocket API Roadmap

WebSockets should carry raw PCM frames for live integrations:

```text
WS /ws/audio/devices/<name>/input
WS /ws/audio/devices/<name>/output
WS /ws/audio/devices/<name>/duplex
WS /ws/calls/<id>/audio
```

Recommended stream format:

```text
format=s16le
sample_rate=8000
channels=1
frame_ms=20
```

This enables future integrations:

- STT subscribes to input frames.
- TTS publishes output frames.
- A bridge service connects call audio to another network.
- A browser UI monitors or participates in a call.

## Implementation Steps

### Step 1: Stabilize Call Control

- Keep call queueing in SQLite.
- Keep modem operations in the loop process.
- Ensure stale in-flight calls are marked ended after loop restart.
- Ensure terminal calls cannot be moved back into request states.
- Add call listing and detail APIs.

### Step 2: Add Audio Device Configuration

- Add `AUDIO_DEVICES`.
- Add `calls.audio_device` reference under `DEVICES`.
- Add validation and runtime lookup helpers.
- Add CLI/API endpoints to list configured audio devices.

### Step 3: Add Audio Smoke Tests

- Add HTTP or CLI commands to record a short sample.
- Add HTTP or CLI commands to play a short sample.
- Keep these APIs generic and independent from calls.

### Step 4: Add Call Hooks

- Add `on_call_dialing`, `on_call_answered`, `on_call_ended`, and
  `on_call_failed` under `calls.hooks`. This is implemented for grouped
  config and legacy flat keys.
- Pass call and audio environment variables to every hook. Implemented hook
  vars include `CALL_ID`, `CALL_DIRECTION`, `CALL_OWN_NUMBER`,
  `CALL_OTHER_NUMBER`, `CALL_CALLER`, `CALL_RECIPIENT`, `CALL_STATUS`,
  `CALL_STARTED_AT`, `CALL_ENDED_AT`, `CALL_AUDIO_DEVICE`,
  `CALL_AUDIO_INPUT`, and `CALL_AUDIO_OUTPUT`.
- Preserve `calls.hooks.received` as the notification point for incoming calls.

### Step 5: Add Managed Call Audio Command

- Start `calls.audio.command` when a call is answered. Implemented.
- Stop it when the call ends or fails. Implemented.
- Track PID/process state in memory and record metadata in DB `extra`.
  Implemented.
- Ensure loop shutdown cleans up child processes. Implemented.

### Step 6: Add Call Recording

- Add recording DB table. Implemented as `phone_call_recording`.
- Add recording config. Implemented under `calls.recording`.
- Start recording through a generic command or managed recorder. Implemented
  through `calls.recording.command`.
- Store recording path, status, timestamps, and errors. Implemented.
- Add APIs to list recordings for a call. Implemented as
  `GET /calls/<id>/recordings`.

### Step 7: Add WebSocket Audio Streams

- Expose input, output, and duplex streams.
- Use explicit PCM stream parameters.
- Add backpressure and one-owner rules for playback.
- Make this the foundation for browser audio, STT, and TTS.

### Step 8: Add Optional STT/TTS Adapters

- Keep STT/TTS outside the core by default.
- Provide hooks or commands that consume/produce PCM.
- Add higher-level convenience APIs only after the lower-level stream model is
  stable.

## Non-Goals

- Do not build a fixed voicemail behavior into the core.
- Do not require a specific STT, TTS, SIP, or AI provider.
- Do not assume audio hardware numbering such as `hw:3,0` is stable forever.
- Do not let the API process open GSM serial ports.
- Do not make recording mandatory for all calls.
