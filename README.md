# gsm-center

gsm-center manages GSM modems for SMS and phone-call workflows. It exposes a
small REST API for queuing work, while the modem listener process owns the
serial devices and performs the actual modem operations.

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

## Current API

```text
GET  /own-numbers
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
python manage.py list-sent-smss [SENDER] -n 10
python manage.py list-received-smss [RCPT] -n 10
python manage.py list-smss [NUMBER] -n 10
python manage.py list-sms-dialog NUM1 NUM2 -n 10
python manage.py preview-sms-dialogs [NUM] -n 10
python manage.py list-phone-calls [OWN_NUMBER] -n 10
python manage.py call CALLER RECIPIENT
python manage.py answer-call CALL_ID
python manage.py hangup-call CALL_ID
python manage.py list-audio-devices
python manage.py test-audio-record NAME PATH --seconds 3  # NAME: AUDIO_DEVICES key; PATH: output WAV
python manage.py test-audio-play NAME PATH                 # NAME: AUDIO_DEVICES key; PATH: input WAV
```

## Device Configuration Shape

Prefer grouped SMS and call settings for new config:

```yaml
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
        command: "ffmpeg -y -f alsa -ac 1 -ar 8000 -i {CALL_AUDIO_INPUT} -codec:a libmp3lame -b:a 32k {CALL_RECORDING_FILE}"
        format: mp3
        env: {}
```

Legacy flat keys such as `sms_enabled`, `call_enabled`,
`on_sms_received`, and `on_call_received` are still supported.

## Design Docs

- [Multipart SMS Handling](docs/multipart-sms.md)
- [Phone Calls, Audio Streams, and Recording Roadmap](docs/call-audio-roadmap.md)
