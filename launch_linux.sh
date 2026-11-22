#!/usr/bin/env bash
set -eu
cd -- "$(dirname -- "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'Install Python 3.11 or 3.12, then run this launcher again.'
  exit 1
fi
python3 -c 'import sys; assert (3,10) <= sys.version_info[:2] < (3,14), "Use Python 3.10–3.13; Python 3.11 or 3.12 is recommended."'
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv || { printf '%s\n' 'Could not create .venv. Your system may need its python3-venv package.'; exit 1; }
fi
py=.venv/bin/python
if ! "$py" -c 'import numpy; import PySide6.QtWidgets' >/dev/null 2>&1; then
  "$py" -m pip install --disable-pip-version-check -r requirements.txt
fi
if [ ! -f .venv/.numba_attempted ]; then
  if ! "$py" -c 'import numba' >/dev/null 2>&1; then
    printf '%s\n' 'Trying the optional Numba accelerator. If unavailable, NumPy will be used.'
    "$py" -m pip install --disable-pip-version-check numba || printf '%s\n' 'Optional accelerator unavailable; continuing with NumPy.'
  fi
  : > .venv/.numba_attempted
fi
exec "$py" main.py "$@"
