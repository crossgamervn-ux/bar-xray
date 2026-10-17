-- Local PIP compatibility: use the engine full-view state for the default view.
-- Keep the installed game's implementation and explicit tracked/LOS perspectives.
local a = assert(VFS.LoadFile('luaui/Widgets/gui_pip.lua', VFS.ZIP), 'PIP archive source missing')
local b = 'elseif not cameraState.mySpecState then\n\t\tlocal myTeamID = Spring.GetLocalTeamID()'
local c = 'elseif not cameraState.mySpecState and not fullview then\n\t\tlocal myTeamID = Spring.GetLocalTeamID()'
a = a:gsub('\r\n', '\n')
local d, e = a:find(b, 1, true)
if d and not a:find(b, e + 1, true) then
  a = a:sub(1, d - 1) .. c .. a:sub(e + 1)
  Spring.Echo('[PIP local] Engine view compatibility loaded')
else
  Spring.Echo('[PIP local] Source changed; using original implementation')
end
local f, g = loadstring(a, '@luaui/Widgets/gui_pip.lua')
assert(f, g)
setfenv(f, getfenv(1))
return f()
