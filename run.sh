#!/bin/sh
set -e
echo "!!! [run.sh] ALEMBIC START !!!"
alembic upgrade head
echo "!!! [run.sh] ALEMBIC DONE, STARTING PYTHON !!!"
exec python -u main.py
