# Running Mavis Locally — SOP

This SOP covers the version of Mavis observed on this workstation:
**MiniMax.app v3.0.27 (electron)**, with a bundled daemon-management CLI
symlinked at `~/.mavis/bin/mavis`.

Important terminology:

- `mmx` / `mmx-cli` is the public MiniMax platform CLI documented by
  MiniMax and installable with `npm install -g mmx-cli`.
- `mavis` is the desktop-app-bundled local daemon CLI installed as a side
  effect of installing `MiniMax.app` from the DMG. As of this workstation's
  v3.0.27 install, it is not a separately documented public CLI.

The goal is a healthy, locally running Mavis daemon that the Mavis-Eval
harness (`python3 -m mavis_eval run-mavis ...`) can drive.

---

## 1. Layout

| Path | Role |
|------|------|
| `/Applications/MiniMax.app/Contents/MacOS/MiniMax` | Electron desktop binary |
| `/Applications/MiniMax.app/Contents/Resources/resources/daemon/cli.js` | Daemon CLI entry |
| `/Applications/MiniMax.app/Contents/Resources/resources/daemon/daemon.js` | Daemon process |
| `/Applications/MiniMax.app/Contents/Resources/app.asar.unpacked/node_modules/better-sqlite3/` | Native SQLite module (Mach-O arm64) |
| `~/.mavis/bin/mavis` | Symlink → daemon `cli.js`; this is what should be on `PATH` after the DMG install |
| `~/.mavis/` | Per-user data dir: `sqlite.db`, `sessions/`, `logs/`, `config.yaml`, … |
| `~/.mavis/logs/` | Daemon spawn + plugin logs; check here when the daemon won't start |

The CLI uses port **5321** by default. Override with `--port <N>` or
`MAVIS_PORT=N`.

`mavis start` uses the current shell's Node runtime through the `#!/usr/bin/env
node` shebang. On this workstation, system Node is `v26.0.0`, while the native
SQLite module bundled in the app was built for Electron's Node `v22.20.0`.

---

## 2. One-time setup

```sh
# 1. Confirm the CLI is on PATH
which mavis                    # should print /Users/<you>/.mavis/bin/mavis
mavis --version                # 3.0.27 (or later)

# 2. If `which mavis` returns nothing, add ~/.mavis/bin to PATH:
echo 'export PATH="$HOME/.mavis/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

## 3. Start, status, stop

```sh
mavis status                   # {"status": "stopped"}  or  running info
mavis start --no-web           # start daemon, don't open browser
mavis status                   # confirm running
mavis stop                     # clean shutdown
```

Useful flags:

- `--no-web` — don't open the web UI in your browser.
- `--no-service` — don't register a launchd service (dev use).
- `--port 5321` — pin port.
- `--data-dir ~/.mavis` — pin data dir.

---

## 4. Known failure: `Cannot find module 'better-sqlite3'`

### Symptom
```
$ mavis
  启动 Daemon ...
  等待 Daemon 就绪 ...
Error: Daemon exited immediately (code: 1, signal: null)
--- Recent daemon log ---
  Error: Cannot find module 'better-sqlite3'
  Require stack:
  - /Applications/MiniMax.app/Contents/Resources/resources/daemon/daemon.js
      at loadBetterSqlite3 (daemon.js:36005:39)
```

### Root cause
The Electron bundle places the native `better-sqlite3` module at
`/Applications/MiniMax.app/Contents/Resources/app.asar.unpacked/node_modules/better-sqlite3/`
but the daemon (`daemon.js`) is launched from
`/Applications/MiniMax.app/Contents/Resources/resources/daemon/` whose
`node_modules/` does **not** contain that package. `daemon.js` does
`createRequire(import.meta.url)("better-sqlite3")`, which only searches
upward from `resources/daemon/`, so resolution fails.

The daemon does support an env override (`MAVIS_SQLITE3_MODULE_PATH`),
**but the CLI strips that key before spawning the daemon child process**
(see `cli.js` → `spawnDaemon` → `buildChildEnv("spawn-daemon", { … })` —
only `MAVIS_REGION` and `MAVIS_BUILD_ENV` are re-injected). Setting the
env var in your shell does **not** propagate to the daemon.

The unpacked native module was built for Electron's Node ABI. On this
workstation:

```sh
node -p 'process.version + " " + process.versions.modules'
# v26.0.0 147

ELECTRON_RUN_AS_NODE=1 /Applications/MiniMax.app/Contents/MacOS/MiniMax \
  -e 'console.log(process.version, process.versions.modules)'
# v22.20.0 139
```

So forcing system Node to load the unpacked native module fails with:

```text
better_sqlite3.node was compiled against NODE_MODULE_VERSION 139.
This version of Node.js requires NODE_MODULE_VERSION 147.
```

`/Applications/MiniMax.app/Contents/Resources/resources/daemon/node_modules/`
is part of the app bundle. Mutating it by hand is fragile and may break the
desktop app bundle.

### Fix path (in order of preference)

1. **Update/reinstall MiniMax.app from the official desktop distribution.**
   This is the correct fix because the daemon, native SQLite module, Electron
   runtime, and bundled `opencode` binary need to agree with each other.
   ```sh
   ~/.mavis/bin/mavis --version
   ~/.mavis/bin/mavis status
   ```
2. **Use the desktop app to manage daemon lifecycle** if it is available.
   The public May 2026 messaging says CLI/API/Agent are included in the
   subscription, but public MiniMax docs currently document `mmx-cli`; this
   local `mavis` CLI is bundled with the desktop app.
3. **Temporary local workaround for evaluation only:** start the daemon with
   Electron's Node runtime, and make both bundled native modules and bundled
   `opencode` visible:
   ```sh
   export PATH="/Applications/MiniMax.app/Contents/Resources/resources/opencode:$HOME/.mavis/bin:$PATH"

   NODE_PATH="/Applications/MiniMax.app/Contents/Resources/resources/daemon/node_modules" \
   MAVIS_SQLITE3_MODULE_PATH="/Applications/MiniMax.app/Contents/Resources/app.asar.unpacked/node_modules" \
   ELECTRON_RUN_AS_NODE=1 \
   /Applications/MiniMax.app/Contents/MacOS/MiniMax \
     /Applications/MiniMax.app/Contents/Resources/resources/daemon/daemon.js \
     --port 5321 \
     --data-dir "$HOME/.mavis" \
     > "$HOME/.mavis/logs/manual-daemon.log" 2>&1 &

   ~/.mavis/bin/mavis status
   ~/.mavis/bin/mavis agent list
   ```
   This bypasses `mavis start`; use it only as a local unblocker.
4. **File a bug to MiniMax** if reinstall/update does not resolve it — this is a
   packaging bug, not a user-recoverable misconfiguration. Include:
   - `mavis --version`
   - `~/.mavis/logs/daemon-spawn.log` tail
   - `node --version`
   - `ls /Applications/MiniMax.app/Contents/Resources/app.asar.unpacked/node_modules/better-sqlite3` (should show files)
   - `ls /Applications/MiniMax.app/Contents/Resources/resources/daemon/node_modules/ | grep sqlite` (will be empty — the bug)

### What NOT to try
- `export MAVIS_SQLITE3_MODULE_PATH=...` — the CLI strips it on spawn; harmless but a dead end.
- `npm install better-sqlite3 -g` and adding to `NODE_PATH` — system Node and Electron Node have different native module ABIs here.
- Editing files under `/Applications/MiniMax.app` — read-only without `sudo` and breaks code signing.
- Relying on `mavis update --force` as the primary fix in v3.0.27. This
  command is hard-coded to install `@minimax/mavis` from
  `https://npmmirror.xaminim.com/`; on this workstation that registry timed out,
  and the package is not visible on the public npm registry.

### Quick triage
```sh
mavis --version                           # CLI itself is fine — it doesn't need sqlite
ls /Applications/MiniMax.app/Contents/Resources/resources/daemon/node_modules/ | grep -i sqlite
# Empty result = the packaging bug. Update/reinstall MiniMax.app, or use the
# Electron-Node workaround above for local evaluation.
```

---

## 5. Smoke test once daemon is up

```sh
mavis status                              # {"status": "running", "port": 5321, ...}
mavis agent list                          # at least the built-in agents
mavis session new mavis --from root --workspace "$PWD" --prompt "Say OK and stop."
mavis session info <session-id>
```

For end-to-end harness verification:

```sh
cd ~/Documents/dev/MARVIS-EVAL
python3 -m mavis_eval run-mavis cases/examples/smoke_seed_cases.json \
  --case-id missing_file_recovery_001 \
  --fixtures-root fixtures \
  --timeout-s 300
```

Expected: a new run dir under `runs/missing_file_recovery_001/` with
`trajectory.jsonl`, an evaluator report under `reports/`, and JSON
summary printed to stdout.

---

## 6. Logs to check when something is wrong

- `~/.mavis/logs/daemon-spawn.log` — exit reasons for failed daemon launches.
- `~/.mavis/logs/opencode-*.log` — agent runtime log (timestamped).
- `~/.mavis/logs/plugin-*.log` — plugin runtime log.

Tail the freshest log:
```sh
ls -t ~/.mavis/logs/*.log | head -1 | xargs tail -n 200
```

---

## 7. Clean reset (when in doubt)

```sh
mavis stop || true
rm -f ~/.mavis/daemon.lock ~/.mavis/daemon.pid ~/.mavis/daemon.port
# Optional: archive (do not delete) sqlite.db before reinstall
mv ~/.mavis/sqlite.db ~/.mavis/sqlite.db.bak.$(date +%s)
# Then update/reinstall MiniMax.app from the official desktop installer.
```

Do **not** delete `~/.mavis/` wholesale — it holds your agents, sessions,
credentials, and memory.
