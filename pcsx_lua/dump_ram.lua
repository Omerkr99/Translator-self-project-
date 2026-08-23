-- Minimal RAM Snapshot Capture -- Phase 1 of the Audio Data Trace
-- milestone (see docs/audio/AUDIO_DATA_TRACE.md).
--
-- Deliberately does almost nothing: no continuous per-frame loop, no
-- vsync listener, no breakpoints. It exists ONLY to be called, once,
-- on explicit user command, at exactly the moment you want a
-- snapshot -- this is the direct lesson from the SPU Playback Trace
-- milestone's own session: continuous 60Hz work inside PCSX-Redux's
-- Lua environment correlated with repeated instability there, while a
-- one-shot dump avoids that whole class of problem entirely.
--
-- HOW TO USE: Debug > Show Lua Console, then call dump_ram() with a
-- filename at exactly the moment you want to capture:
--
--   dofile("pcsx_lua/dump_ram.lua")
--   dump_ram("run01_before.bin")     -- ~1-2s before the target line starts
--   -- ... play until the line is audible, roughly the middle of it ...
--   dump_ram("run01_during.bin")
--   -- ... let the line finish ...
--   dump_ram("run01_after.bin")
--
-- Repeat with run02_*/run03_* filenames for repeated runs (see the
-- milestone's own repeatability requirement -- reproducible regions
-- across runs are much stronger evidence than a single capture).
--
-- WHAT IT CAPTURES: the full 2MB PS1 main RAM window via
-- PCSX.getMemPtr() (confirmed against the real FFI source this
-- project already verified for gcrts.spu_playback_trace -- see that
-- module's own docstring). This is the full range PCSX.getMemPtr()
-- exposes; nothing is excluded. Analyze offline with
-- `python -m gcrts.audio_data_trace`.

RAM_SIZE = 0x200000 -- 2MB, PS1 main RAM

function dump_ram(filename)
    local mem = PCSX.getMemPtr()
    local file = io.open(filename, "wb")
    if not file then
        printError("dump_ram: could not open " .. filename .. " for writing")
        return false
    end
    -- Write in chunks (not one giant string.char call) to avoid
    -- building a single multi-megabyte Lua string in one shot.
    local CHUNK = 65536
    local buf = {}
    for base = 0, RAM_SIZE - 1, CHUNK do
        local n = math.min(CHUNK, RAM_SIZE - base)
        for i = 0, n - 1 do
            buf[i + 1] = string.char(mem[base + i])
        end
        file:write(table.concat(buf, "", 1, n))
    end
    file:close()
    PCSX.log("dump_ram: wrote " .. tostring(RAM_SIZE) .. " bytes to " .. filename)
    return true
end

PCSX.log("dump_ram loaded. Call dump_ram(\"filename.bin\") at the exact moment you want a snapshot.")
