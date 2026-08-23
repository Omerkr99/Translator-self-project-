-- Precision RAM capture triggered by CD_init firing, instead of manual
-- real-time timing. See docs/audio/SPU_AUDIO_PATH_DISCOVERY.md for the
-- CD_init function itself (0x80081B04-0x80081BCC, identified via its
-- own debug string "CD_init:addr=%08x\n").
--
-- IMPORTANT, already-documented caveat: a prior milestone's own live
-- correlation experiment found CD_init did NOT fire during a separately
-- confirmed-audible dialogue window (0/6 armed sites hit). This script
-- is being armed again anyway, per direct instruction, because that
-- prior negative result was for a different capture session -- this is
-- a fresh, honest re-test, not an assumption that it will work.
--
-- HOW TO USE:
--   dofile("pcsx_lua/dump_ram.lua")
--   dofile("pcsx_lua/cd_init_trigger_dump.lua")
--   dump_ram("run04_before.bin")   -- manual, ~1-2s before triggering the line
--   -- ... trigger the dialogue (advance through the scene) ...
--   -- the breakpoint below auto-dumps "cdinit_trigger_NN.bin" every
--   -- time CD_init fires, with zero manual timing guesswork, and does
--   -- NOT pause the emulator (invoker returns false -> execution
--   -- continues immediately)
--   -- ... after the line finishes ...
--   dump_ram("run04_after.bin")

-- 0x80081BB8 is the specific SPUCNT-write instruction inside CD_init,
-- already confirmed to actually fire live in gcrts.spu_audio_path's own
-- captures (see pcsx_lua/spu_playback_trace.lua's WRITER_SITES table) --
-- NOT the same as the function's rough 0x80081B04 start address, which
-- this script used first and never fired.
local CD_INIT_ADDR = 0x80081BB8
local fire_count = 0

local function onCdInit()
    fire_count = fire_count + 1
    local fname = string.format("cdinit_trigger_%02d.bin", fire_count)
    dump_ram(fname)
    PCSX.log("CD_init fired (#" .. fire_count .. ") -- dumped " .. fname .. "\n")
    return false -- do not pause; let execution continue immediately
end

PCSX.addBreakpoint(CD_INIT_ADDR, "Exec", 4, "CD_init trigger", onCdInit, "cd_init_dump_trigger")
PCSX.log("Armed: CD_init breakpoint at 0x80081BB8 -- will auto-dump RAM (cdinit_trigger_NN.bin) every time it fires.\n")
