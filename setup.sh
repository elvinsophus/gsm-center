#!/usr/bin/env bash

cd "$(dirname "$0")" || exit 1

RECONFIGURE=0
NO_CONFIG_WIZARD=0

for arg in "$@"; do
    case "${arg}" in
        --reconfigure)
            RECONFIGURE=1
            ;;
        --no-config-wizard)
            NO_CONFIG_WIZARD=1
            ;;
        -h|--help)
            cat <<'EOF'
Usage: ./setup.sh [--reconfigure] [--no-config-wizard]

Options:
  --reconfigure       Run the interactive config wizard even if config.yaml exists.
  --no-config-wizard  Copy config.yaml.template when config.yaml is missing.
EOF
            exit 0
            ;;
        *)
            echo "Unknown option: ${arg}" >&2
            exit 1
            ;;
    esac
done

function info() {
    echo -e "\e[01;34m$1\e[0m"
}
function error() {
    echo -e "\e[01;31m$1\e[0m"
    exit 1
}

function generate_config_interactively() {
    "${VENV_DIR}/bin/python" <<'PY'
from pathlib import Path
from shutil import which
from subprocess import run, TimeoutExpired
import glob
import re
import sys

from ruamel.yaml import YAML


CARD_RE = re.compile(r'^\s*(\d+)\s+\[([^\]]+)\]:\s+(.+)$')
DEVICE_RE = re.compile(
    r'^card\s+(\d+):\s+([^\[]+)\[([^\]]+)\],\s+device\s+(\d+):\s+'
    r'([^\[]+)\[([^\]]+)\]')


def ask(prompt, default=''):
    suffix = f' [{default}]' if default else ''
    value = input(f'{prompt}{suffix}: ').strip()
    return value or default


def ask_yes(prompt, default=True):
    default_text = 'Y/n' if default else 'y/N'
    while True:
        value = input(f'{prompt} [{default_text}]: ').strip().lower()
        if not value:
            return default
        if value in ('y', 'yes'):
            return True
        if value in ('n', 'no'):
            return False
        print('Please answer yes or no.')


def read_cards():
    cards = {}
    current = None
    try:
        content = Path('/proc/asound/cards').read_text()
    except OSError:
        return cards
    for line in content.splitlines():
        match = CARD_RE.match(line)
        if match:
            index, card_id, name = match.groups()
            current = int(index)
            cards[current] = {
                'id': card_id.strip(),
                'name': name.strip(),
                'description': '',
                'inputs': [],
                'outputs': [],
            }
        elif current is not None and line.strip():
            cards[current]['description'] = line.strip()
            current = None
    return cards


def read_endpoints(cards, kind):
    command = ['arecord' if kind == 'inputs' else 'aplay', '-l']
    try:
        completed = run(
            command, capture_output=True, check=False, text=True, timeout=5)
    except (OSError, TimeoutExpired):
        return
    for line in completed.stdout.splitlines():
        match = DEVICE_RE.match(line)
        if not match:
            continue
        card_index, _card_id, _card_name, device_index, device_name, stream = (
            match.groups())
        card_index = int(card_index)
        endpoint = {
            'alsa': f'plughw:{card_index},{int(device_index)}',
            'device_name': device_name.strip(),
            'stream': stream.strip(),
        }
        cards.setdefault(card_index, {
            'id': '',
            'name': '',
            'description': '',
            'inputs': [],
            'outputs': [],
        })[kind].append(endpoint)


def discover_cards():
    cards = read_cards()
    read_endpoints(cards, 'inputs')
    read_endpoints(cards, 'outputs')
    result = []
    for i in sorted(cards):
        card = dict(cards[i])
        card['index'] = i
        result.append(card)
    return result


def recommended_card(cards):
    useful = [c for c in cards if c['inputs'] and c['outputs']]
    if not useful:
        return None
    for card in useful:
        text = ' '.join([
            card.get('id', ''),
            card.get('name', ''),
            card.get('description', ''),
        ]).lower()
        if 'usb' in text:
            return card
    return useful[0]


def choose_card(cards):
    if not cards:
        print('No ALSA cards were found.')
        return None
    rec = recommended_card(cards)
    if rec:
        print(f'Recommended audio card: {rec["index"]} '
              f'({rec["id"] or rec["name"]})')
    print()
    for card in cards:
        marker = '*' if rec and card['index'] == rec['index'] else ' '
        print(f'{marker} card {card["index"]}: '
              f'{card["id"] or "-"} | {card["name"] or "-"}')
        if card.get('description'):
            print(f'    {card["description"]}')
        inputs = ', '.join(e['alsa'] for e in card['inputs']) or 'none'
        outputs = ', '.join(e['alsa'] for e in card['outputs']) or 'none'
        print(f'    inputs: {inputs}')
        print(f'    outputs: {outputs}')
    print()
    default = str(rec['index']) if rec else ''
    value = ask('Choose audio card number, or leave blank to skip audio',
                default)
    if not value:
        return None
    try:
        index = int(value)
    except ValueError:
        print('Invalid card number; skipping audio.')
        return None
    for card in cards:
        if card['index'] == index:
            return card
    print('Card number not found; skipping audio.')
    return None


def probe_rate(device):
    if not device or not which('ffmpeg'):
        return 48000
    rates = [8000, 16000, 44100, 48000]
    ok = []
    print()
    print(f'Probing capture sample rates for {device} with ffmpeg...')
    for rate in rates:
        command = [
            'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'alsa', '-acodec', 'pcm_s16le', '-ac', '1',
            '-ar', str(rate), '-i', device, '-t', '1', '-f', 'null', '-',
        ]
        try:
            completed = run(
                command, capture_output=True, check=False, text=True,
                timeout=6)
        except TimeoutExpired:
            completed = None
        if completed and completed.returncode == 0:
            ok.append(rate)
            print(f'  {rate}: ok')
        else:
            print(f'  {rate}: failed')
    if not ok:
        print('No tested rate worked; using 48000 as a placeholder.')
        return 48000
    for rate in (8000, 16000, 48000, 44100):
        if rate in ok:
            return rate
    return ok[0]


def main():
    print()
    print('Interactive gsm-center configuration')
    print()
    region = ask('Default mobile region', 'CN')
    sqlite_file = ask('SQLite database file', 'db.sqlite3')

    ports = sorted(glob.glob('/dev/ttyUSB*'))
    if ports:
        print()
        print('Detected serial ports:')
        for port in ports:
            print(f'  {port}')
    port = ask('GSM modem AT-command serial port',
               ports[-1] if ports else '/dev/ttyUSB0')
    baudrate = int(ask('GSM modem baud rate', '115200'))
    pin = ask('SIM PIN, blank if not needed', '')
    own_number = ask('Own phone number in E.164 form, e.g. +8613512345678')
    sms_enabled = ask_yes('Enable SMS support', True)
    calls_enabled = ask_yes('Enable phone-call support', True)

    audio_name = ''
    audio_device = None
    if calls_enabled and ask_yes('Configure call audio device now', True):
        card = choose_card(discover_cards())
        if card:
            input_dev = card['inputs'][0]['alsa'] if card['inputs'] else ''
            output_dev = card['outputs'][0]['alsa'] if card['outputs'] else ''
            input_dev = ask('ALSA capture input', input_dev)
            output_dev = ask('ALSA playback output', output_dev or input_dev)
            audio_name = ask('AUDIO_DEVICES config key', 'gsm_usb')
            sample_rate = probe_rate(input_dev)
            audio_device = {
                'input': input_dev,
                'output': output_dev,
                'sample_rate': sample_rate,
                'channels': 1,
                'format': 's16le',
                'frame_ms': 20,
            }

    recording = None
    if calls_enabled and audio_device and ask_yes('Enable MP3 call recording',
                                                 False):
        directory = ask('Recording directory', 'recordings')
        sample_rate = audio_device['sample_rate']
        recording = {
            'enabled': True,
            'directory': directory,
            'format': 'mp3',
            'command': (
                'ffmpeg -y -f alsa -ac 1 '
                f'-ar {sample_rate} -i {{CALL_AUDIO_INPUT}} '
                '-codec:a libmp3lame -b:a 32k {CALL_RECORDING_FILE}'
            ),
            'env': {},
        }

    device_config = {
        'baudrate': baudrate,
        'own_number': own_number,
        'sms': {'enabled': sms_enabled},
        'calls': {'enabled': calls_enabled},
    }
    if pin:
        device_config['pin'] = pin
    if calls_enabled and audio_name:
        device_config['calls']['audio_device'] = audio_name
    if recording:
        device_config['calls']['recording'] = recording

    config = {
        'DEFAULT_MOBILE_REGION': region,
        'SQLITE3_FILE': sqlite_file,
    }
    if audio_name and audio_device:
        config['AUDIO_DEVICES'] = {audio_name: audio_device}
    config['DEVICES'] = {port: device_config}

    yaml = YAML()
    yaml.default_flow_style = False
    with Path('config.yaml').open('w') as f:
        yaml.dump(config, f)
    print()
    print('Wrote config.yaml')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        sys.exit(130)
PY
}

info "Checking Python version..."
if [[ ! -x "$(command -v python3)" ]]; then
    error "  Python3 does not exist, please install it manually"
fi

PY_VERSION=3.10
if [[ $( (python3 --version | awk -F' ' '{print $2}' | awk -F'.' '{print $2}')) -lt 10 ]]; then
    error "  Version of Python3 is too low (${PY_VERSION} required)"
fi

info "Checking Virtualenv..."
if [[ ! -x "$(command -v virtualenv)" ]]; then
    error "  Virtualenv does not exist,  please install it manually"
fi

VENV_DIR=venv
info "Checking Virtual environment..."
if [[ -d "${VENV_DIR}" ]]; then
    info "  Virtual environment already exists in '${VENV_DIR}'; skipping initialisation"
else
    info "  Setting up virtual environment in '${VENV_DIR}'..."
    virtualenv -ppython3 "${VENV_DIR}"
    venv_ret=$?
    if [[ ${venv_ret} -ne 0 ]]; then
        rm -fr "${VENV_DIR}"
        error "'virtualenv' exited with status ${venv_ret}"
    fi
fi

info "Installing requirements..."
source ${VENV_DIR}/bin/activate && pip install -r requirements.txt

if [[ -f "config.yaml" && "${RECONFIGURE}" -ne 1 ]]; then
  info "config.yaml already exists; leaving it unchanged"
elif [[ ! -t 0 || "${NO_CONFIG_WIZARD}" -eq 1 ]]; then
  info "Generating config.yaml from template"
  cp config.yaml.template config.yaml
  chmod 600 config.yaml
else
  info "Generating config.yaml interactively"
  generate_config_interactively || error "Interactive configuration failed"
  chmod 600 config.yaml
fi

info "Setup finished!"
