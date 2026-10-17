# AX: how the full-view change works

I made AX while tracing BAR/Recoil's visibility code. The main finding was that changing the local full-view flag and running the engine's existing refresh functions also changed what LuaUI could read.

The important part is in [view_refresh_v2.cpp](runtime/native/view_refresh_v2.cpp). Start there, especially `callback()`. The widget is just an on/off button.

## What the C++ does

The DLL receives a requested value through shared memory. Its callback waits until it is running on the engine thread recorded by the resident bridge, outside the synced context. It then does three things:

```cpp
// Names below describe the objects identified during analysis.
gu->spectatingFullView = requestedValue;
CLuaUI::UpdateTeams();
unitDrawerData->PlayerChanged(localPlayerID);
```

This is a readable summary, not the literal code. The original implementation uses addresses relative to the loaded executable and offsets into the engine objects.

**The first write changes the view flag.** It does not set `gu->spectating` or turn the player into a spectator.

**`CLuaUI::UpdateTeams()` refreshes the LuaUI context.** In the saved checks, turning AX on changed `full_read` to true and `read_ally_team` to `-2`, while the control team stayed unchanged.

**`CUnitDrawerData::PlayerChanged()` refreshes drawing/icon state.** Changing only the flag was not enough to refresh all the presentation. The later version added this call. The PIP minimap also needed a separate widget adjustment and a LuaUI reload in the historical test.

So the core is a write to engine state followed by two existing engine functions. It is not a replacement renderer, and it is not just a single patched instruction.

## How the hook runs

`OpStart()` checks the expected function bytes, opens the resident bridge's shared memory, creates the AX request/result mapping, and installs a MinHook hook on the callback identified as `GetRenderFeaturesDrawFlagChanged`.

When a request is pending, `callback()` checks the thread, request deadline, pointers, and synced-context state. It applies the change, writes the result back, then calls the original function. It only changes the view when requested; it does not continuously force the flag on.

The separate [bridge.cpp](runtime/native/bridge.cpp) supplies the engine-thread identity used by this check. Its original unit-order code is still in the file, but the AX demo does not submit unit orders.

## Main files

| File | Purpose |
|---|---|
| [view_refresh_v2.cpp](runtime/native/view_refresh_v2.cpp) | Changes the full-view flag and calls the LuaUI/render refresh functions. |
| [bridge.cpp](runtime/native/bridge.cpp) | Resident bridge used to identify the engine thread. |
| [ax_control.py](runtime/ax_control.py) | Sends the requested toggle through shared memory and reads the state back. |
| [native_client.py](runtime/native_client.py) | Loads the DLLs and opens the resident bridge mapping. |
| [engine_support.py](runtime/engine_support.py) | Finds the process, checks its executable, and reads engine memory. |
| [demo.py](runtime/demo.py) | Small command-line entry point for `status`, `on`, and `off`. |
| [ax.lua](reference/widgets/ax.lua) | Original widget frontend. Not needed for the command-line demo. |
| [gui_pip.lua](reference/widgets/gui_pip.lua) | Historical compatibility adjustment for the game's PIP widget. |

The command-line flow is:

```text
 demo.py
   -> ax_control.py
   -> shared-memory request
   -> view_refresh_v2.cpp callback
   -> full-view write + UpdateTeams + PlayerChanged
   -> shared-memory result
   -> Python reads the engine state again
```

The original widget reached the same Python handler through a local bridge service. The command-line version skips that UI/service setup.

## What was recorded

One saved diagnostic contains:

```text
spectating      = 0
full_view       = 1
full_read       = 1
ctrl_team       = 0
select_team     = 0
read_team       = -2
read_ally_team  = -2
```

A separate OFF/ON/OFF check kept `ctrl_team=12` throughout. Another refresh check counted 8 invalid icon entries before the refresh and 0 afterward, in a list of 9 units.

These are separate checks. The original values are in [recorded-checks.json](evidence/recorded-checks.json). They show local state changes; they do not establish what the server or other clients observed.

## Build and try it

The retained code targets **Windows x64, Recoil 2026.07.04**, with a specific executable fingerprint checked by `engine_support.py`. The offsets are not portable to another build.

You need 64-bit Python and an x64 MinGW-w64 GCC toolchain. MinHook is included. From the repository root:

```powershell
.\runtime\native\build.ps1 -Toolchain 'C:\msys64\mingw64\bin'
```

Start a developer-controlled match with the matching engine, then run:

```powershell
python .\runtime\demo.py status
python .\runtime\demo.py on
python .\runtime\demo.py off
```

`status` only reads state. `on` and `off` load the required DLLs if needed. Use `--pid <PID>` if more than one game process is running. Exit the game to unload the hooks; `off` only changes the view state back.

Both DLLs compile from the files in this repo. The new CLI wrapper has not been tested in a live match since the game was uninstalled; the saved evidence comes from the earlier AX implementation. The widget files are included for reference and are not required to run the CLI.

---

AI assisted with the code analysis, parts of the implementation, and the writing of this article. The source files and recorded diagnostics are included so the technical claims can be checked directly.
