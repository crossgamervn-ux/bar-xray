-- Bounded local mailboxes. No socket dependency; all paths are sandbox-permitted.
local M={}
function M.new(json,channel)
  local base='LuaUI/Config/op_ipc/'
  if Spring.CreateDir then Spring.CreateDir(base) end
  local self={now=0,seq=0,queue={},active={},channel=channel,
    session=tostring(Spring.GetGameFrame())..':'..string.format('%06x%06x%06x%06x',math.random(0,16777215),math.random(0,16777215),math.random(0,16777215),math.random(0,16777215)),nextRead=0}
  local req=base..channel..'.request.json'
  local res=base..channel..'.response.json'
  function self:request(body,callback)
    if #self.queue>=32 then return false end
    self.seq=self.seq+1
    self.queue[#self.queue+1]={id=self.seq,body=body,callback=callback}
    return true
  end
  function self:update(dt)
    self.now=self.now+dt
    if self.batch and self.now>=self.nextRead then
      self.nextRead=self.now+0.001
      local f=io.open(res,'rb')
      if f then
        local raw=f:read(262145);f:close()
        if raw and #raw<=262144 then
          local ok,v=pcall(json.decode,raw)
          if ok and type(v)=='table' and v.session==self.session and v.batch==self.batch then
            local callbacks=self.active;self.active={};self.batch=nil
            for _,r in ipairs(callbacks) do
              local result=v.results and v.results[tostring(r.id)]
              r.callback(type(result)=='table' and result or {ok=false,status='file_bad_response'})
            end
          end
        end
      end
      if self.batch and self.now-self.sentAt>12 then
        local callbacks=self.active;self.active={};self.batch=nil
        for _,r in ipairs(callbacks) do r.callback({ok=false,status='file_timeout'}) end
      end
    end
    if not self.batch and #self.queue>0 then
      local items={}
      for _,r in ipairs(self.queue) do items[#items+1]={id=r.id,body=r.body} end
      local batch=self.queue[#self.queue].id
      local raw=json.encode({version=1,session=self.session,batch=batch,items=items})
      if #raw>262144 then
        local callbacks=self.queue;self.queue={}
        for _,r in ipairs(callbacks) do r.callback({ok=false,status='file_batch_too_large'}) end
        return
      end
      local f=io.open(req..'.tmp','wb')
      if f then
        local ok=f:write(raw);local closed=f:close()
        if ok and closed then
          -- Windows rename may not replace an existing file. A missing-file gap is safe.
          os.remove(req)
          if os.rename(req..'.tmp',req) then
            self.active=self.queue;self.queue={};self.batch=batch;self.sentAt=self.now
          end
        end
      end
    end
  end
  function self:shutdown()
    -- Unload cannot await callbacks. Publish queued cleanup even if an older batch is pending.
    self.batch=nil;self.active={};self:update(0)
  end
  return self
end
return M
