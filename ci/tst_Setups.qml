import QtQuick
import QtTest
import qs.components.methods

// Loads every setup the way axiom loads an import, with axiom's own code
// (ConfigMigration, SchemaValidation, ConfigExamples from a checkout's
// components/methods, laid out by its scripts/qml_modules.py --pure).
// scripts/check.sh writes .work/input.json ({ schema, setups: { id: config } })
// and reads .work/migrated.json back for scripts/validate.py:
//   { id: { migrated, removed, errors, applyErrors, secrets, changes } | { exception } }
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
      "secrets": Object.keys(result.secrets ?? {}),
      "changes": result.changes ?? [],
      "config": SchemaValidation.applyDefaults(result.config, schema)
    };
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
        // Applied as axiom applies an import: look only, onto the defaults
        const applied = ConfigExamples.apply(defaults, loaded.config, schema, false);
        out[id] = {
          "migrated": loaded.migrated,
          "removed": loaded.removed,
          "secrets": loaded.secrets,
          "changes": loaded.changes,
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
