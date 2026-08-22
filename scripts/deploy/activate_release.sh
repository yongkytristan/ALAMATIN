#!/usr/bin/env bash
#
# Activate an uploaded ALAMATIN release on the Dewacloud node.
#
# Streamed to the node over stdin by .github/workflows/deploy.yml and run as
# `bash -s -- <root> <release> <restart-command>`. Arguments are used instead of
# an inlined heredoc so the workflow never has to escape shell metacharacters,
# and so this logic stays reviewable in version control.
#
# Usage: bash activate_release.sh ROOT RELEASE [RESTART_COMMAND]

set -euo pipefail

ROOT="${1:?deploy root is required}"
RELEASE="${2:?release name is required}"
RESTART_COMMAND="${3:-}"

RELEASE_DIR="$ROOT/releases/$RELEASE"
SHARED_VENV="$ROOT/shared/venv"
KEEP_RELEASES=5

[ -d "$RELEASE_DIR" ] || {
  echo "error: release directory not found: $RELEASE_DIR" >&2
  exit 1
}
cd "$RELEASE_DIR"

# A virtualenv shared across releases keeps deploys fast. The lock file is
# still applied on every deploy, so a dependency change takes effect.
if [ ! -d "$SHARED_VENV" ]; then
  echo "Creating shared virtualenv..."
  python3 -m venv "$SHARED_VENV"
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
  # shellcheck disable=SC2086
  eval "$RESTART_COMMAND"
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
