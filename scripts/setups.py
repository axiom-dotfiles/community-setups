"""Shared checks for community setups.

The scope rules are axiom's own: a setup's config is walked along axiom's
config.schema.json the way ConfigExamples.pick walks it (components/methods/
ConfigExamples.qml), so what this repo accepts is exactly the `look` part
axiom would apply from it. Nothing here hard-codes a config section.
"""

import hashlib
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETUPS = ROOT / "setups"
MANIFEST_SCHEMA = ROOT / "schema" / "setup.schema.json"

ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
BASE_RE = re.compile(r"^base0[0-9A-F]$")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp")

# Limits, in bytes and pixels
SCREENSHOT_MAX = 3 * 1024 * 1024
EXTRA_MAX = 2 * 1024 * 1024
WALLPAPER_MAX = 10 * 1024 * 1024
THEME_MAX = 16 * 1024
CONFIG_MAX = 256 * 1024
SCREENSHOT_MIN_WIDTH = 1280
SCREENSHOT_MAX_WIDTH = 7680
ASPECT_MIN, ASPECT_MAX = 1.3, 3.6  # 4:3 up to 32:9
EXTRA_COUNT = 3


class Report:
    """Errors fail a setup; warnings are shown but pass."""

    def __init__(self, setup_id):
        self.id = setup_id
        self.errors = []
        self.warnings = []

    def error(self, message, file="setup.json"):
        self.errors.append((file, message))

    def warn(self, message, file="setup.json"):
        self.warnings.append((file, message))

    @property
    def ok(self):
        return not self.errors


# ---------------------------------------------------------------- axiom ---


class Axiom:
    """What a checkout of axiom says: its schema, version and themes."""

    def __init__(self, path):
        self.path = Path(path)
        schema_file = self.path / "config" / "json" / "config.schema.json"
        if not schema_file.is_file():
            raise SystemExit(
                f"{schema_file} not found: point --axiom (or AXIOM_DIR) at a checkout of axiom"
            )
        self.schema = json.loads(schema_file.read_text())
        self.version = self.schema["properties"]["version"]["default"]
        themes = self.path / "config" / "themes"
        self.themes = sorted(p.stem for p in themes.glob("*.json"))
        self.theme_template = json.loads((themes / "template" / "theme.json").read_text())

    @staticmethod
    def locate(arg=None):
        for candidate in (arg, os.environ.get("AXIOM_DIR"), ROOT / ".axiom"):
            if candidate and Path(candidate).is_dir():
                return Axiom(candidate)
        raise SystemExit(
            "No axiom checkout: pass --axiom DIR, set AXIOM_DIR, or clone axiom into .axiom/"
        )

    def resolve(self, node):
        """A $ref's definition, with the keys beside the $ref over it (SchemaValidation._resolve)"""
        if isinstance(node, dict) and "$ref" in node:
            name = node["$ref"].replace("#/definitions/", "")
            definition = self.schema.get("definitions", {}).get(name)
            if definition is None:
                return node
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return {**definition, **extra} if extra else definition
        return node

    def node(self, value, schema, scope):
        """(schema, scope) for `value` at `schema`, oneOf discriminated by `type` (ConfigExamples._node)"""
        node = self.resolve(schema)
        if isinstance(node, dict):
            scope = node.get("x-scope", scope)
            if "oneOf" in node:
                node = self.discriminate(value, node)
        if isinstance(node, dict):
            scope = node.get("x-scope", scope)
        return node if isinstance(node, dict) else None, scope

    def discriminate(self, value, node):
        if not isinstance(value, dict):
            return None
        for option in node["oneOf"]:
            option = self.resolve(option)
            const = option.get("properties", {}).get("type", {}).get("const")
            if const is not None and const == value.get("type"):
                return option
        return None

    @staticmethod
    def child(node, key):
        if key in node.get("properties", {}):
            return node["properties"][key]
        extra = node.get("additionalProperties")
        return extra if isinstance(extra, dict) else None


def scope_problems(config, axiom):
    """Every place `config` holds something axiom wouldn't take from a shared
    file: ([(path, scope)], [(path, why)]) for errors and warnings. Errors are
    personal or machine values and takeover settings; warnings are keys or
    types the current schema doesn't know (usually an older version's)."""
    errors, warnings = [], []

    def walk(value, schema, scope, path):
        node, scope = axiom.node(value, schema, scope)
        if node is not None and node.get("x-takeover") is True:
            errors.append((path, "takeover"))
            return
        keep = scope == "look"
        if isinstance(value, list):
            if not keep:
                errors.append((path, scope))
                return
            items = node.get("items") if node else None
            for i, item in enumerate(value):
                if items is not None:
                    walk(item, items, scope, f"{path}[{i}]")
            return
        if isinstance(value, dict):
            if node is None:
                if keep:
                    warnings.append((path, f"unknown type {value.get('type')!r}"))
                else:
                    errors.append((path, scope))
                return
            for key, sub in value.items():
                child = axiom.child(node, key)
                sub_path = f"{path}.{key}" if path else key
                if child is None:
                    if sub not in ({}, []):  # an empty leftover axiom prunes
                        warnings.append((sub_path, "unknown key"))
                else:
                    walk(sub, child, scope, sub_path)
            return
        if not keep:
            errors.append((path, scope))

    root = axiom.schema
    for key, value in config.items():
        if key in ("_example", "version"):
            continue
        child = Axiom.child(root, key)
        if child is None:
            warnings.append((key, "unknown section"))
        else:
            walk(value, child, root.get("x-scope", "machine"), key)
    return errors, warnings


# ---------------------------------------------------------------- files ---


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path, report, file):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        report.error(f"not valid JSON: {e}", file)
        return None


def write_json(path, value):
    """Atomically, 2-space indented, as axiom writes its own files"""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def one_file(folder, stem):
    found = [p for p in folder.iterdir() if p.is_file() and p.stem == stem and p.suffix.lower() in IMAGE_EXTS]
    return found


def check_image(path, folder, report, max_bytes, screenshot=False):
    from PIL import Image

    name = path.relative_to(folder).as_posix()
    size = path.stat().st_size
    if size > max_bytes:
        report.error(f"{size // 1024} KB, over the {max_bytes // 1024} KB limit", name)
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            width, height = im.size
            fmt = im.format
    except Exception as e:  # Pillow raises many kinds
        report.error(f"not a readable image: {e}", name)
        return
    if fmt not in ("PNG", "JPEG", "WEBP"):
        report.error(f"{fmt} image: use PNG, JPEG or WebP", name)
    if screenshot:
        if not SCREENSHOT_MIN_WIDTH <= width <= SCREENSHOT_MAX_WIDTH:
            report.error(f"{width}px wide: screenshots are {SCREENSHOT_MIN_WIDTH}–{SCREENSHOT_MAX_WIDTH}px", name)
        if not ASPECT_MIN <= width / height <= ASPECT_MAX:
            report.error(f"{width}×{height}: crop to a whole screen, 4:3 to 32:9", name)


# ------------------------------------------------------------- checking ---


def check_manifest(manifest, report):
    import jsonschema

    schema = json.loads(MANIFEST_SCHEMA.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    for e in sorted(validator.iter_errors(manifest), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in e.path) or "(root)"
        report.error(f"{where}: {e.message}")


def check_theme(theme, setup_id, manifest, axiom, report):
    template = axiom.theme_template
    allowed = set(template)
    for key in theme:
        if key not in allowed:
            report.error(f"unknown key {key!r} (a theme has {', '.join(sorted(allowed))})", "theme.json")
    if not isinstance(theme.get("name"), str) or not theme["name"].strip():
        report.error("`name` is empty: it's what the Themes page shows", "theme.json")
    if theme.get("variant") not in ("dark", "light"):
        report.error("`variant` must be dark or light", "theme.json")
    paired = theme.get("paired", "")
    if paired and paired not in axiom.themes:
        report.error(f"`paired` {paired!r} isn't a theme axiom ships (leave it empty)", "theme.json")
    if theme.get("author") and theme["author"] != manifest.get("author"):
        report.warn("`author` differs from setup.json's", "theme.json")
    colors = theme.get("colors")
    if not isinstance(colors, dict):
        report.error("`colors` is missing", "theme.json")
        return
    for key in template["colors"]:
        if not HEX_RE.match(str(colors.get(key, ""))):
            report.error(f"colors.{key} must be #rrggbb", "theme.json")
    for key in colors:
        if key not in template["colors"]:
            report.error(f"unknown colour {key!r}", "theme.json")
    semantic = theme.get("semantic", {})
    if not isinstance(semantic, dict):
        report.error("`semantic` must be an object", "theme.json")
        return
    for key, value in semantic.items():
        if key not in template["semantic"]:
            report.error(f"unknown semantic colour {key!r}", "theme.json")
        elif not (BASE_RE.match(str(value)) or HEX_RE.match(str(value))):
            report.error(f"semantic.{key} must be a base00–base0F name or #rrggbb", "theme.json")


def check_setup(folder, axiom, fix=False, loaded=None):
    """All the checks for one setups/<id>/ folder. `loaded`: its entry from
    ci/tst_Setups.qml (the config migrated and loaded by axiom's own code);
    without it the config is checked as written, against the current schema."""
    folder = Path(folder)
    setup_id = folder.name
    report = Report(setup_id)

    if not ID_RE.match(setup_id) or len(setup_id) > 40:
        report.error(f"folder name {setup_id!r}: lowercase letters, digits and dashes, at most 40", ".")

    allowed = {"setup.json", "config.json", "theme.json", "extra"}
    for entry in folder.iterdir():
        if entry.name in allowed or (entry.is_file() and entry.stem in ("screenshot", "wallpaper") and entry.suffix.lower() in IMAGE_EXTS):
            continue
        report.error(f"unexpected file {entry.name!r}", entry.name)

    manifest_file = folder / "setup.json"
    if not manifest_file.is_file():
        report.error("missing setup.json")
        return report
    manifest = load_json(manifest_file, report, "setup.json")
    if not isinstance(manifest, dict):
        return report
    check_manifest(manifest, report)

    # Images
    shots = one_file(folder, "screenshot")
    if len(shots) != 1:
        report.error("needs exactly one screenshot.png, .jpg or .webp", ".")
    else:
        check_image(shots[0], folder, report, SCREENSHOT_MAX, screenshot=True)
    walls = one_file(folder, "wallpaper")
    if len(walls) > 1:
        report.error("at most one wallpaper file", ".")
    for wall in walls:
        check_image(wall, folder, report, WALLPAPER_MAX)
    if walls and not manifest.get("wallpaper"):
        report.error("a wallpaper needs `wallpaper.license` and `wallpaper.source` in setup.json")
    if manifest.get("wallpaper") and not walls:
        report.error("`wallpaper` is set but there's no wallpaper file")
    extra = folder / "extra"
    if extra.exists():
        images = sorted(p for p in extra.iterdir())
        if len(images) > EXTRA_COUNT:
            report.error(f"at most {EXTRA_COUNT} extra screenshots", "extra")
        for p in images:
            if p.suffix.lower() not in IMAGE_EXTS:
                report.error(f"unexpected file {p.name!r}", f"extra/{p.name}")
            else:
                check_image(p, folder, report, EXTRA_MAX)

    # Config
    config_file = folder / "config.json"
    if not config_file.is_file():
        report.error("missing config.json (Settings → Maintenance → Share → Export)", "config.json")
        return report
    if config_file.stat().st_size > CONFIG_MAX:
        report.error(f"over {CONFIG_MAX // 1024} KB: export it again, it holds only what differs from the defaults", "config.json")
    config = load_json(config_file, report, "config.json")
    if not isinstance(config, dict):
        return report
    version = config.get("version")
    if not isinstance(version, int) or version < 1:
        report.error("no `version`: export it from axiom rather than copying config.json", "config.json")
    elif version > axiom.version:
        report.error(f"version {version} is newer than axiom main ({axiom.version})", "config.json")

    checked = config
    if loaded is not None:
        if "exception" in loaded:
            report.error(f"axiom can't load it: {loaded['exception']}", "config.json")
            return report
        checked = loaded["migrated"]
        if loaded["secrets"]:
            report.error(f"holds secrets ({', '.join(loaded['secrets'])}): never share an API key; export again", "config.json")
        for message in loaded["errors"]:
            report.error(f"invalid once loaded: {message}", "config.json")
        for message in loaded["applyErrors"]:
            report.error(f"invalid once applied: {message}", "config.json")
    errors, warnings = scope_problems(checked, axiom)
    for path, scope in errors:
        if scope == "takeover":
            report.error(f"{path}: takes something over on the PC (compositor mode, locker, idle, polkit, greeter) and is never shared", "config.json")
        elif scope == "personal":
            report.error(f"{path}: personal (keybinds, apps, commands): export again with those switched off", "config.json")
        else:
            report.error(f"{path}: belongs to the PC it was made on (monitors, wallpapers, accounts, paths), never shared", "config.json")
    for path, why in warnings:
        report.warn(f"{path}: {why} in axiom {axiom.version}" + (" (after migrating)" if loaded is not None else "") + ": axiom ignores it", "config.json")

    # The header: setup.json is the source of truth
    header = {"title": manifest.get("title", ""), "description": manifest.get("description", "")}
    if config.get("_example") != header:
        if fix:
            config = {"_example": header, **{k: v for k, v in config.items() if k != "_example"}}
            write_json(config_file, config)
        else:
            report.error("`_example` must match setup.json's title and description (run scripts/validate.py --fix)", "config.json")

    # Theme
    appearance = config.get("Appearance") if isinstance(config.get("Appearance"), dict) else {}
    theme_name = appearance.get("theme")
    theme_file = folder / "theme.json"
    own = f"community/{setup_id}"
    if isinstance(theme_name, str) and theme_name.startswith("generated/"):
        report.error(f"Appearance.theme {theme_name!r} was generated from a wallpaper on your PC: copy it to theme.json and set the theme to {own!r}", "config.json")
    elif isinstance(theme_name, str) and theme_name.startswith("community/"):
        if theme_name != own:
            report.error(f"Appearance.theme {theme_name!r}: a bundled theme is named {own!r}", "config.json")
        if not theme_file.is_file():
            report.error(f"Appearance.theme is {own!r} but there's no theme.json", "config.json")
    elif theme_name is not None and theme_name not in axiom.themes:
        report.error(f"Appearance.theme {theme_name!r} isn't a theme axiom ships: bundle it as theme.json and set the theme to {own!r}", "config.json")
    if theme_file.is_file():
        if theme_name != own:
            report.error(f"theme.json is bundled but Appearance.theme isn't {own!r}", "theme.json")
        if theme_file.stat().st_size > THEME_MAX:
            report.error("too large for a theme", "theme.json")
        theme = load_json(theme_file, report, "theme.json")
        if isinstance(theme, dict):
            check_theme(theme, setup_id, manifest, axiom, report)
        else:
            report.error("must be a JSON object", "theme.json")

    # Fonts
    family = (appearance.get("font") or {}).get("family") if isinstance(appearance.get("font"), dict) else None
    if family and family not in manifest.get("fonts", []):
        report.error(f"the config uses the font {family!r}: list it in `fonts`")

    return report


def all_setups():
    if not SETUPS.is_dir():
        return []
    return sorted(p for p in SETUPS.iterdir() if p.is_dir())
