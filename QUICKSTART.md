# Quick test

Download **AX-review-windows-x64.zip** from [Releases](https://github.com/crossgamervn-ux/bar-xray/releases/latest) and extract it. The ZIP contains both compiled DLLs, Python files, and the AX widget.

Requires **64-bit Python 3.11+**, Windows x64, and the exact reference Recoil **2026.07.04** executable checked by the tool. The game/engine is not bundled. DLLs need no local compilation. Keep the extracted directory structure intact.

## Fastest: command line

Start a developer-controlled match. Open a terminal in the extracted folder:

```powershell
python runtime/demo.py status
python runtime/demo.py on
python runtime/demo.py off
```

## With the AX button

Replace the example path with your actual BAR **data** directory. Install once:

```powershell
python runtime/widget_bridge.py --data "C:\game\Beyond-All-Reason\data" --install
```

Then start the bridge and leave its terminal open:

```powershell
python runtime/widget_bridge.py --data "C:\game\Beyond-All-Reason\data"
```

In the match, enter `/luaui reload`. Enable **AX** in the widget list if it is disabled. When the button says CONNECTED, click it to toggle ON/OFF.

The installer writes `LuaUI/Widgets/ax.lua` and `LuaUI/Config/op_file_client.lua`, generates a fresh local token, and backs up existing files in `LuaUI/Config/ax_review`. The bridge handles only AX view requests; do not run it alongside the original OP bridge.

The original AX widget has extra display code. Income is not supplied by this minimal bridge, so no income panel is expected. The optional historical PIP shim is included for reference but is not installed automatically.

## Finish

Turn AX OFF, stop the Python bridge with Ctrl+C, then exit the test game to unload the hooks. To remove the widget integration, disable/remove `LuaUI/Widgets/ax.lua` or restore the installer's backup. Do not delete the shared `op_file_client.lua` if other OP widgets use it.

An unsupported-build error means the executable does not match; changing the hash is not a version update. If DLL initialization fails, restart the test game before retrying.

The packaged DLLs compile successfully. The CLI/widget adapters were checked locally, but this release has not been live-tested in a match since the game was removed. Earlier evidence is in `evidence/recorded-checks.json`.

AI assisted with preparing the code and documentation.
