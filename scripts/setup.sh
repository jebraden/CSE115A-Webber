#!/bin/sh

# This script sets up the development environmet

set -e

if [ ${#} -eq 0 ]; then
    echo "usage: setup.sh [MODULE...]"
    echo "MODULES are probably \"frontend\" and \"backend\"."
    exit 1
fi

# macOS commonly exposes Python 3 only as python3.
if command -v python3 >/dev/null 2>&1; then
    python_cmd=python3
elif command -v python >/dev/null 2>&1; then
    python_cmd=python
else
    echo "Python 3 is required. Install Python 3 and retry."
    exit 1
fi

echo "Modules: ${*}"

for module; do
    if ! [ -d "${module}" ]; then
        echo "No such module: ${module}"
        exit 1
    fi

    echo "Setting up Python venv for ${module}"
    set -x
    "${python_cmd}" -m venv "${module}/venv"
    set +x

    echo "Installing dependencies..."
    . "${module}/venv/bin/activate"
    set --
    for file in "${module}"/*requirements.txt; do
        set -- '-r' "${file}" "${@}"
    done
    set -x
    pip install "${@}"
    set +x
    deactivate
done

