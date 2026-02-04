#!/bin/sh
set -e
set -x

echo "=== DEBUG: START.SH BEGIN ==="
echo "=== PWD: $(pwd) ==="
echo "=== PYTHON VERSION: $(python --version) ==="
echo "=== PYTHON PATH: $(which python) ==="

echo "=== RUNNING ALEMBIC ==="
alembic upgrade head 2>&1

echo "=== ALEMBIC DONE, STARTING MAIN.PY ==="
exec python -u main.py 2>&1
