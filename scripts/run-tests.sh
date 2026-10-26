#!/bin/sh

set -e

if [ ${#} -eq 0 ]; then
    echo "usage: run-tests.sh [--headless] [MODULES...]"
    echo "Modules are probably \"frontend\" and \"backend\"."
    exit 1
fi

if [ "${1}" = "--headless" ]; then
    export QT_QPA_PLATFORM=offscreen
    shift
fi

out=0

for module; do
    if ! [ -f "${module}/venv/bin/activate" ]; then
        echo "No such module: ${module}"
        echo ' => Have you run `make setup`?'
        exit 1
    fi

    . "${module}/venv/bin/activate"
    if ! ls -A1q "${module}/tests/" | grep -qE 'test.+py'; then
        echo "No tests found, skipping ${module}..."
        continue
    fi
    if ! pytest "${module}/tests"; then
        out=1
    fi
    deactivate
done

exit ${out}
