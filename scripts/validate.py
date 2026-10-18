#!/usr/bin/env python3
"""Check community setups against axiom's schema.

    scripts/validate.py [--axiom DIR] [--fix] [ID ...]
    scripts/validate.py --pr-author USER --changed ID,ID   (CI)

With no IDs, checks every setup. --fix writes config.json's `_example`
header from setup.json. Exits 1 when any setup has an error.
"""

import argparse
import os
import sys
from pathlib import Path

from setups import ROOT, SETUPS, Axiom, check_setup


def maintainers():
    """GitHub handles named in CODEOWNERS"""
    owners = ROOT / ".github" / "CODEOWNERS"
    if not owners.is_file():
        return set()
    handles = set()
    for line in owners.read_text().splitlines():
        line = line.split("#", 1)[0]
        handles.update(w[1:].lower() for w in line.split()[1:] if w.startswith("@") and "/" not in w)
    return handles


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ids", nargs="*")
    parser.add_argument("--axiom", help="axiom checkout (default: $AXIOM_DIR, then .axiom/)")
    parser.add_argument("--fix", action="store_true", help="write config.json's _example from setup.json")
    parser.add_argument("--pr-author", help="the PR's author: changed setups must be theirs")
    parser.add_argument("--changed", default="", help="comma-separated ids the PR touches")
    parser.add_argument("--root", help="folder holding the setups (default: setups/)")
    parser.add_argument("--dump-input", metavar="FILE", help="write ci/tst_Setups.qml's input and stop (scripts/check.sh)")
    parser.add_argument("--migrated", metavar="FILE", help="ci/tst_Setups.qml's output: check the configs as axiom loads them")
    args = parser.parse_args()

    axiom = Axiom.locate(args.axiom)
    base = Path(args.root) if args.root else SETUPS
    folders = [base / i for i in args.ids] if args.ids else (sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else [])
    if args.ids:
        missing = [f.name for f in folders if not f.is_dir()]
        if missing:
            sys.exit(f"No such setup: {', '.join(missing)}")

    if args.dump_input:
        import json

        setups = {}
        for f in folders:
            try:
                config = json.loads((f / "config.json").read_text())
            except (OSError, ValueError):
                continue  # reported by the real run
            if isinstance(config, dict):
                setups[f.name] = config
        Path(args.dump_input).write_text(json.dumps({"schema": axiom.schema, "setups": setups}))
        return

    loaded = {}
    if args.migrated:
        import json

        loaded = json.loads(Path(args.migrated).read_text())
    reports = [check_setup(f, axiom, fix=args.fix, loaded=loaded.get(f.name)) for f in folders]

    changed = [c for c in args.changed.split(",") if c]
    if args.pr_author and changed:
        owners = maintainers()
        if args.pr_author.lower() not in owners:
            import json

            by_id = {r.id: r for r in reports}
            for setup_id in changed:
                manifest = base / setup_id / "setup.json"
                report = by_id.get(setup_id)
                if not manifest.is_file() or report is None:
                    continue  # a removal, or caught above
                try:
                    author = json.loads(manifest.read_text()).get("author", "")
                except ValueError:
                    continue
                if str(author).lower() != args.pr_author.lower():
                    report.error(f"author is {author!r} but this PR is from {args.pr_author!r}: only a setup's author or a maintainer changes it")

    github = os.environ.get("GITHUB_ACTIONS") == "true"
    summary = []
    failed = 0
    for r in reports:
        rel = (base / r.id).relative_to(ROOT) if (base / r.id).is_relative_to(ROOT) else base / r.id
        status = "ok" if r.ok else "FAILED"
        failed += not r.ok
        print(f"{r.id}: {status}" + (f" ({len(r.warnings)} warnings)" if r.warnings else ""))
        summary.append(f"### {'✅' if r.ok else '❌'} `{r.id}`")
        for kind, items in (("error", r.errors), ("warning", r.warnings)):
            for file, message in items:
                print(f"  {kind}: {file}: {message}")
                summary.append(f"- **{kind}** `{file}`: {message}")
                if github:
                    print(f"::{kind} file={rel}/{file}::{message}")
    if not args.migrated:
        print("(not migrated first: run scripts/check.sh for the full check)")
    if not reports:
        print("No setups to check.")
        summary.append("No setups to check.")

    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a") as f:
            f.write(f"## Setups checked against axiom (config version {axiom.version})\n\n" + "\n".join(summary) + "\n")
    print(f"\n{len(reports) - failed}/{len(reports)} setups ok, against axiom config version {axiom.version}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
