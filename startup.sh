#!/usr/bin/env bash
# App Service startup.
#
# Oryx creates the virtualenv against its temporary build path; when that output
# is unpacked at runtime the venv's base prefix is gone. Use the runtime Python
# and point it at the extracted site-packages instead, then seed and serve.
set -euo pipefail

cd /home/site/wwwroot
DEBUG=/home/site/wwwroot/startup-debug.log
SITE_PACKAGES=/home/site/wwwroot/antenv/lib/python3.15/site-packages

{
  echo "started $(date -u +%FT%TZ)"
  ls -d /opt/python/* 2>/dev/null || true
  ls -d /usr/local/lib/python3.15* 2>/dev/null || true
  command -v python3.15 || true
} > "$DEBUG" 2>&1 || true

PY=""
for candidate in /opt/python/*/bin/python3.15 /opt/python/*/bin/python3 \
                 /usr/local/bin/python3.15 /usr/bin/python3.15; do
  if [ -x "$candidate" ]; then
    PY="$candidate"
    break
  fi
done

if [ -n "$PY" ]; then
  PREFIX="$(dirname "$(dirname "$PY")")"
  export LD_LIBRARY_PATH="$PREFIX/lib:${LD_LIBRARY_PATH:-}"
  export PYTHONPATH="$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
  echo "runtime python: $PY (prefix $PREFIX)" >> "$DEBUG"
else
  export PATH="/home/site/wwwroot/antenv/bin:$PATH"
  PY=python
  echo "falling back to venv python" >> "$DEBUG"
fi

"$PY" -m sentinel.store.seed >> "$DEBUG" 2>&1
exec "$PY" -m uvicorn sentinel.api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
