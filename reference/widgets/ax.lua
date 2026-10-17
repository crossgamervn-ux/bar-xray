function widget:GetInfo()
  return {name='AX', desc='AX C++ control', author='local', date='2026-09-27', license='GPL v2', layer=0, enabled=true}
end

local a = Json or VFS.Include('common/luaUtilities/json.lua')
local b = '__TOKEN__'
local fileClient=VFS.Include('LuaUI/Config/op_file_client.lua').new(a,'ax')
local c, d, e = 0, 0, nil
local f, g, h = false, false, 'CONNECTING'
local i = {15, 0, 185, 0}
local incomeRows,incomeAt={},-100

local function j()
  local x, y = Spring.GetViewGeometry()
  i = {15, math.floor(y * 0.46) + 96, 185, math.floor(y * 0.46) + 134}
end

local function k(v)
  if e then return false end
  e=true
  if v~=nil then h='UPDATING' elseif not g then h='CONNECTING' end
  local started=fileClient:request({op='ax',token=b,value=v},function(q)
    e=nil;d=c+1
    g=type(q)=='table' and q.ok==true and type(q.value)=='boolean'
    if g then incomeRows=type(q.income)=='table' and q.income or {};incomeAt=c;f=q.value;h='CONNECTED'
    else h='DISCONNECTED';if q and q.error then Spring.Echo('[AX] '..q.error) end end
  end)
  if not started then e=nil;g=false;h='FILE BUSY' end
  return started
end

local function l()
  if g and not e then k(not f) end
end

function widget:Initialize() j() end
function widget:ViewResize() j() end
function widget:Update(v)
  c=c+v
  fileClient:update(v)
  if not e and c>=d then d=c+3;k(nil);fileClient:update(0) end
end

function widget:MousePress(x,y,v)
  if v==1 and x>=i[1] and x<=i[3] and y>=i[2] and y<=i[4] then l(); return true end
end
function widget:TextCommand(v)
  if v=='ax' then l(); return true end
end
function widget:DrawScreen()
  if Spring.IsGUIHidden and Spring.IsGUIHidden() then return end
  if not g then gl.Color(0.32,0.20,0.08,0.90)
  elseif f then gl.Color(0.08,0.42,0.20,0.95)
  else gl.Color(0.20,0.20,0.24,0.95) end
  gl.Rect(unpack(i)); gl.Color(1,1,1,1)
  gl.Text('AX: '..(g and (f and 'ON' or 'OFF') or '--'),i[1]+10,i[2]+22,12,'o')
  gl.Text(h,i[1]+10,i[2]+7,9,'o')
end
function widget:Shutdown()
  fileClient:shutdown();e=nil
end

local m, n, o = {}, {}, 0
local function p()
  local _, v = Spring.GetSpectatingState()
  return g and f and v
end
local q = widget.Initialize
function widget:Initialize()
  q(self)
  for v,w in pairs(UnitDefs or {}) do
    local x=0
    for _,y in ipairs(w.weapons or {}) do
      local z=WeaponDefs[y.weaponDef]
      if z and (z.interceptor or 0)>0 and (z.coverageRange or 0)>x then x=z.coverageRange end
    end
    if x>0 then m[v]=x end
  end
end
local r = widget.Update
function widget:Update(v)
  r(self,v)
  if not (g and f) then n={}; return end
  if not p() then n={}; return end
  o=o-v
  if o>0 then return end
  o=0.25
  local w={}
  local x=Spring.GetMyAllyTeamID()
  for _,y in ipairs(Spring.GetAllUnits() or {}) do
    local z=m[Spring.GetUnitDefID(y)]
    if z and Spring.GetUnitAllyTeam(y)~=x then
      local a,b,c=Spring.GetUnitPosition(y)
      local d,e,f=Spring.GetUnitStockpile(y)
      if a then w[#w+1]={a,b,c,z,d,e,f} end
    end
  end
  n=w
end
function widget:DrawWorldPreUnit()
  if #n==0 or not p() or Spring.IsGUIHidden() then return end
  gl.DepthTest(false)
  gl.LineWidth(1.5)
  gl.Color(1,0.85,0.12,0.65)
  for _,v in ipairs(n) do gl.DrawGroundCircle(v[1],v[2],v[3],v[4],128) end
  gl.LineWidth(1)
  gl.DepthTest(false)
  gl.Color(1,1,1,1)
end
local s=widget.DrawScreen
function widget:DrawScreen()
  s(self)
  if #n==0 or not p() or Spring.IsGUIHidden() then return end
  local a,b=Spring.GetViewGeometry()
  for _,v in ipairs(n) do
    local x,y,z=Spring.WorldToScreenCoords(v[1],v[2]+45,v[3])
    if x and z and z>0 and z<1 and x>=0 and x<=a and y>=0 and y<=b then
      local w='AMMO: '..(v[5]~=nil and tostring(v[5]) or '?')
      gl.Color(1,0.9,0.25,1)
      gl.Text(w,x,y+14,14,'oc')
    end
  end
  gl.Color(1,1,1,1)
end

-- Income values come exclusively from the resident C++ snapshot.
local t={}
local allyColors,colorsAt={},-100
local function incomeReference()
  local spec=Spring.GetSpectatingState()
  if spec then
    if WG and WG.AirRaidOP and WG.AirRaidOP.GetWatchedPlayer then
      local _,team,name=WG.AirRaidOP.GetWatchedPlayer()
      if team~=nil and Spring.GetTeamInfo then
        local _,_,_,_,_,ally=Spring.GetTeamInfo(team,false)
        return ally,name,true
      end
    end
    return nil,nil,true
  end
  return Spring.GetMyAllyTeamID and Spring.GetMyAllyTeamID(),nil,false
end
local function v()
  local a=Spring.GetSpectatingState and Spring.GetSpectatingState()
  return g and (f or a)
end
local w=widget.Update
function widget:Update(dt)
  w(self,dt)
  t=(v() and c-incomeAt<=4) and incomeRows or {}
  if c-colorsAt>=1 then
    colorsAt=c;allyColors={}
    if Spring.GetTeamList and Spring.GetTeamColor then
      for _,row in ipairs(t) do
        local colors={};allyColors[row.id]=colors
        for _,team in ipairs(Spring.GetTeamList(row.id) or {}) do
          if not Spring.GetGaiaTeamID or team~=Spring.GetGaiaTeamID() then
            local r,g,b=Spring.GetTeamColor(team)
            if r and g and b then colors[#colors+1]={r,g,b} end
          end
        end
      end
    end
  end
end
local function x(a)
  if a>=1000000 then return string.format('%.2fM',a/1000000) end
  if a>=1000 then return string.format('%.1fk',a/1000) end
  return string.format('%.0f',a)
end
local y=widget.DrawScreen
function widget:DrawScreen()
  y(self)
  if not v() or #t==0 or Spring.IsGUIHidden() then return end
  local a,b=Spring.GetViewGeometry()
  local c=math.max(8,a-290);local d=b-112
  local reference,name,spec=incomeReference()
  gl.Color(.06,.09,.11,.88);gl.Rect(c,d-4-#t*25,a-10,d)
  for i,j in ipairs(t) do
    local k=d-i*25+8
    local label=reference==nil and 'Ally ' or (reference==j.id and (spec and 'ALLY ' or 'MY ') or 'OPP ')
    gl.Color(.85,.9,1,1);gl.Text(label..j.id,c+8,k,12,'o')
    local colors=allyColors[j.id] or {}
    for n,color in ipairs(colors) do
      gl.Color(color[1],color[2],color[3],1)
      gl.Rect(c+6+(n-1)*54/#colors,k-4,c+6+n*54/#colors,k-2)
    end
    gl.Color(.8,.85,.95,1);gl.Text('M '..(j.ok and x(j.m) or '--')..'/s',c+88,k,12,'o')
    gl.Color(1,.85,.2,1);gl.Text('E '..(j.ok and x(j.e) or '--')..'/s',c+185,k,12,'o')
  end
  gl.Color(1,1,1,1)
end
