# AX / Recoil fog-of-war report and reproduction source

Technical material submitted by CrossGamer for BAR/Recoil maintainers. Start with [the report](docs/REPORT.md) and [recorded evidence](evidence/recorded-checks.json).

## Exact reference build

Windows x64, documented locally as **Recoil 2026.07.04**. Executable SHA-256:

`2b5362606e697d9f81bdb8cda7ecad9951957d9de8ad516f79f337d905351e3b`

The hash, not a folder name or release label, is the compatibility check. No current-version support is claimed. The engine binary and game content are not included. Obtain the reference build from the maintainers or their official archive; do not change the expected hash merely to bypass the check.

## What this reproduces

The retained native implementation changes the client field identified as `gu->spectatingFullView`, calls `CLuaUI::UpdateTeams()`, then `CUnitDrawerData::PlayerChanged()`. Recorded diagnostics include a non-spectator state with full-view/full-read enabled. This does not prove that simulation LOS changes, another client's display changes, or the modification cannot be detected.

## Build and run in a developer-controlled test match

Prerequisites: Windows x64, 64-bit Python 3.11+, an x64 MinGW-w64 GCC toolchain, and the **exact reference executable**. No third-party Python packages are needed. MinHook sources and their license are included.

From the repository root, in PowerShell:

```powershell
.
untime
ativeuild.ps1 -Toolchain 'C:\msys64\mingw64\bin'
python .
untime\demo.py --help
```

Use the appropriate path to your 64-bit Python if `python` resolves to another installation.

1. Start an isolated test match on the reference engine, as a normal player. Put test enemy units outside the player's LOS/radar. Keep the game running/rendering and detach debuggers before loading hooks.
2. Record the baseline:

```powershell
python .
untime\demo.py status
```

3. Enable the retained AX transition:

```powershell
python .
untime\demo.py on
```

4. Observe the world view and inspect the printed `value`, `full_read`, `read_ally_team`, and `ctrl_team`. Compare with the baseline. This readback alone is not a visual test.
5. Disable and record restoration:

```powershell
python .
untime\demo.py off
python .
untime\demo.py status
```

`--pid <PID>` can explicitly select a test process. Without it, exactly one `spring.exe` must be running.

`status` only reads state and does not inject DLLs. `on`/`off` load the original resident bridge if needed, wait for its engine-thread identity, then use the original AX control path. This wrapper sends no unit commands and starts no network service. The retained bridge source still contains its original order-handling implementation, although the demo does not use it.

The DLLs remain loaded after `off`; exit the test game to unload the hooks. After an initialization failure or a DLL rebuild, restart the game instead of reinjecting into the same process. The toggle is not a general-purpose restoration of every possible pre-existing spectator configuration: record baseline state and use a fresh normal-player test match.

## Files and reading order

- [docs/REPORT.md](docs/REPORT.md): historical investigation, observations and limitations.
- [evidence/recorded-checks.json](evidence/recorded-checks.json): separate historical checks with PID/raw addresses removed.
- [runtime/native/view_refresh_v2.cpp](runtime/native/view_refresh_v2.cpp): native mutation and refresh, especially `callback()` and `OpStart()`.
- [runtime/ax_control.py](runtime/ax_control.py): request serialization, shared-memory control and readback.
- [runtime/demo.py](runtime/demo.py): new standalone reproduction wrapper; replaces the original UI/server orchestration for this package.
- [runtime/engine_support.py](runtime/engine_support.py): executable hash verification, process discovery and reads.
- [runtime/native_client.py](runtime/native_client.py): original DLL loading and resident bridge transport.
- [runtime/native/bridge.cpp](runtime/native/bridge.cpp): original resident bridge supplying the engine-thread identity.
- [reference/widgets/ax.lua](reference/widgets/ax.lua): original frontend for reference only. It uses a placeholder token and the old external OP infrastructure, not the standalone CLI.
- [reference/widgets/gui_pip.lua](reference/widgets/gui_pip.lua): historical PIP compatibility shim, optional and dependent on the matching game's original widget. Not required for the core world-view test. It is not installed automatically.
- [docs/HISTORICAL-NOTES-VI.md](docs/HISTORICAL-NOTES-VI.md): original Vietnamese notes; some refer to earlier TCP transport or separate tests.

The original full path was UI -> local IPC/Python handler -> shared memory -> DLL callback -> engine state/readback. The standalone wrapper begins at the Python handler, eliminating the widget, authentication token, and IPC service setup.

## Validation status

Both DLLs were compiled from these packaged sources on the reporter's machine. Python syntax/imports and CLI help were checked. The new standalone wrapper has **not been live-tested in a match**, because the game installation was removed. Evidence is from earlier tests of the retained implementation, not a fresh test of this package. Do not interpret successful compilation as confirmation of runtime compatibility or exploit scope.

A complete minimap/UI outcome also depends on the game's rendering widgets. The report distinguishes native state transitions from historical PIP/minimap observations.

## Troubleshooting

- SHA256 mismatch: unsupported binary; stop and verify the reference build.
- No game / multiple processes: enter a match or specify the correct test PID.
- Access denied: Python must be allowed to access the test process; check whether the two processes run at different privilege levels.
- Missing DLL: run the build script; commit contents intentionally exclude precompiled binaries.
- Missing thread identity / callback timeout: ensure the match is active and rendering, with no attached debugger or competing hooks; restart after failed initialization.
- State changes but no icons: inspect world rendering and PIP separately; do not assume all game widgets refresh identically.

No account credentials, local bridge tokens, player logs, or game binaries are included. MinHook remains under its bundled license. No blanket license is asserted over the original project/engine-related material; consult the maintainers before redistribution beyond this disclosure.
