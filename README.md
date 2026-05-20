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

## Current API

```text
GET  /own-numbers
POST /sms
GET  /calls
GET  /calls/<id>
POST /calls
POST /calls/<id>/answer
POST /calls/<id>/hangup
```

## Current CLI

```bash
python manage.py loop [PORT]
python manage.py list_sent_smss [SENDER] -n 10
python manage.py list_received_smss [RCPT] -n 10
python manage.py list_smss [NUMBER] -n 10
python manage.py list_sms_dialog NUM1 NUM2 -n 10
python manage.py preview_sms_dialogs [NUM] -n 10
python manage.py list_phone_calls [OWN_NUMBER] -n 10
python manage.py call CALLER RECIPIENT
python manage.py answer_call CALL_ID
python manage.py hangup_call CALL_ID
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
```

Legacy flat keys such as `sms_enabled`, `call_enabled`,
`on_sms_received`, and `on_call_received` are still supported.

## Design Docs

- [Phone Calls, Audio Streams, and Recording Roadmap](docs/call-audio-roadmap.md)
