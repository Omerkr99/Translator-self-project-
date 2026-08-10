-- Observational PCSX-Redux probe for GCRTS runtime asset lifecycle research.
-- Load from Debug > Show Lua Console with: dofile([[C:/Users/טופז/starter-project/gcrts_runtime_probe.lua]])
if GCRTSRuntimeProbe then
  if GCRTSRuntimeProbe.decode then GCRTSRuntimeProbe.decode:remove() end
  if GCRTSRuntimeProbe.vsync then GCRTSRuntimeProbe.vsync:remove() end
  if GCRTSRuntimeProbe.reset then GCRTSRuntimeProbe.reset:remove() end
  if GCRTSRuntimeProbe.timwrite then GCRTSRuntimeProbe.timwrite:remove() end
  if GCRTSRuntimeProbe.otroot then GCRTSRuntimeProbe.otroot:remove() end
  for _,bp in pairs(GCRTSRuntimeProbe.returns or {}) do bp:remove() end
end
local Probe = { frame = 0, events = {}, returns = {}, fileIndex = 1, flushPending = false }
local mem = PCSX.getMemPtr()
local eventPath = 'C:/tmp/gcrts-runtime-events.tsv'
local initialFile = assert(io.open(eventPath,'w'));initialFile:close()

local function ram(address) return bit.band(address, 0x001fffff) end
local function u16(address) local p=ram(address); return mem[p] + mem[p+1]*256 end
local function u32(address) return u16(address) + u16(address+2)*65536 end
local function s16(v) v=bit.band(v,0xffff);if v>=0x8000 then return v-0x10000 end;return v end
local function prefix(address,count)
  local out={};local p=ram(address)
  for i=0,count-1 do out[#out+1]=string.format('%02x',mem[p+i]) end
  return table.concat(out)
end
local function compressedSize(address)
  local p=ram(address);local start=p
  while p<0x200000 do
    local c=mem[p];p=p+1
    if c==0xff then return p-start end
    if c<0x80 then p=p+c+1 elseif c<0xc0 then p=p+1 elseif c<0xf0 then p=p+2 else return 0 end
  end
  return 0
end
local function timSize(address)
  if u32(address)~=0x10 then return 0 end
  local flags=u32(address+4);local pos=8
  if bit.band(flags,8)~=0 then local n=u32(address+pos);if n<12 or n>0x100000 then return 0 end;pos=pos+n end
  local n=u32(address+pos);if n<12 or n>0x100000 then return 0 end
  return pos+n
end
local function emit(e)
  Probe.events[#Probe.events+1]=e
  if #Probe.events>2048 then table.remove(Probe.events,1) end
end
local function flushEvents()
  Probe.flushPending=false
  if Probe.fileIndex>#Probe.events then return end
  local file=io.open(eventPath,'a');if not file then return end
  for i=Probe.fileIndex,#Probe.events do local e=Probe.events[i];file:write(string.format('%s\t%d\t%08x\t%d\t%s\t%08x\t%d\t%08x\n',e.kind,e.frame,e.source_ptr,e.compressed_size,e.compressed_prefix,e.decoded_ptr,e.decoded_size,e.caller)) end
  Probe.fileIndex=#Probe.events+1;file:close()
end
Probe.vsync=PCSX.Events.createEventListener('GPU::Vsync',function()
  Probe.frame=Probe.frame+1
  if not Probe.flushPending then Probe.flushPending=true;PCSX.nextTick(flushEvents) end
end)
Probe.reset=PCSX.Events.createEventListener('ExecutionFlow::Reset',function() Probe.events={};Probe.returns={};Probe.frame=0 end)
if PCSX.WebServer and PCSX.WebServer.Handlers then
  PCSX.WebServer.Handlers['gcrts/runtime-events']=function()
    local lines={};for _,e in ipairs(Probe.events) do lines[#lines+1]=string.format('%s\t%d\t%08x\t%d\t%s\t%08x\t%d\t%08x',e.kind,e.frame,e.source_ptr,e.compressed_size,e.compressed_prefix,e.decoded_ptr,e.decoded_size,e.caller) end
    return table.concat(lines,'\n')
  end
end
GCRTSRuntimeProbe=Probe
print('GCRTS Lua breakpoint probe is disabled; runtime tracking uses validated external RAM/VRAM snapshots.')
