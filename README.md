# gsm-center

gsm-center manages GSM modems for SMS and phone-call workflows. It exposes a
small REST API for queuing work, while the modem listener process owns the
serial devices and performs the actual modem operations.

## Quick Start

### 1. Install

On the Linux machine that has the GSM modem attached:

```bash
git clone https://github.com/elvinsophus/gsm-center.git
cd gsm-center
./setup.sh
```

`setup.sh` creates a Python virtual environment, installs dependencies, and
creates `config.yaml` if needed. When run in an interactive terminal, it asks
for the modem serial port, phone number, SMS/call choices, and can help choose
an ALSA sound card for call audio. Use `--reconfigure` to run the wizard again,
or `--no-config-wizard` to copy the template without prompts.

If you are setting up manually:

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
cp config.yaml.template config.yaml
```

Install system tools for audio discovery, smoke tests, and MP3 recording:

```bash
sudo apt install alsa-utils ffmpeg
```

### 2. Find The GSM Serial Port

If you used the interactive setup wizard, this may already be configured. To
check manually, plug in the modem and inspect serial devices:

```bash
ls /dev/ttyUSB*
dmesg | grep ttyUSB
```

Choose the modem AT-command port, then put it under `DEVICES` in
`config.yaml`.

### 3. Configure SMS And Calls

If you skipped the wizard, start with a minimal `config.yaml`:

```yaml
DEFAULT_MOBILE_REGION: CN
SQLITE3_FILE: db.sqlite3

DEVICES:
  /dev/ttyUSB5:
    baudrate: 115200
    pin: "1234"
    own_number: "+8613512345678"

    sms:
      enabled: yes

    calls:
      enabled: yes
```

The phone number should be in E.164 form. For example, a China number should
look like `+8613512345678`.

### 4. Find And Probe Audio Devices

The setup wizard can do this for you. To run the same steps manually, first
list ALSA sound cards:

```bash
. venv/bin/activate
python manage.py discover-audio-devices --name gsm_usb
```

The command prints capture/playback endpoints and suggests `AUDIO_DEVICES`
blocks. Pick the sound card connected to the GSM module's audio jack.

Then probe the selected ALSA device:

```bash
python manage.py probe-audio-device gsm_usb --input plughw:3,0 --output plughw:3,0
```

Use the suggested block in `config.yaml`, for example:

```yaml
AUDIO_DEVICES:
  gsm_usb:
    input: "plughw:3,0"
    output: "plughw:3,0"
    sample_rate: 48000
    channels: 1
    format: s16le
    frame_ms: 20

DEVICES:
  /dev/ttyUSB5:
    calls:
      enabled: yes
      audio_device: gsm_usb
```

The probe defaults to `ffmpeg` because that matches the recommended MP3
recording path. Use `--backend arecord` when you want to check the raw PCM path
used by WebSocket input streams.

### 5. Optional Call Recording

Recordings are disabled unless configured. Enable them under the device's
`calls.recording` block:

```yaml
DEVICES:
  /dev/ttyUSB5:
    calls:
      enabled: yes
      audio_device: gsm_usb
      recording:
        enabled: yes
        directory: "recordings"
        format: mp3
        command: "ffmpeg -y -f alsa -ac 1 -ar 48000 -i {CALL_AUDIO_INPUT} -codec:a libmp3lame -b:a 32k {CALL_RECORDING_FILE}"
        env: {}
        hooks:
          completed:
            command: "./scripts/on-recording-completed.sh"
            env: {}
          failed:
            command: "./scripts/on-recording-failed.sh"
            env: {}
```

Use the sample rate recommended by `probe-audio-device`.
Recording hooks run after the recording row has been finalized. They receive
the normal call hook environment plus `CALL_RECORDING_ID`,
`CALL_RECORDING_FILE`, `CALL_RECORDING_FORMAT`, `CALL_RECORDING_STATUS`,
`CALL_RECORDING_STARTED_AT`, and `CALL_RECORDING_ENDED_AT`.

### 6. Run The Service

Run the API and modem loop in separate terminals:

```bash
. venv/bin/activate
./run_api.sh 25601 venv
```

By default the API binds to `127.0.0.1`. If another machine or a Docker
container needs to reach it, bind to an address reachable from that network:

```bash
./run_api.sh 25601 venv 0.0.0.0
# or:
GSM_CENTER_API_HOST=0.0.0.0 ./run_api.sh 25601 venv
```

Only expose the API on a trusted network or behind your own access controls.

```bash
. venv/bin/activate
./run_loop.sh
```

Or run the loop for one modem only:

```bash
python manage.py loop /dev/ttyUSB5
```

The API queues work in SQLite. The loop owns the modem serial port and performs
SMS/call actions.

### 7. Smoke Test

Check active own numbers:

```bash
curl http://127.0.0.1:25601/own-numbers
```

Send an SMS:

```bash
curl -X POST http://127.0.0.1:25601/sms \
  -H 'Content-Type: application/json' \
  -d '{"sender":"+8613512345678","recipient":"+8613812345678","content":"hello"}'
```

Queue an outgoing call:

```bash
python manage.py call +8613512345678 +8613812345678
python manage.py list-calls +8613512345678
```

For incoming ringing calls, `answer-call` and `hangup-call` may omit the call
ID when exactly one call is eligible:

```bash
python manage.py answer-call
python manage.py hangup-call
```

For a ringing incoming call, `hangup-call` rejects the call without answering
it. Some carriers present this to the caller as busy.

## Runtime Shape

The normal deployment runs two processes:

```text
gsm-center-api   -> REST API, writes requests to SQLite
gsm-center-loop  -> modem owner, sends SMS, receives SMS, handles calls
```

This split is intentional. The API process should not open modem serial ports.
For calls, the API writes answer/hangup/dial requests and the loop process
executes them.

The API is served by `run_api.sh` through Gunicorn with exactly one threaded
worker, so HTTP routes and WebSocket audio streams share one application
process. WebSocket routes may open ALSA audio devices, but they still do not
instantiate `GSMCenter` or open modem serial ports.
`run_api.sh` binds to `127.0.0.1` by default; pass a third argument or set
`GSM_CENTER_API_HOST` when the API must be reachable from Docker or another
host.

## Current API

```text
GET  /own-numbers
GET  /contacts
POST /contacts
DELETE /contacts/<alias>
GET  /audio/devices
GET  /audio/devices/<name>
POST /audio/devices/<name>/test-record
POST /audio/devices/<name>/test-play
WS   /ws/audio/devices/<name>/input
WS   /ws/audio/devices/<name>/output
WS   /ws/audio/devices/<name>/duplex
WS   /ws/calls/<id>/audio
POST /sms
GET  /calls
GET  /calls/<id>
GET  /calls/<id>/recordings
POST /calls
POST /calls/<id>/answer
POST /calls/<id>/hangup
```

## Current CLI

```bash
python manage.py loop [PORT]
python manage.py list-contacts
python manage.py set-contact ALIAS PHONE_NUMBER
python manage.py delete-contact ALIAS
python manage.py list-sent-smses [SENDER] -n 10
python manage.py list-received-smses [RCPT] -n 10
python manage.py list-smses [NUMBER] -n 10
python manage.py list-sms-dialog NUM1 NUM2 -n 10
python manage.py preview-sms-dialogs [NUM] -n 10
python manage.py list-calls [OWN_NUMBER] -n 10
python manage.py call CALLER RECIPIENT
python manage.py answer-call [CALL_ID]
python manage.py hangup-call [CALL_ID]
python manage.py list-audio-devices
python manage.py discover-audio-devices --name gsm_usb
python manage.py probe-audio-device [NAME] --input DEV --output DEV
python manage.py test-audio-record NAME PATH --seconds 3  # NAME: AUDIO_DEVICES key; PATH: output WAV
python manage.py test-audio-play NAME PATH                 # NAME: AUDIO_DEVICES key; PATH: input WAV
```

## Device Configuration Shape

Prefer grouped SMS and call settings for new config:

```yaml
CONTACTS:
  alice: "+8613512345678"
  bob: "+8613812345678"

DEVICES:
  /dev/ttyUSB0:
    baudrate: 115200
    pin: "1234"
    own_number: "+8613512345678"

    sms:
      enabled: yes
      on_received:
        command: "./scripts/on-sms.sh"
        env: {}

    calls:
      enabled: yes
      outgoing:
        answer_timeout: 45
      audio_device: gsm_usb
      hooks:
        received:
          command: "./scripts/on-call.sh"
          env: {}
        answered:
          command: "./scripts/on-call-answered.sh"
          env: {}
      audio:
        command: "./scripts/call-audio-session.sh"
        env: {}
        input:
          command: "./scripts/call-stt.sh"
          env: {}
        output:
          command: "./scripts/call-tts.sh"
          env: {}
      recording:
        enabled: yes
        directory: "recordings"
        command: "ffmpeg -y -f alsa -ac 1 -ar 48000 -i {CALL_AUDIO_INPUT} -codec:a libmp3lame -b:a 32k {CALL_RECORDING_FILE}"
        format: mp3
        env: {}
        hooks:
          completed:
            command: "./scripts/on-recording-completed.sh"
            env: {}
          failed:
            command: "./scripts/on-recording-failed.sh"
            env: {}
```

`CONTACTS` is optional seed data for the `contact` table. Aliases may be used
anywhere a sender, recipient, caller, callee, own number, or peer number is
accepted by the API or CLI. Aliases are resolved to phone numbers before SMSes
and calls are stored, so history tables still contain only phone numbers. Edit
contacts dynamically with `set-contact`/`delete-contact` or the `/contacts`
API. Alias names must start with a letter and contain only letters, numbers,
underscores, dots, or hyphens; alias matching is case-insensitive, and each
normalized phone number may have only one alias.

`calls.outgoing.answer_timeout` is optional and defaults to `0`, which disables
the local timeout. When set to a positive number, unanswered outgoing calls are
hung up after that many seconds and recorded with
`ended_reason=outgoing_answer_timeout`.

Legacy flat keys such as `sms_enabled`, `call_enabled`,
`on_sms_received`, and `on_call_received` are still supported.

## Design Docs

- [Multipart SMS Handling](docs/multipart-sms.md)
- [Phone Calls, Audio Streams, and Recording Roadmap](docs/call-audio-roadmap.md)

## License

Copyright (C) 2026 Elvin SEAH

Unless otherwise noted, gsm-center source files are licensed under the GNU
General Public License v3.0 or later: see [LICENSE](LICENSE).

SPDX-License-Identifier: GPL-3.0-or-later
