#!/usr/bin/env bash
# Check setups the way CI does: load each through axiom's own migration and
# ConfigExamples.pick (qmltestrunner on a checkout's pure QML), then
# scripts/validate.py.
#
#   scripts/check.sh [--axiom DIR] [validate.py args…] [ID…]
#   scripts/check.sh [--axiom DIR] --upgrade ID…
#
# --upgrade rewrites each setup's config.json as an Export from that axiom
# would hold it (migrated, look only, defaults left out), then checks it:
# how a maintainer brings setups up to a new config schema.
#
# The axiom checkout is --axiom, else $AXIOM_DIR, else .axiom/ (CI clones
# axiom's main there). Needs Qt 6's qmltestrunner (QT_BIN, else qmake6's,
# else /usr/lib/qt6/bin): what a setup may hold is decided by axiom's QML.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
axiom="${AXIOM_DIR:-$root/.axiom}"
args=()
upgrade=false
while [ $# -gt 0 ]; do
  case "$1" in
    --axiom) axiom="$2"; shift 2 ;;
    --axiom=*) axiom="${1#--axiom=}"; shift ;;
    --upgrade) upgrade=true; shift ;;
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
if [ ! -x "$qt_bin/qmltestrunner" ]; then
  echo "error: no Qt 6 qmltestrunner in $qt_bin (set QT_BIN): setups are loaded by axiom's own QML" >&2
  exit 2
fi
tree="$(mktemp -d)"
trap 'rm -rf "$tree"' EXIT
python3 "$axiom/scripts/qml_modules.py" --pure "$tree" >/dev/null

# Each config through axiom's QML: .work/input.json in, .work/migrated.json out
load() {
  python3 "$root/scripts/validate.py" --axiom "$axiom" --dump-input "$work/input.json" "${args[@]}"
  QML_XHR_ALLOW_FILE_READ=1 QML_XHR_ALLOW_FILE_WRITE=1 QT_QPA_PLATFORM=offscreen \
    "$qt_bin/qmltestrunner" -import "$tree" -input "$root/ci/tst_Setups.qml" -silent
}

load
if $upgrade; then
  python3 "$root/scripts/validate.py" --axiom "$axiom" --migrated "$work/migrated.json" --upgrade "${args[@]}"
  load
fi
python3 "$root/scripts/validate.py" --axiom "$axiom" --migrated "$work/migrated.json" "${args[@]}"
