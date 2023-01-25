#!/usr/bin/env bash

cd "$(dirname "$0")" || exit 1

function info() {
    echo -e "\e[01;34m$1\e[0m"
}
function error() {
    echo -e "\e[01;31m$1\e[0m"
    exit 1
}

info "Checking Python version..."
if [[ ! -x "$(command -v python3)" ]]; then
    error "  Python3 does exist, please install it manually"
fi

PY_VERSION=3.9
if [[ $( (python3 --version | awk -F' ' '{print $2}' | awk -F'.' '{print $2}')) -lt 9 ]]; then
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

info "Generating config.yaml file; please fill in required configurations"
cp config.yaml.template config.yaml
chmod 600 config.yaml

info "Setup finished!"
