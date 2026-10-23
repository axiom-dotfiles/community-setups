import QtQuick
import QtTest
import qs.components.methods

// Loads every setup the way axiom loads an import, with axiom's own code
// (ConfigMigration, SchemaValidation, ConfigExamples from a checkout's
// components/methods, laid out by its scripts/qml_modules.py --pure).
// scripts/check.sh writes .work/input.json ({ schema, setups: { id: config } })
// and reads .work/migrated.json back for scripts/validate.py:
//   { id: { migrated, removed, errors, applyErrors, secrets, changes, dropped, exported } | { exception } }
// `dropped` is what axiom wouldn't take from the setup: [{ path, scope }];
// `exported` the setup as an Export from this axiom would write it, without
// its header (SavedConfigsManager.exportConfig: scripts/check.sh --upgrade).
// What a shared file may hold is decided here by axiom's own
// ConfigExamples.pick, so a change to the schema's scopes (x-scope,
// x-scopeIf, x-monitorRef, x-takeover) needs no change in this repo.
TestCase {
  name: "Setups"

  function read(path) {
    const xhr = new XMLHttpRequest();
    xhr.open("GET", Qt.resolvedUrl(path), false);
    xhr.send();
    if (xhr.responseText === "")
      throw new Error("empty or unreadable: " + path);
    return JSON.parse(xhr.responseText);
  }

  // A synchronous PUT leaves the file empty: wait for `done`
  function write(path, content) {
    const state = {
      done: false
    };
    const xhr = new XMLHttpRequest();
    xhr.onreadystatechange = () => {
      if (xhr.readyState === XMLHttpRequest.DONE)
        state.done = true;
    };
    xhr.open("PUT", Qt.resolvedUrl(path));
    xhr.send(content);
    return state;
  }

  // ConfigManager.normalizeConfig, keeping what pruning removes
  function load(raw, schema) {
    const result = ConfigMigration.migrate(Utils.clone(raw));
    const migrated = Utils.clone(result.config);
    const removed = SchemaValidation.pruneUnknown(result.config, schema);
    return {
      "migrated": migrated,
      "removed": removed,
      "pruned": Utils.clone(result.config),
      "secrets": Object.keys(result.secrets ?? {}),
      "changes": result.changes ?? [],
      "config": SchemaValidation.applyDefaults(result.config, schema)
    };
  }

  // Monitors by place, as an export writes them: picking with these as the
  // monitors keeps a place ("#2", "*", and "" as "@primary") and leaves out
  // a monitor's name
  readonly property var places: Array.from({
    "length": 32
  }, (_, i) => "#" + (i + 1))

  // `value` with each "@primary" as "" (the primary monitor it stands for),
  // so picking writes it back as the same place
  function _primaryAsEmpty(value) {
    if (value === "@primary")
      return "";
    if (Array.isArray(value))
      return value.map(_primaryAsEmpty);
    if (!_isObject(value))
      return value;
    const result = {};
    for (const key in value)
      result[key] = _primaryAsEmpty(value[key]);
    return result;
  }

  // Each value of `config` (loaded, not filled) that a shared file can't
  // hold, as ConfigExamples.pick decides: [{ path, scope }], scope being
  // "takeover", or the first of personal, commands that would carry it,
  // else "machine". Defaults carry nothing (an export leaves them out, and
  // a migration may fill some in), so only the rest is looked at.
  function dropped(config, schema) {
    const values = ConfigExamples.sparse(_primaryAsEmpty(config), schema);
    const missing = carry => {
      const out = [];
      _missing(values, ConfigExamples.pick(values, schema, carry, places), "", out);
      return out;
    };
    const related = (a, b) => a === b || [a, b].some((p, i) => {
      const q = i === 0 ? b : a;
      return q.startsWith(p + ".") || q.startsWith(p + "[");
    });
    const takeovers = ConfigExamples.takeoverPaths(schema).map(path => path.join("."));
    const withPersonal = missing(["personal"]);
    const withCommands = missing(["commands"]);
    return missing([]).map(path => {
      let scope = "machine";
      if (takeovers.some(takeover => related(takeover, path)))
        scope = "takeover";
      else if (!withPersonal.some(other => related(other, path)))
        scope = "personal";
      else if (!withCommands.some(other => related(other, path)))
        scope = "commands";
      return {
        "path": path,
        "scope": scope
      };
    });
  }

  function _isObject(value) {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }

  // Nothing to carry: {}, [] or only those
  function _empty(value) {
    if (Array.isArray(value))
      return value.every(_empty);
    return _isObject(value) && Object.values(value).every(_empty);
  }

  // A place pick wrote for the monitor `value` names
  function _same(value, kept) {
    if (Utils.deepEqual(value, kept))
      return true;
    return typeof kept === "string" && /^(#[1-9][0-9]*|\*|@primary)$/.test(kept) && (value === "" ? kept === "@primary" : value === kept);
  }

  // Adds to `out` the paths of `value` that `kept` (its pick) left out
  function _missing(value, kept, path, out) {
    if (_empty(value) || _same(value, kept))
      return;
    if (Array.isArray(value) && Array.isArray(kept)) {
      // An item left out by its own scope (x-scopeIf) shifts the rest
      let j = 0;
      for (let i = 0; i < value.length; i++) {
        const item = value[i];
        const other = kept[j];
        const paired = j < kept.length && (value.length - i === kept.length - j || _same(item, other) || (_isObject(item) && _isObject(other) && ["id", "name", "type"].some(key => item[key] !== undefined && item[key] === other[key])));
        if (paired) {
          _missing(item, other, path + "[" + i + "]", out);
          j++;
        } else if (!_empty(item)) {
          out.push(path + "[" + i + "]");
        }
      }
      return;
    }
    if (_isObject(value) && _isObject(kept)) {
      for (const key in value)
        _missing(value[key], kept[key], path === "" ? key : path + "." + key, out);
      return;
    }
    out.push(path);
  }

  function test_load_setups() {
    const input = read(".work/input.json");
    const schema = input.schema;
    const defaults = load({
      "version": ConfigMigration.currentVersion
    }, schema).config;
    const out = {};
    for (const id in input.setups) {
      try {
        const loaded = load(input.setups[id], schema);
        // Applied as axiom applies a community setup: look only, onto the
        // defaults
        const applied = ConfigExamples.apply(defaults, loaded.config, schema, []);
        out[id] = {
          "migrated": loaded.migrated,
          "removed": loaded.removed,
          "secrets": loaded.secrets,
          "changes": loaded.changes,
          "dropped": dropped(loaded.pruned, schema),
          "exported": ConfigExamples.sparse(ConfigExamples.pick(loaded.config, schema, [], places), schema),
          "errors": SchemaValidation.validationErrors(loaded.config, schema),
          "applyErrors": SchemaValidation.validationErrors(applied, schema)
        };
      } catch (e) {
        out[id] = {
          "exception": String(e)
        };
      }
    }
    const state = write(".work/migrated.json", JSON.stringify(out));
    tryVerify(() => state.done);
  }
}
