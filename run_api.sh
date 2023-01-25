#!/usr/bin/env bash

cd "$(dirname "$0")" || exit 1

PID_FILE=uwsgi.pid

function error() {
    echo -e "\e[01;31m$1\e[0m"
    exit 1
}

function on_exit {
    if [[ -f ${PID_FILE} ]]; then
        uwsgi --stop ${PID_FILE}
        wait "$(cat ${PID_FILE})"
        rm ${PID_FILE}
    fi
    exit 0
}

trap on_exit EXIT

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

source "${venv}/bin/activate" && uwsgi \
    --protocol http \
    --socket localhost:"${port}" \
    --venv "${venv}" \
    --pidfile ${PID_FILE} \
    --wsgi run_api:app
