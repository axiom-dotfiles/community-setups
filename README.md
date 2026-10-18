<div align="center">

# axiom community setups

**Desktops people built with [axiom](https://github.com/axiom-dotfiles/axiom), ready to apply in one click.**

[Browse](#gallery) · [Apply one](#apply-one) · [Submit yours](#submit-yours) · [What a setup can hold](#what-a-setup-can-hold)

</div>

A setup is the look and layout of an axiom desktop: its bars and their style, overlay pages, edge menus, docks, OSDs, popouts, the lock screen's layout, the theme, font, shape and motion. Each one here was built inside axiom with its own editors and exported with **Share → Export**, so none of them was written by hand.

## Gallery

**[Browse the gallery →](../../tree/catalog#readme)** (rebuilt after every merge, newest first).

## Apply one

- **In axiom** (coming soon): Settings → Maintenance → **Community setups** lets you search, preview and apply one.
- **By hand**: download a setup's `config.json`, then go to Settings → Maintenance → Share → **Import…**. If it has a `theme.json`, copy that first to `~/.local/share/axiom/themes/<id>.json`.

Applying a setup first saves your current one as `before-<id>`, so going back is one click under **Saved configs**.

## What a setup can hold

Only the look. Every setting in axiom has a scope, and a setup holds only `look` settings: CI rejects anything else, and axiom drops anything else when it applies one.

| Never in a setup | Why |
|---|---|
| Keybinds, apps, widget and button commands, pinned apps | A command would run as you. These stay yours. |
| Monitors, wallpapers (apart from the optional one below), accounts, paths | They only mean something on the PC they were set on. |
| Compositor config mode, lock screen, idle, polkit, greeter | They take something over on your PC, so only their own cards switch them. |
| API keys and passwords | Never shared. A config holding one is refused. |

On top of the look, a setup may bundle:
- **its own palette** (`theme.json`), when it doesn't use one of axiom's themes. It's installed as `community/<id>` and shows up on the Themes page.
- **one wallpaper**, which you only get if you choose to.

**Compositors.** A setup made on Hyprland applies on niri and sway too: what a compositor can't do (blur, some window looks) is skipped there. Its `tested` list says which ones its author actually ran it on.

**Fonts.** A setup lists the fonts it uses. Without one installed, text falls back to another font.

## Submit yours

The [contributing guide](CONTRIBUTING.md) has the details. In short:

1. Build your setup in axiom.
2. Go to **Settings → Maintenance → Share → Export**, with keybinds, apps and commands **off**.
3. Take a screenshot of the whole screen.
4. Submit it either way:
   - **No git needed**: open a [Submit a setup](../../issues/new?template=01-submit-setup.yml) issue, paste the export and drag the screenshot in. A pull request is made for you.
   - **As a pull request**: add `setups/<id>/` with `setup.json`, `config.json` and `screenshot.png`.

Every submission is checked against axiom's current `main` (its schema, themes and config migrations), then reviewed by a maintainer.

## For maintainers

| | |
|---|---|
| `scripts/check.sh [ID…]` | Everything CI checks: each config is loaded through axiom's own migration code (Qt 6's `qmltestrunner` on an axiom checkout), then `scripts/validate.py` |
| `scripts/validate.py --fix ID` | Writes `config.json`'s `_example` header from `setup.json` |
| `scripts/build_index.py OUT` | The catalog axiom reads and its gallery page (published as the [`catalog`](../../tree/catalog) branch) |
| `tests/test_validate.py`, `tests/test_issue.py` | The checks' own tests |
| `.github/workflows/` | `validate` (pull requests, main, nightly), `publish` (catalog + gallery after a merge), `submission` (issue → pull request, then `validate` on its branch) |

The axiom checkout comes from `--axiom DIR`, else `$AXIOM_DIR`, else `.axiom/`. CI always clones axiom's `main`, so the checks follow axiom with no pinning. The nightly run opens a `needs-update` issue when a change in axiom breaks a setup.

`main` is protected: changes land through a squashed pull request with the `validate` check passing and a code owner's approval (admins may merge their own). The `catalog` branch can't be deleted. CI force-pushes it.

The catalog is `https://raw.githubusercontent.com/axiom-dotfiles/community-setups/catalog/index.json`. Each setup's files are listed with their `path` (relative to the index), `sha256` and `size`.

## License

The scripts are [MIT](LICENSE), and so are the setups, their palettes and screenshots, unless they say otherwise. A wallpaper carries the license named in its setup's `setup.json`.
