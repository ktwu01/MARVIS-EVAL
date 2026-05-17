# Running Mavis Locally (SOP)

This SOP covers the version of Mavis observed on this workstation:
**MiniMax.app v3.0.27 (electron)**, with a bundled daemon-management CLI
at `/Applications/MiniMax.app/Contents/Resources/resources/daemon/cli.js`,
symlinked at `~/.mavis/bin/mavis`.

Important terminology:

- `mmx` / `mmx-cli` is the public MiniMax platform CLI documented by
  MiniMax and installable with `npm install -g mmx-cli`. **We do not use
  it here.**
- `mavis` is the desktop-app-bundled local daemon CLI installed as a side
  effect of installing `MiniMax.app` from the DMG. **This is what
  Mavis-Eval drives.** It is not separately documented in public MiniMax
  docs as of this writing.

The goal is a healthy, locally running Mavis daemon that the Mavis-Eval
harness (`python3 -m mavis_eval run-mavis ...`) can connect to.

---

## TL;DR (the working recipe on v3.0.27)

1. **Open the MiniMax desktop app** (`/Applications/MiniMax.app`).
2. Wait ~2 seconds. The Electron app starts its own daemon as a
   subprocess; you do not need to run `mavis start`.
3. From your terminal, verify and drive it with `~/.mavis/bin/mavis ...`.

Skip the desktop app and run `mavis start` directly on v3.0.27 and the
daemon crashes with `Cannot find module 'better-sqlite3'`. The desktop
app sidesteps that bug because it launches the daemon under Electron's
Node runtime, which can see the bundled native module. See
[§5](#5-known-failure-mavis-start-without-the-desktop-app) for details.

---

## 1. Layout

| Path | Role |
|------|------|
| `/Applications/MiniMax.app/Contents/MacOS/MiniMax` | Electron desktop binary; opening this starts the daemon |
| `/Applications/MiniMax.app/Contents/Resources/resources/daemon/cli.js` | Daemon CLI entry |
| `/Applications/MiniMax.app/Contents/Resources/resources/daemon/daemon.js` | Daemon process |
| `/Applications/MiniMax.app/Contents/Resources/app.asar.unpacked/node_modules/better-sqlite3/` | Native SQLite module (Mach-O arm64, ABI matched to Electron's Node) |
| `~/.mavis/bin/mavis` | Symlink → daemon `cli.js`. Use it via absolute path; it may not be on `$PATH` after a fresh install |
| `~/.mavis/` | Per-user data dir: `sqlite.db`, `sessions/`, `logs/`, `config.yaml` |
| `~/.mavis/daemon.pid` | JSON. When `owner` is `electron`, the daemon was started by the desktop app |
| `~/.mavis/daemon.port` | Currently active daemon port (dynamic; **not** 5321 in v3.0.27, observed 15321 on this workstation) |

The CLI talks to the daemon over local HTTP on whatever port is in
`~/.mavis/daemon.port`. **Do not hard-code 5321** in scripts; read it from
that file or call `mavis status`.

---

## 2. One-time setup

```sh
# 1. Install MiniMax.app from the official DMG (manual step in the GUI).

# 2. Add the CLI to PATH (optional; you can also call ~/.mavis/bin/mavis
#    directly):
echo 'export PATH="$HOME/.mavis/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
which mavis                    # /Users/<you>/.mavis/bin/mavis
mavis --version                # 3.0.27 (or later)
```

If `which mavis` still returns nothing after editing `~/.zshrc`, use the
absolute path `~/.mavis/bin/mavis` everywhere below. Mavis-Eval's
adapter already accepts an explicit CLI path; it does not require `mavis`
to be on `$PATH`.

---

## 3. Start the daemon (happy path)

The supported way on v3.0.27:

```sh
# 1. Open the desktop app. This starts the daemon under Electron's Node.
open /Applications/MiniMax.app

# 2. Wait a couple of seconds, then verify the daemon is healthy.
~/.mavis/bin/mavis status
# {
#   "status": "running",
#   "pid": 51801,
#   "port": 15321,
#   "uptimeSeconds": 0
# }

# 3. Confirm the daemon really was started by the desktop app
#    (owner: "electron"). This is the marker that you are on the
#    happy path, not on a partial CLI-only start.
cat ~/.mavis/daemon.pid
# {"pid":51801,"owner":"electron","startedAt":"2026-05-17T07:22:25.638Z"}

# 4. Smoke test: list agents.
~/.mavis/bin/mavis agent list | head -10
```

You can leave the desktop app open in the background; you do not need to
interact with its GUI for the CLI to work.

To stop the daemon, quit the MiniMax app from the macOS menu bar. The
daemon shuts down with it.

---

## 4. Drive a Mavis session from the CLI

Once the daemon is up (i.e. `mavis status` shows `running`), Mavis-Eval
can drive it:

```sh
cd ~/Documents/dev/MARVIS-EVAL

python3 -m mavis_eval run-mavis cases/examples/smoke_seed_cases.json \
  --case-id missing_file_recovery_001 \
  --fixtures-root fixtures \
  --timeout-s 300
```

Expected on success: a new run dir under `runs/missing_file_recovery_001/`
with `trajectory.jsonl`, a JSON report under `reports/`, and a JSON
summary on stdout.

You can also call the CLI directly to sanity-check:

```sh
~/.mavis/bin/mavis session new mavis \
  --from root \
  --workspace "$PWD" \
  --prompt "Say OK and stop."
~/.mavis/bin/mavis session info <session-id>
```

All Mavis sessions are persisted in `~/.mavis/sqlite.db`. Mavis-Eval's
`scripts/export_from_mavis_db.py` reads from there to reconstruct
`runs/<case_id>/` if the workspace files were cleaned up.

---

## 5. Known failure: `mavis start` without the desktop app

### Symptom
```
$ mavis start --no-web
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
upward from `resources/daemon/`, so resolution fails when the daemon is
spawned under system Node.

The desktop app avoids this because it spawns the daemon as a child of
the Electron process, where the Electron-bundled Node ABI matches the
native `.node` file and the unpacked `node_modules` are reachable.

The daemon does support an env override (`MAVIS_SQLITE3_MODULE_PATH`),
**but `cli.js`'s `spawnDaemon` strips that key before spawning the
daemon child process** (only `MAVIS_REGION` and `MAVIS_BUILD_ENV` are
re-injected). Setting the env var in your shell does **not** propagate
to the daemon when you use `mavis start`.

ABI check, for the curious:

```sh
node -p 'process.version + " " + process.versions.modules'
# v26.0.0 147   <- system Node

ELECTRON_RUN_AS_NODE=1 /Applications/MiniMax.app/Contents/MacOS/MiniMax \
  -e 'console.log(process.version, process.versions.modules)'
# v22.20.0 139   <- Electron's bundled Node

# The bundled .node file was built for ABI 139. Loading it from system
# Node (ABI 147) fails with:
#   better_sqlite3.node was compiled against NODE_MODULE_VERSION 139.
#   This version of Node.js requires NODE_MODULE_VERSION 147.
```

### Fix path

**Preferred:** open the desktop app and let Electron spawn the daemon
(§3 above). This is the recipe that works on v3.0.27 today.

**Last-resort manual start, only if the desktop app is unavailable:**
spawn the daemon directly under Electron's Node:

```sh
export PATH="/Applications/MiniMax.app/Contents/Resources/resources/opencode:$HOME/.mavis/bin:$PATH"

NODE_PATH="/Applications/MiniMax.app/Contents/Resources/resources/daemon/node_modules" \
MAVIS_SQLITE3_MODULE_PATH="/Applications/MiniMax.app/Contents/Resources/app.asar.unpacked/node_modules" \
ELECTRON_RUN_AS_NODE=1 \
/Applications/MiniMax.app/Contents/MacOS/MiniMax \
  /Applications/MiniMax.app/Contents/Resources/resources/daemon/daemon.js \
  --port 15321 \
  --data-dir "$HOME/.mavis" \
  > "$HOME/.mavis/logs/manual-daemon.log" 2>&1 &

~/.mavis/bin/mavis status
```

This bypasses `mavis start` and reproduces what the desktop app does.
Use it only when you cannot run the GUI (CI, headless server, etc.).

### What NOT to try
- `mavis start` (or `mavis start --no-web`) without the desktop app open
  on v3.0.27. It fails as documented above.
- `export MAVIS_SQLITE3_MODULE_PATH=...` before `mavis start`. The CLI
  strips it before spawning the daemon.
- `npm install better-sqlite3 -g` and adding to `NODE_PATH`. System Node
  and Electron Node have different native module ABIs here, so the
  globally-installed copy will not load anyway.
- Editing files under `/Applications/MiniMax.app`. The directory is
  read-only without `sudo`, and modifying app contents breaks code
  signing.
- Relying on `mavis update --force` as the primary fix in v3.0.27. This
  command is hard-coded to install `@minimax/mavis` from
  `https://npmmirror.xaminim.com/`; on this workstation that registry
  timed out, and the package is not visible on the public npm registry.

### Quick triage

```sh
~/.mavis/bin/mavis --version                                      # the CLI itself is fine; it doesn't need sqlite
ls /Applications/MiniMax.app/Contents/Resources/resources/daemon/node_modules/ | grep -i sqlite
# Empty result = the packaging bug. Open the desktop app instead.

cat ~/.mavis/daemon.pid 2>/dev/null
# If "owner":"electron", desktop app is driving the daemon (happy path).
# If absent or owner is something else, daemon is not running or was
# started a different way.
```

---

## 6. Logs to check when something is wrong

- `~/.mavis/logs/daemon-spawn-*.log`: exit reasons for failed daemon
  launches via `mavis start`. The most useful single log.
- `~/.mavis/logs/opencode-*.log`: agent runtime log (timestamped).
- `~/.mavis/logs/plugin-*.log`: plugin runtime log.

Tail the freshest log:
```sh
ls -t ~/.mavis/logs/*.log | head -1 | xargs tail -n 200
```

---

## 7. Clean reset (when in doubt)

```sh
# Quit MiniMax from the macOS menu bar first, then:
rm -f ~/.mavis/daemon.lock ~/.mavis/daemon.pid ~/.mavis/daemon.port

# Optional: archive (do not delete) sqlite.db before a reinstall.
mv ~/.mavis/sqlite.db ~/.mavis/sqlite.db.bak.$(date +%s)

# Reinstall MiniMax.app from the official DMG, then reopen it.
```

Do **not** delete `~/.mavis/` wholesale. It holds your agents, sessions,
credentials, and memory.

---

## 8. Verification log

Last end-to-end verification of this SOP on this workstation:

| step | command | observed |
|------|---------|----------|
| reset | `osascript -e 'tell application "MiniMax" to quit'` | `mavis status` → `{"status":"stopped"}`, `daemon.pid`/`daemon.port` removed |
| §3.1 start | `open /Applications/MiniMax.app` | within 1 second, daemon ready |
| §3.2 status | `~/.mavis/bin/mavis status` | `{"status":"running","pid":70582,"port":15321,"uptimeSeconds":0}` |
| §3.3 owner | `cat ~/.mavis/daemon.pid` | `{"pid":70582,"owner":"electron","startedAt":"2026-05-17T08:21:17.019Z"}` |
| §3.4 agents | `~/.mavis/bin/mavis agent list` | `mavis`, `verifier`, ... built-in agents listed |
| §4 drive | `python3 -m mavis_eval run-mavis ... --case-id missing_file_recovery_001 --timeout-s 120` | session `mvs_a9a8c2af016744d6b966e99ab5c92780` ran in 79.5s, evaluator returned `pass: true` |

If your numbers differ in shape (port not 15321 is fine; `owner` not
`electron` is a problem; `status` stuck at `stopped` after the desktop
app is open is a problem), see §5 and §6.

