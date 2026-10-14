#!/bin/sh

. frontend/venv/bin/activate

exec python -m frontend.src -- "${@}"
