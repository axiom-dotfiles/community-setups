#!/usr/bin/env bash
# Check setups the way CI does: load each through axiom's own migration
# (qmltestrunner on a checkout's pure QML), then scripts/validate.py.
#
#   scripts/check.sh [--axiom DIR] [validate.py args…] [ID…]
#
# The axiom checkout is --axiom, else $AXIOM_DIR, else .axiom/ (CI clones
# axiom's main there). Without Qt 6's qmltestrunner the load step is
# skipped with a warning (CI always has it).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
axiom="${AXIOM_DIR:-$root/.axiom}"
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --axiom) axiom="$2"; shift 2 ;;
    --axiom=*) axiom="${1#--axiom=}"; shift ;;
    *) args+=("$1"); shift ;;
  esac
done
axiom="$(cd "$axiom" && pwd)"

qt_bin="${QT_BIN:-}"
if [ -z "$qt_bin" ] && command -v qmake6 >/dev/null 2>&1; then
  qt_bin="$(qmake6 -query QT_INSTALL_BINS 2>/dev/null)"
fi
qt_bin="${qt_bin:-/usr/lib/qt6/bin}"

work="$root/ci/.work"
rm -rf "$work"
mkdir -p "$work"
migrated=()
if [ -x "$qt_bin/qmltestrunner" ]; then
  tree="$(mktemp -d)"
  trap 'rm -rf "$tree"' EXIT
  python3 "$axiom/scripts/qml_modules.py" --pure "$tree" >/dev/null
  python3 "$root/scripts/validate.py" --axiom "$axiom" --dump-input "$work/input.json" "${args[@]}"
  QML_XHR_ALLOW_FILE_READ=1 QML_XHR_ALLOW_FILE_WRITE=1 QT_QPA_PLATFORM=offscreen \
    "$qt_bin/qmltestrunner" -import "$tree" -input "$root/ci/tst_Setups.qml" -silent
  migrated=(--migrated "$work/migrated.json")
else
  echo "warning: no Qt 6 qmltestrunner in $qt_bin: setups aren't migrated first (set QT_BIN)" >&2
fi
python3 "$root/scripts/validate.py" --axiom "$axiom" "${migrated[@]}" "${args[@]}"
