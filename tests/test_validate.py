#!/usr/bin/env python3
"""The validator's own tests: a good setup passes, and each way of breaking
one fails with its message. Builds the setups in a temp folder and runs
scripts/check.sh on them (so through axiom's migration too, where Qt is).

    tests/test_validate.py [--axiom DIR]
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from setups import Axiom  # noqa: E402

THEME = {
    "name": "Fixture",
    "author": "someone",
    "variant": "dark",
    "paired": "",
    "colors": {f"base0{c}": "#123456" for c in "0123456789ABCDEF"},
    "semantic": {"accent": "base0D", "background": "#000000"},
}


def good(axiom):
    return {
        "setup.json": {
            "title": "Fixture",
            "author": "someone",
            "description": "A setup the validator must accept",
            "tags": ["dark", "minimal"],
            "tested": ["hyprland"],
            "fonts": ["Inter"],
        },
        "config.json": {
            "_example": {"title": "Fixture", "description": "A setup the validator must accept"},
            "version": axiom.version,
            "Appearance": {"theme": "dracula", "font": {"family": "Inter", "size": 14}, "shape": {"radius": 12}},
        },
        "screenshot.png": (1920, 1080),
    }


def with_config(change):
    def mutate(files):
        change(files["config.json"])
    return mutate


def with_manifest(change):
    def mutate(files):
        change(files["setup.json"])
    return mutate


def bundled_theme(files, theme=None):
    files["config.json"]["Appearance"]["theme"] = "community/{id}"
    files["theme.json"] = theme or dict(THEME)


# name: (mutation, expected substring in the output, or None for a pass)
CASES = {
    "good": (lambda f: None, None),
    "good-bundled-theme": (bundled_theme, None),
    "good-wallpaper": (lambda f: (f.__setitem__("wallpaper.jpg", (2560, 1440)), f["setup.json"].__setitem__("wallpaper", {"license": "CC0-1.0", "source": "own"})), None),
    "personal-apps": (with_config(lambda c: c.__setitem__("Apps", {"terminal": "kitty"})), "personal"),
    "machine-monitor": (with_config(lambda c: c.__setitem__("Bars", [{"id": "b", "monitor": "DP-1"}])), "belongs to the PC"),
    "takeover": (with_config(lambda c: c.__setitem__("Compositor", {"mode": "managed"})), "takes something over"),
    "newer-version": (with_config(lambda c: c.__setitem__("version", 9999)), "newer than axiom"),
    "no-version": (with_config(lambda c: c.pop("version")), "no `version`"),
    "header-mismatch": (with_config(lambda c: c.__setitem__("_example", {"title": "x", "description": "y"})), "`_example` must match"),
    "generated-theme": (with_config(lambda c: c["Appearance"].__setitem__("theme", "generated/wall")), "generated from a wallpaper"),
    "unknown-theme": (with_config(lambda c: c["Appearance"].__setitem__("theme", "my-own")), "isn't a theme axiom ships"),
    "theme-wrong-name": (lambda f: (bundled_theme(f), f["config.json"]["Appearance"].__setitem__("theme", "community/other")), "a bundled theme is named"),
    "theme-unused": (lambda f: f.__setitem__("theme.json", dict(THEME)), "Appearance.theme isn't"),
    "theme-bad-colour": (lambda f: bundled_theme(f, {**THEME, "colors": {**THEME["colors"], "base08": "red"}}), "colors.base08"),
    "theme-extra-key": (lambda f: bundled_theme(f, {**THEME, "script": "x"}), "unknown key 'script'"),
    "font-unlisted": (with_manifest(lambda m: m.__setitem__("fonts", [])), "list it in `fonts`"),
    "bad-tag": (with_manifest(lambda m: m.__setitem__("tags", ["cool"])), "tags/0"),
    "bad-author": (with_manifest(lambda m: m.__setitem__("author", "not a handle")), "author"),
    "no-screenshot": (lambda f: f.pop("screenshot.png"), "exactly one screenshot"),
    "small-screenshot": (lambda f: f.__setitem__("screenshot.png", (800, 450)), "px wide"),
    "tall-screenshot": (lambda f: f.__setitem__("screenshot.png", (1920, 1920)), "crop to a whole screen"),
    "wallpaper-no-license": (lambda f: f.__setitem__("wallpaper.jpg", (1920, 1080)), "needs `wallpaper.license`"),
    "license-no-wallpaper": (with_manifest(lambda m: m.__setitem__("wallpaper", {"license": "CC0-1.0", "source": "own"})), "no wallpaper file"),
    "stray-file": (lambda f: f.__setitem__("run.sh", "echo hi"), "unexpected file 'run.sh'"),
    "Bad_Id": (lambda f: None, "folder name"),
}


def write_setup(folder, files):
    folder.mkdir(parents=True)
    for name, value in files.items():
        path = folder / name
        if isinstance(value, tuple):
            Image.new("RGB", value, (40, 44, 52)).save(path)
        elif isinstance(value, dict):
            text = json.dumps(value).replace("{id}", folder.name)
            path.write_text(text)
        else:
            path.write_text(value)


def main():
    axiom_arg = sys.argv[sys.argv.index("--axiom") + 1] if "--axiom" in sys.argv else None
    axiom = Axiom.locate(axiom_arg)
    tmp = Path(tempfile.mkdtemp())
    try:
        for name, (mutate, _) in CASES.items():
            files = good(axiom)
            mutate(files)
            write_setup(tmp / name, files)
        env = {**os.environ, "GITHUB_ACTIONS": "", "GITHUB_STEP_SUMMARY": ""}
        failures = 0
        for name, (_, expected) in CASES.items():
            run = subprocess.run(
                [str(ROOT / "scripts" / "check.sh"), "--axiom", str(axiom.path), "--root", str(tmp), name],
                capture_output=True, text=True, env=env,
            )
            output = run.stdout + run.stderr
            passed = run.returncode == 0
            ok = passed if expected is None else (not passed and expected in output)
            failures += not ok
            print(f"{'ok  ' if ok else 'FAIL'} {name}")
            if not ok:
                print("     expected " + ("a pass" if expected is None else f"a failure with {expected!r}"))
                print("     " + output.strip().replace("\n", "\n     "))
        print(f"\n{len(CASES) - failures}/{len(CASES)} cases ok")
        sys.exit(1 if failures else 0)
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
