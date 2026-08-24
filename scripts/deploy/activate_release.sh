#!/usr/bin/env bash
#
# Activate an uploaded ALAMATIN release on the production host.
#
# Streamed to the node over stdin by .github/workflows/deploy.yml and run as
# `bash -s -- <root> <release> <restart-command>`. Arguments are used instead of
# an inlined heredoc so the workflow never has to escape shell metacharacters,
# and so this logic stays reviewable in version control.
#
# Usage: bash activate_release.sh ROOT RELEASE [RESTART_COMMAND] [PYTHON_BIN]

set -euo pipefail

ROOT="${1:?deploy root is required}"
RELEASE="${2:?release name is required}"
RESTART_COMMAND="${3:-}"
# Use an explicit interpreter because the application requires Python 3.10+
# and a host's default `python3` may be older.
PYTHON_BIN="${4:-python3.11}"

RELEASE_DIR="$ROOT/releases/$RELEASE"
SHARED_VENV="$ROOT/shared/venv"
KEEP_RELEASES=5

[ -d "$RELEASE_DIR" ] || {
  echo "error: release directory not found: $RELEASE_DIR" >&2
  exit 1
}
cd "$RELEASE_DIR"

# Fail here, with the reason, rather than letting the service crash on import
# after a deploy that reported success.
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "error: interpreter '$PYTHON_BIN' not found on this node." >&2
  echo "       Install Python 3.11+ on the host or set the" >&2
  echo "       DEWACLOUD_PYTHON repository variable to an interpreter that exists." >&2
  exit 1
fi
if ! "$PYTHON_BIN" - <<'PYCHECK'
import sys
from dataclasses import dataclass
try:
    @dataclass(frozen=True, slots=True)
    class _Probe:
        value: int
except TypeError:
    sys.exit(1)
PYCHECK
then
  echo "error: '$PYTHON_BIN' ($("$PYTHON_BIN" -V 2>&1)) does not support" >&2
  echo "       dataclass(slots=True), which this application requires." >&2
  echo "       Python 3.10 or newer is needed." >&2
  exit 1
fi
echo "Using interpreter: $PYTHON_BIN ($("$PYTHON_BIN" -V 2>&1))"

# A virtualenv shared across releases keeps deploys fast. The lock file is
# still applied on every deploy, so a dependency change takes effect.
#
# An existing virtualenv is also checked, not just reused: one built earlier
# from a different interpreter would otherwise survive every later deploy and
# keep breaking the application silently.
if [ -d "$SHARED_VENV" ]; then
  want="$("$PYTHON_BIN" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
  have="$("$SHARED_VENV/bin/python" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo none)"
  if [ "$want" != "$have" ]; then
    echo "Rebuilding shared virtualenv: found Python $have, need $want"
    rm -rf "$SHARED_VENV"
  fi
fi
if [ ! -d "$SHARED_VENV" ]; then
  echo "Creating shared virtualenv..."
  "$PYTHON_BIN" -m venv "$SHARED_VENV"
fi
"$SHARED_VENV/bin/python" -m pip install --upgrade pip >/dev/null

# Anything that is not blank and not a comment counts as a real requirement.
if grep -qE '^[[:space:]]*[^[:space:]#]' requirements.lock 2>/dev/null; then
  echo "Installing locked dependencies..."
  # --require-hashes is deliberate: the repository policy requires exact,
  # hash-verified dependencies. If this fails, the lock file is missing hashes
  # and that must be fixed rather than worked around here.
  "$SHARED_VENV/bin/python" -m pip install --require-hashes -r requirements.lock
else
  echo "requirements.lock declares no dependencies; skipping install."
fi

# Boot check before activation. The application is imported exactly as the
# service will import it, so a release that cannot start never becomes
# "current" and the previous one keeps serving. Without this, a missing runtime
# file surfaced only as a 502 after the swap had already happened.
echo "Verifying the release can start..."
if ! PYTHONPATH="$RELEASE_DIR/src" "$SHARED_VENV/bin/python" -c "import alamatin.service" 2>&1; then
  echo "error: the release failed to import alamatin.service; not activating it." >&2
  echo "       The previous release is untouched and still serving." >&2
  exit 1
fi

# Atomic swap: create the new link beside the live one and rename over it, so
# no request ever observes a missing or half-written "current".
echo "Activating $RELEASE..."
ln -sfn "$RELEASE_DIR" "$ROOT/current.new"
if ! mv -T "$ROOT/current.new" "$ROOT/current" 2>/dev/null; then
  # mv -T is GNU-specific. The fallback is not atomic, so it is only used when
  # the platform leaves no better option.
  echo "warning: 'mv -T' unavailable; falling back to a non-atomic swap" >&2
  # Refuse to delete a real directory here. If "current" is not a symlink then
  # something other than this script created it, and "rm -rf" would destroy a
  # release rather than replace a pointer.
  if [ -e "$ROOT/current" ] && [ ! -L "$ROOT/current" ]; then
    # Report before cleaning up, so a failed cleanup cannot swallow the reason
    # this deploy aborted.
    echo "error: $ROOT/current exists and is not a symlink; refusing to remove it." >&2
    echo "       Inspect the node and move it aside manually before deploying." >&2
    rm -f "$ROOT/current.new" || true
    exit 1
  fi
  rm -f "$ROOT/current"
  mv "$ROOT/current.new" "$ROOT/current"
fi

if [ -n "$RESTART_COMMAND" ]; then
  echo "Restarting service..."
  # stdin is closed for the restart command on purpose. This script is streamed
  # to the node on stdin, so a command that reads stdin -- an interpreter, or
  # anything prompting for confirmation -- would consume the rest of this file
  # and the remainder would never run.
  # shellcheck disable=SC2086
  eval "$RESTART_COMMAND" </dev/null
else
  echo "warning: no restart command configured; the new release is on disk but" >&2
  echo "         the running service was not restarted." >&2
fi

# Keep a bounded number of releases so a rollback target always survives.
cd "$ROOT/releases"
# shellcheck disable=SC2012
ls -1dt */ 2>/dev/null | tail -n "+$((KEEP_RELEASES + 1))" | while read -r old; do
  echo "Pruning old release: $old"
  rm -rf "$old"
done

echo "Release $RELEASE is active."
