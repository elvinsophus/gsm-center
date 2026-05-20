# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in
this repository.

## Project Overview

**gsm-center** is a Flask application that manages multiple GSM modems for SMS
and phone-call workflows. It exposes a REST API for queuing work and provides
CLI tools for querying SMS/call history and managing devices.

The app is intentionally interface-oriented: core code owns modem state,
persistence, and lifecycle transitions, while deployment-specific behavior is
configured through hooks, commands, and future audio APIs.

## Setup & Running

```bash
# Initial setup (creates venv, installs deps, copies config template)
./setup.sh

# Copy and edit configuration
cp config.yaml.template config.yaml
# Edit config.yaml: add device serial ports, SIM PINs, own phone numbers

# Run REST API (default port 25601)
./run_api.sh [PORT] [VENV_DIR]
# Or directly:
source venv/bin/activate && python run_api.py

# Run GSM modem listener loop
./run_loop.sh
# Or:
source venv/bin/activate && python manage.py loop [/dev/ttyUSB0]

# Interactive IPython shell (GSMCenter, config, and databases pre-imported)
python manage.py shell
```

## Deployment Shape

The supervisor deployment runs two programs:

```text
gsm-center-api   -> REST API, writes requests to SQLite
gsm-center-loop  -> modem owner, sends SMS, receives SMS, handles calls
```

Keep this ownership boundary intact. The API process should not instantiate
`GSMCenter` or open serial ports. Call actions are queued in SQLite and executed
by the loop process that owns the modem and live call objects.

## Tests

Run tests in the project venv:

```bash
pytest
```

The suite covers DB helpers, REST API behavior, utility functions, config
normalization, and call restart/request edge cases.

## CLI Commands

```bash
python manage.py loop [PORT]                       # Start modem listener for a port or all devices
python manage.py list_sent_smss [SENDER] -n 10     # View sent SMS
python manage.py list_received_smss [RCPT] -n 10   # View received SMS
python manage.py list_smss [NUMBER] -n 10          # View all SMS for a number
python manage.py list_sms_dialog NUM1 NUM2 -n 10   # View conversation thread
python manage.py preview_sms_dialogs [NUM] -n 10   # Preview all conversation threads
python manage.py list_phone_calls [OWN] -n 10      # View phone calls
python manage.py call CALLER RECIPIENT             # Queue outgoing phone call
python manage.py answer_call CALL_ID               # Queue answer request
python manage.py hangup_call CALL_ID               # Queue hangup request
python manage.py test                              # Healthcheck (prints "Hello world!")
```

## REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/own-numbers` | List active phone numbers (updated in last 60s) |
| `POST` | `/sms` | Queue SMS: `{"sender": "+...", "recipient": "+...", "content": "..."}` |
| `POST` | `/calls` | Queue outgoing call: `{"caller": "+...", "recipient": "+..."}` |
| `POST` | `/calls/<id>/answer` | Queue answer request for a ringing incoming call |
| `POST` | `/calls/<id>/hangup` | Queue hangup request for a non-terminal call |

## Architecture

### Entry Points

- `run_api.py` - WSGI entry point for Flask
- `manage.py` - Flask CLI with custom commands
- `app/__init__.py` - Flask app factory (`create_app`), logging config

### Core Classes (`app/main.py`)

**`GSMCenter`** manages a single modem on a serial port:

- Runs a `_loop()` background thread.
- Every loop tick updates SIM status, processes pending SMS, and processes
  pending phone-call requests.
- Every 300s checks network coverage and modem-stored SMS messages.
- `send_sms()` sends via modem and records to `SmsDB`.
- `process_pending_smss()` picks up CREATED pending SMS and advances status.
- `_handle_received_sms()` stores inbound SMS and optionally runs an SMS hook.
- `_handle_incoming_call()` records inbound calls, keeps the live call object,
  and optionally runs a call hook.
- `process_phone_call_requests()` dials queued calls and applies answer/hangup
  requests in the modem-owning loop process.

**`GSMStore`** is the data access layer, queryable by `own_number`:

- `add_pending_sms()` queues outgoing SMS.
- `add_phone_call()` queues outgoing phone calls.
- `request_phone_call_answer()` and `request_phone_call_hangup()` queue call
  actions.
- `list_smss()`, `list_dialog()`, `list_phone_calls()`,
  `list_active_own_numbers()` etc.

### Database (`app/db.py`)

SQLite tables use a thread-local connection wrapper:

- **`sim_card`** - device metadata (`gsm_port`, `phone_number`,
  `call_enabled`, `sms_enabled`, `updated_at`)
- **`pending_sms`** - outgoing SMS queue (`CREATED -> PENDING -> PROCESSED`)
- **`sms`** - sent/received SMS history
- **`phone_call`** - outgoing/incoming call history and request queue

## Flow

### SMS

Incoming:

```text
Modem callback -> _handle_received_sms() -> sms table -> optional hook
```

Outgoing:

```text
POST /sms -> pending_sms CREATED -> loop sends -> sms table updated
```

### Phone Calls

Outgoing:

```text
POST /calls -> phone_call CREATED -> loop dials -> DIALING/ANSWERED/ENDED
```

Incoming:

```text
Modem callback -> phone_call RINGING -> optional hook -> answer/hangup request
```

The live modem call object exists only in the loop process. On loop startup,
stale in-flight calls are marked `ENDED` so old rows do not remain actionable
after supervisor restarts.

## Configuration (`app/config.py`)

YAML-based, no environment variable overrides. Prefer grouped device config:

```yaml
DEFAULT_MOBILE_REGION: CN
SQLITE3_FILE: db.sqlite3

AUDIO_DEVICES:
  gsm_usb:
    input: plughw:3,0
    output: plughw:3,0
    sample_rate: 8000
    channels: 1
    format: s16le
    frame_ms: 20

DEVICES:
  /dev/ttyUSB0:
    baudrate: 115200
    pin: "1234"
    own_number: "+8613512345678"

    sms:
      enabled: yes
      on_received:
        command: "curl -X POST http://example.com/webhook"
        env: {}

    calls:
      enabled: yes
      audio_device: gsm_usb
      hooks:
        received:
          command: "./scripts/on-call-received.sh"
          env: {}
```

Legacy flat keys are still supported:

```yaml
sms_enabled:
call_enabled:
on_sms_received:
on_sms_received_env:
on_call_received:
on_call_received_env:
```

Grouped config takes precedence when both forms are present.

## Audio Roadmap

Phone-call audio, call recording, WebSocket streams, and future STT/TTS
integrations are planned in `docs/call-audio-roadmap.md`.

Keep audio generic:

- Audio devices are reusable resources, not GSM-only internals.
- Calls may bind to an audio device.
- Hooks and managed commands decide behavior.
- Recording should be modeled as a media session with metadata, not as fixed
  built-in call behavior.

## Key Implementation Notes

- **Phone numbers**: Always normalized to E.164 (`+CC...`).
  `simplify_number()` strips country code for local modem display/dialing.
- **Threading**: One `GSMCenter` per port, each with its own background thread.
  SQLite connections are per-thread via `threading.local()`.
- **Error handling**: `safe()` wraps loop callbacks to log exceptions without
  crashing the loop.
- **Ownership**: Do not let multiple loop processes own the same modem port.
- **Compatibility**: Preserve legacy flat config keys while implementing grouped
  config for new behavior.
