#!/bin/sh

# This script sets up the development environmet

set -e

if [ ${#} -eq 0 ]; then
    echo "usage: setup.sh [MODULE...]"
    echo "MODULES are probably \"frontend\" and \"backend\"."
    exit 1
fi

echo "Modules: ${*}"

for module; do
    if ! [ -f "${module}" ]; then
        echo "No such module: ${module}"
        exit 1
    fi

    echo "Setting up Python venv for ${module}"
    set -x
    python -m venv "${module}/venv"
    set +x

    echo "Installing dependencies..."
    . "${module}/venv/bin/activate"
    set -x
    pip install -r "${module}/requirements.txt"
    set +x
    deactivate
done

