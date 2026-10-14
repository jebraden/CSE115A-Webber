#!/bin/sh

set -e

if [ ${#} -eq 0 ]; then
    echo "usage: run-tests.sh [MODULES...]"
    echo "Modules are probably \"frontend\" and \"backend\"."
    exit 1
fi

for module; do
    if ! [ -f "${module}/venv/bin/activate" ]; then
        echo "No such module: ${module}"
        exit 1
    fi

    . "${module}/venv/bin/activate"
    pytest "${module}/tests"
    deactivate
done
