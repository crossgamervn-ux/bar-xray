# Private security report: client-side fog-of-war disclosure through spectator view state

Prepared: 17 October 2026  
Reporter / in-game nickname: CrossGamer (Discord: @Cross)  
Contact: existing private Discord ticket; account email not provided  
Intended recipients: BAR / Recoil Engine maintainers
tôi## Summary

I am reporting a local client modification that exposed units normally hidden by fog of war. My local tool was called AX. It used a native DLL to change the engine's full-view state and invoke existing engine refresh functions. This also widened the LuaUI read context, allowing UI code to read information outside its normal ally-team visibility restrictions.

One retained diagnostic records `spectating = 0` while `full_view = 1` and `full_read = 1`. In that snapshot, control and selection remained assigned to the local team. The distinction matters: this was not simply a spectator enabling the intended full-view option.

I would like the maintainers to investigate the trust boundary and advise on mitigation. I am providing the method privately rather than publishing a ready-to-run tool. I have not assigned a severity score or established the scope across current builds.

## Build and prerequisites

- Platform: Windows x64.
- Local documentation identifies the reference engine as Recoil `2026.07.04`.
- Executable SHA-256 enforced by the retained tooling:
  `2b5362606e697d9f81bdb8cda7ecad9951957d9de8ad516f79f337d905351e3b`
- Prerequisite: ability to modify/inject code into the local game process. This is not a remote compromise or a server-code-execution issue.
- The implementation is build-specific. Source tags/commits used during analysis are not proof of the exact commit used to build the executable.
- The game installation and live game logs were subsequently removed locally. Source code and selected diagnostics remain. This report is based on those retained artifacts and prior observations, not a fresh reproduction on the latest engine.

## Investigation and mechanism

1. I compared the public Recoil C++ source with local disassembly/decompiler output to identify the view-state objects and relevant refresh functions. I used module-relative addresses because absolute addresses change between processes.
2. An earlier implementation only changed the local full-view flag. That did not reliably refresh all UI/minimap presentation.
3. The later DLL processed a toggle request on the engine thread identified by an existing native bridge, with a check that execution was outside the synced context.
4. It changed the field identified as `gu->spectatingFullView`, then called `CLuaUI::UpdateTeams()` to refresh LuaUI permissions/read-team state.
5. It called `CUnitDrawerData::PlayerChanged(...)` to refresh unit-drawing/icon state.
6. A local widget supplied an on/off control. A separate local compatibility adjustment was used for the PIP/minimap widget's visibility filtering. Therefore, the full UI outcome should not be described as the result of one machine instruction alone.

The important operation is a write to client-side data followed by existing engine functions. The DLL also installs a hook to schedule this work; describing the entire method merely as “patching one instruction” would be inaccurate.

## Retained evidence

These are separate snapshots/checks, not one continuous recording:

| Artifact | Relevant observation |
|---|---|
| `luaui-diagnostic.json` | `spectating=0`, `full_view=1`, `full_read=1`, `ctrl_team=0`, `select_team=0`, `read_team=-2`, `read_ally_team=-2` |
| `ax-v2-validation.json` | OFF → ON → restored changed full-view/full-read and read-ally-team, while `ctrl_team` remained 12. ON had `read_ally_team=-2`. This particular check had zero units in the draw list. |
| `refresh-v2-result.json` | Status 0 on the expected thread; 9 units in the inspected list; entries counted by the tool as invalid icons changed from 8 to 0. |
| Prior user observations | World visibility and later minimap icons were reported as working. The minimap result followed a LuaUI reload and local PIP compatibility change. |

The zero-unit toggle check proves state transitions, not visual exposure by itself. The other artifacts and visual observations must be considered separately. The meaning of `-2` as unrestricted read access should be verified against the affected engine revision rather than inferred from the number alone.

## Impact and limits

The observed effect was local visibility of information that the normal player view would hide, together with an expanded LuaUI read context. This could enable unfair observation and UI-assisted decisions in a match.

I have not established that this changes simulation LOS, grants control over other teams, modifies other clients' displays, or changes the server's authoritative player/spectator state. I do not have packet-capture evidence proving that the modification is undetectable or that no relevant information reaches the server. Spectator screenshots alone would not demonstrate the non-spectator issue; the retained non-spectator diagnostic is the specific evidence for that distinction.

If hidden unit state is already present in the client for simulation, closing this particular display/read-context path will not, by itself, prevent arbitrary process-memory inspection. Please evaluate this as a client trust-boundary problem rather than assume that hiding a widget or changing an address eliminates the underlying risk.

## Suggested maintainer validation

In an isolated developer-controlled match with a normal player and units outside that player's LOS/radar:

- Confirm the unmodified client hides those units and restricts the LuaUI read context.
- Instrument the spectator/full-view transition and `CLuaUI::UpdateTeams()` path. Check whether normal-player state can acquire unrestricted read flags without a legitimate spectator transition.
- Compare render state, LuaUI read/control/selection teams, and synced LOS before and after the transition.
- Check ordinary minimap and PIP independently, including behavior after LuaUI reload.
- Capture relevant network/server state if assessing propagation or detection; do not infer these from the local display.
- Repeat on currently supported builds before deciding which versions are affected.

I can provide the retained build-specific source and diagnostics privately for reproduction. This report itself does not include an injector, runnable DLL, authentication tokens, or an automated patch script.

## Mitigation considerations

- Audit the propagation of spectator/full-view state into LuaUI read permissions, especially `CLuaUI::UpdateTeams()` and Lua read-access checks.
- Maintain clear separation between view permissions, control permissions, and actual player/spectator role. Add regression tests for normal-player and spectator transitions.
- Review unit-drawing/minimap caches so legitimate permission changes do not leave stale privileged presentation.
- Treat local consistency checks or integrity checks as defense in depth: a process owner can modify client-side checks too.
- Assess whether hidden information can be withheld where the engine architecture permits it. Do not assume this is a trivial change for a deterministic simulation client.

## Evidence provenance / private follow-up

Reviewed local artifacts: `recoil-control/ax_control.py`, `native/view_refresh_v2.cpp`, `VIEW_VI.md`, `engine_support.py`, `ENGINE_UPDATE_VI.md`, and the three JSON diagnostics listed above.

Please let me know which private upload method you prefer for the retained source/diagnostics and which supported build you want investigated. I will not assume these results apply to a newer binary without verification.
