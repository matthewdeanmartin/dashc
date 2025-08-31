#!/usr/bin/env bash
# Integration test for dashc CLI
# Exercises:
#   - python -m dashc file (one-line + script output)
#   - python -m dashc module (run module; run function)
# Prints commands, outputs, and exit codes; minimal assertions.

set -euo pipefail

KEEP_INTEG_ARTIFACTS=1

# --- Helpers ---------------------------------------------------------------

log() { printf "\n\033[1m==> %s\033[0m\n" "$*"; }

run() {
  echo "+ $*"
  # shellcheck disable=SC2068
  "$@"
}

# Cleanup temp directory on exit
TMPDIR="$(mktemp -d 2>/dev/null || mktemp -d -t dashc-integ)"
TMPDIR="scripts/tmp"
mkdir --parent $TMPDIR
cleanup() {
  # leave artifacts if KEEP_INTEG_ARTIFACTS=1
  if [[ "${KEEP_INTEG_ARTIFACTS:-0}" != "1" ]]; then
    rm -rf "$TMPDIR"
  else
    echo "Keeping artifacts at: $TMPDIR"
  fi
}
trap cleanup EXIT

# On some systems `python` may be `python3`. Let users override.
PY="${PYTHON_BIN:-python}"

# Ensure we can run the module as a package (dev trees often prefer this)
DASHC_RUN="$PY -m dashc"

# --- Smoke: version/help ---------------------------------------------------
log "dashc --version"
run $PY -m dashc --version || true

# --- 1) Single file: one-line command -------------------------------------
log "Prepare single-file source"
cat > "$TMPDIR/hello_file.py" <<'PY'
import sys
print("HELLO_FILE", "args:", sys.argv[1:])
PY

log "Generate shebang-less command from single file"
ONE_LINE_CMD="$($DASHC_RUN file "$TMPDIR/hello_file.py" --one-line)"
echo "Generated shebang-less command:"
echo "$ONE_LINE_CMD"

log "Execute the shebang-less command (passes args)"
set +e
bash -c "$ONE_LINE_CMD world 123"
RC1=$?
set -e
echo "Exit code: $RC1"

# --- 2) Single file: script output ----------------------------------------
log "Generate script file from single file"
run $DASHC_RUN file "$TMPDIR/hello_file.py" -o "$TMPDIR/hello_file.sh"
chmod +x "$TMPDIR/hello_file.sh"

log "Run generated script"
set +e
"$TMPDIR/hello_file.sh" foo bar
RC2=$?
set -e
echo "Exit code: $RC2"

# --- 3) Module packaging: run module (__main__) ----------------------------
log "Prepare package with __main__.py"
PKGDIR="$TMPDIR/mypkg"
mkdir -p "$PKGDIR"
cat > "$PKGDIR/__init__.py" <<'PY'
# marker
PY
cat > "$PKGDIR/__main__.py" <<'PY'
import sys
print("HELLO_PKG_MAIN", "args:", sys.argv[1:])
PY

log "Generate module runner (runs python -m mypkg)"
run $DASHC_RUN module "$PKGDIR" -o "$TMPDIR/run_pkg_main.sh"
chmod +x "$TMPDIR/run_pkg_main.sh"

log "Execute module runner"
set +e
"$TMPDIR/run_pkg_main.sh" zig zag
RC3=$?
set -e
echo "Exit code: $RC3"

# --- 4) Module packaging: import function (pkg.cli:main) -------------------
log "Add CLI function entrypoint"
cat > "$PKGDIR/cli.py" <<'PY'
def main():
    print("HELLO_PKG_FUNC")
    return 0
PY

log "Generate function-entrypoint runner"
run $DASHC_RUN module "$PKGDIR" --entrypoint "mypkg.cli:main" -o "$TMPDIR/run_pkg_func.sh"
chmod +x "$TMPDIR/run_pkg_func.sh"

log "Execute function-entrypoint runner"
set +e
"$TMPDIR/run_pkg_func.sh"
RC4=$?
set -e
echo "Exit code: $RC4"

# --- 5) Optional: plain-text embedding path -------------------------------
log "Generate plain-text single file script"
run $DASHC_RUN file "$TMPDIR/hello_file.py" --plain-text -o "$TMPDIR/hello_plain.sh"
chmod +x "$TMPDIR/hello_plain.sh"

log "Execute plain-text script"
set +e
"$TMPDIR/hello_plain.sh" alpha
RC5=$?
set -e
echo "Exit code: $RC5"

# --- Summary ---------------------------------------------------------------
log "Summary of exit codes (non-zero would indicate an execution problem)"
printf "shebang-less: %d | file-script: %d | module-main: %d | module-func: %d | plain-text: %d\n" \
  "$RC1" "$RC2" "$RC3" "$RC4" "$RC5"

# Minimal check: all executions should have succeeded (0)
if [[ "$RC1" -ne 0 || "$RC2" -ne 0 || "$RC3" -ne 0 || "$RC4" -ne 0 || "$RC5" -ne 0 ]]; then
  echo "One or more runs returned a non-zero exit code." >&2
  exit 1
fi

echo "OK"
