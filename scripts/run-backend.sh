#!/bin/sh

. backend/venv/bin/activate

exec python -m backend.src -- "${@}"
