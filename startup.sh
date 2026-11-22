#!/usr/bin/env bash
# App Service startup.
#
# Two layouts occur on this app, and the service must start from the one that
# actually holds the package:
#   * compressed — Oryx leaves `output.tar.zst` + `oryx-manifest.toml` in
#     /home/site/wwwroot and runs the container from an extracted copy under
#     /tmp, invoking this script with that directory as the working directory;
#   * decompressed — the build output was extracted into /home/site/wwwroot, so
#     `sentinel/`, `antenv/` and this script sit together.
# Running from the wrong one serves the previous deployment's code.
set -euo pipefail

# Oryx exports the extracted build's site-packages; its app path is the prefix
# above `antenv/lib/python3.x/site-packages`. Prefer that over the working
# directory and wwwroot, which can still hold the previous deployment's tree.
find_app_root() {
  local candidate
  if [ -n "${PYTHONPATH:-}" ]; then
    candidate="$(printf '%s' "${PYTHONPATH%%:*}" \
      | sed -E 's#/antenv/lib/python3[^/]*/site-packages$##')"
    if [ -n "$candidate" ] && [ -d "$candidate/sentinel" ]; then
      printf '%s' "$candidate"
      return 0
    fi
  fi
  if [ -d "$(pwd)/sentinel" ]; then
    printf '%s' "$(pwd)"
    return 0
  fi
  printf '%s' /home/site/wwwroot
}

APP_ROOT="$(find_app_root)"
cd "$APP_ROOT"

DEBUG="$APP_ROOT/startup-debug.log"

{
  echo "started $(date -u +%FT%TZ)"
  echo "app root: $APP_ROOT"
  ls -d /opt/python/* 2>/dev/null || true
  ls -d /usr/local/lib/python3.15* 2>/dev/null || true
  command -v python3.15 || true
} > "$DEBUG" 2>&1 || true

# Oryx exports PYTHONPATH for the extracted environment. Fall back to the
# virtualenv prefixes only when it did not, or when the package sits next to an
# extracted antenv.
SITE_PACKAGES=""
for candidate in "$APP_ROOT/antenv/lib/python3.15/site-packages" \
                 /home/site/wwwroot/antenv/lib/python3.15/site-packages; do
  if [ -d "$candidate" ]; then
    SITE_PACKAGES="$candidate"
    break
  fi
done

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
  if [ -n "$SITE_PACKAGES" ]; then
    export PYTHONPATH="$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
  fi
  echo "runtime python: $PY (prefix $PREFIX)" >> "$DEBUG"
elif [ -d "$APP_ROOT/antenv/bin" ]; then
  export PATH="$APP_ROOT/antenv/bin:$PATH"
  PY=python
  echo "falling back to venv python" >> "$DEBUG"
else
  PY=python3
fi
echo "site-packages: ${SITE_PACKAGES:-inherited PYTHONPATH}" >> "$DEBUG"

"$PY" -m sentinel.store.seed >> "$DEBUG" 2>&1
exec "$PY" -m uvicorn sentinel.api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
