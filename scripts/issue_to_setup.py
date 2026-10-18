#!/usr/bin/env python3
"""Turn a "Submit a setup" issue into a setups/<id>/ folder.

    ISSUE_BODY=… ISSUE_AUTHOR=login scripts/issue_to_setup.py

Run by .github/workflows/submission.yml. The body is untrusted: it's only
parsed (JSON, images through Pillow), files are fetched only from GitHub's
own attachment hosts, sizes are capped, and nothing from it reaches a
shell. Prints the setup id; exits 2 with a message for the submitter when
the issue can't be turned into a folder (scripts/check.sh then reports
everything else).
"""

import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from setups import ID_RE, SETUPS, WALLPAPER_MAX, write_json

# Issue form labels (.github/ISSUE_TEMPLATE/submit-setup.yml)
FIELDS = {
    "title": "Title",
    "id": "Setup id",
    "description": "Description",
    "about": "About it",
    "tags": "Tags",
    "tested": "Tested on",
    "fonts": "Fonts",
    "config": "config.json",
    "screenshot": "Screenshot",
    "theme": "theme.json",
    "wallpaper": "Wallpaper",
    "license": "Wallpaper license",
    "source": "Wallpaper source",
}
NO_RESPONSE = "_No response_"
ATTACHMENT_HOSTS = ("github.com", "user-images.githubusercontent.com", "private-user-images.githubusercontent.com", "objects.githubusercontent.com")
DOWNLOAD_MAX = WALLPAPER_MAX + 1


class Refused(Exception):
    pass


def sections(body):
    """{label: text} from the form's `### Label` sections"""
    found = {}
    parts = re.split(r"^### (.+?)\s*$", body.replace("\r\n", "\n"), flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        text = parts[i + 1].strip()
        found[parts[i].strip()] = "" if text == NO_RESPONSE else text
    return found


def field(found, key):
    return found.get(FIELDS[key], "").strip()


def listed(text):
    """A multi-select dropdown's answer, or a comma/newline list"""
    return [w.strip() for w in re.split(r"[,\n]", text) if w.strip()]


def attachment_urls(text):
    urls = re.findall(r"""(?:\]\(|src=["'])(https://[^\s)"']+)""", text)
    urls += re.findall(r"(?<![(\"'])\bhttps://github\.com/user-attachments/\S+", text)
    seen = []
    for url in urls:
        url = url.rstrip(").,'\"")
        if url not in seen:
            seen.append(url)
    return seen


def allowed(url):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ATTACHMENT_HOSTS:
        return False
    return parsed.hostname != "github.com" or parsed.path.startswith("/user-attachments/")


def download(url, what):
    if not allowed(url):
        raise Refused(f"{what}: attach the file to the issue (drag it into the field); links elsewhere aren't fetched")
    request = urllib.request.Request(url, headers={"User-Agent": "axiom-community-setups"})
    with urllib.request.urlopen(request, timeout=30) as response:
        final = urlparse(response.geturl()).hostname
        if final not in ATTACHMENT_HOSTS and not final.endswith(".githubusercontent.com"):
            raise Refused(f"{what}: the attachment redirected somewhere unexpected")
        data = response.read(DOWNLOAD_MAX + 1)
    if len(data) > DOWNLOAD_MAX:
        raise Refused(f"{what}: too large")
    return data


def json_field(text, what, required):
    """Pasted JSON (fenced or not) or an attached .json file"""
    if not text:
        if required:
            raise Refused(f"{what} is missing")
        return None
    fenced = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.S)
    candidate = fenced.group(1) if fenced else text
    if candidate.lstrip().startswith("{"):
        source = candidate
    else:
        urls = attachment_urls(text)
        if not urls:
            raise Refused(f"{what}: paste the file's contents, or attach the file")
        source = download(urls[0], what).decode("utf-8", "replace")
    try:
        value = json.loads(source)
    except json.JSONDecodeError as e:
        raise Refused(f"{what} isn't valid JSON: {e}")
    if not isinstance(value, dict):
        raise Refused(f"{what} must be a JSON object")
    return value


def image_field(text, what, required):
    if not text:
        if required:
            raise Refused(f"{what} is missing")
        return None
    urls = attachment_urls(text)
    if not urls:
        raise Refused(f"{what}: drag the image into the field")
    data = download(urls[0], what)
    from io import BytesIO

    from PIL import Image

    try:
        with Image.open(BytesIO(data)) as im:
            fmt = im.format
    except Exception:
        raise Refused(f"{what} isn't a readable image")
    ext = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}.get(fmt)
    if not ext:
        raise Refused(f"{what} is {fmt}: use PNG, JPEG or WebP")
    return data, ext


def slug(text):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")[:40].strip("-")


def build(body, author):
    found = sections(body)
    title = field(found, "title")
    setup_id = field(found, "id") or slug(title)
    if not ID_RE.match(setup_id) or len(setup_id) > 40:
        raise Refused(f"setup id {setup_id!r}: lowercase letters, digits and dashes, at most 40")

    manifest = {
        "title": title,
        "author": author,
        "description": field(found, "description"),
        "tags": listed(field(found, "tags")),
        "tested": [t.lower() for t in listed(field(found, "tested"))],
        "fonts": listed(field(found, "fonts")),
    }
    if field(found, "about"):
        manifest["about"] = field(found, "about")

    config = json_field(field(found, "config"), "config.json", True)
    theme = json_field(field(found, "theme"), "theme.json", False)
    shot = image_field(field(found, "screenshot"), "Screenshot", True)
    wall = image_field(field(found, "wallpaper"), "Wallpaper", False)
    if wall:
        manifest["wallpaper"] = {"license": field(found, "license"), "source": field(found, "source")}

    # A bundled theme is named after the setup, whatever the export said
    if theme is not None:
        config.setdefault("Appearance", {})["theme"] = f"community/{setup_id}"
        theme.setdefault("author", author)
    config = {"_example": {"title": manifest["title"], "description": manifest["description"]}, **{k: v for k, v in config.items() if k != "_example"}}

    folder = SETUPS / setup_id
    if folder.exists():
        existing = json.loads((folder / "setup.json").read_text()).get("author", "")
        if existing.lower() != author.lower():
            raise Refused(f"{setup_id!r} is @{existing}'s setup: pick another id")
        for p in sorted(folder.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    folder.mkdir(parents=True, exist_ok=True)
    write_json(folder / "setup.json", manifest)
    write_json(folder / "config.json", config)
    if theme is not None:
        write_json(folder / "theme.json", theme)
    (folder / ("screenshot" + shot[1])).write_bytes(shot[0])
    if wall:
        (folder / ("wallpaper" + wall[1])).write_bytes(wall[0])
    return setup_id


def main():
    body = os.environ.get("ISSUE_BODY", "")
    author = os.environ.get("ISSUE_AUTHOR", "")
    if not body or not author:
        sys.exit("ISSUE_BODY and ISSUE_AUTHOR are required")
    try:
        print(build(body, author))
    except Refused as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
