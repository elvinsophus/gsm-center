#!/usr/bin/env bash

cd "$(dirname "$0")" || exit 1

function error() {
    echo -e "\e[01;31m$1\e[0m"
    exit 1
}

if [[ -z "$1" ]]; then
    port=25601
else
    port="$1"
fi

if [[ -z "$2" ]]; then
    venv="venv"
else
    venv="$2"
fi

source "${venv}/bin/activate" && exec gunicorn \
    --bind "127.0.0.1:${port}" \
    --workers 1 \
    --worker-class gthread \
    --threads "${GSM_CENTER_API_THREADS:-8}" \
    --timeout 0 \
    run_api:app
