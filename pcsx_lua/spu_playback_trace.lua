-- SPU Playback Trace -- PCSX-Redux Lua tracer.
--
-- See docs/audio/SPU_PLAYBACK_TRACE.md for the full methodology, why
-- this exists, and how to run the "critical experiment" (load save
-- slot 9, arm this script, play, press the marker key ONCE when the
-- target dialogue STARTS (TARGET_BEGIN) and ONCE AGAIN when it ENDS
-- (TARGET_END), stop, analyze with `python -m gcrts.spu_trace_analyzer`).
--
-- HOW TO LOAD: Debug > Lua Editor (or Lua Console) > open this file >
-- Run. PCSX-Redux prints "SPU Playback Trace armed: ..." via
-- PCSX.log() once every breakpoint/listener is set up.
--
-- WHERE THE OUTPUT GOES: TRACE_PATH below, relative to PCSX-Redux's
-- own working directory (this project launches it from the repo root,
-- alongside pcsx.json / SLPS00102.sstate* / memcard1.mcd -- the trace
-- file should land in the same place). Change TRACE_PATH to an
-- absolute path if that assumption is wrong for your setup.
--
-- API USAGE NOTE: every PCSX.* / PCSX.Events.* call in this script is
-- taken directly from this project's own read of PCSX-Redux's real
-- FFI source (src/core/pcsxffi.lua's `ffi.cdef` block and
-- src/core/eventslua.cc's `createEventListener` dispatch table),
-- fetched fresh this session -- not from memory or paraphrased
-- documentation. It has NOT been live-tested inside a running
-- PCSX-Redux instance yet (this project's tooling cannot load/run a
-- Lua script into the GUI on its own -- that is a real user action).
-- If PCSX.log() output or the trace file looks wrong the first time
-- this runs, that is expected-possible, not a sign of a deeper
-- problem -- check the MARK_CANDIDATE diagnostic log lines first (see
-- below).

local TRACE_PATH = "spu_playback_trace.jsonl"

-- GLFW_KEY_F9, assumed (see docs/audio/SPU_PLAYBACK_TRACE.md "marker
-- key verification" section). If pressing F9 during a real session
-- does NOT produce a "SPU Playback Trace: MARK recorded" message in
-- the PCSX-Redux Lua console/log, check the console for
-- "keyboard event: key=<N> action=<N>" lines (logged for every real
-- keypress below) and update MARK_KEY to the real value observed.
local MARK_KEY = 298
local MARK_ACTION_PRESS = 1 -- GLFW_PRESS, assumed

local file = io.open(TRACE_PATH, "a")
if not file then
    printError("SPU Playback Trace: could not open " .. TRACE_PATH .. " for writing -- check TRACE_PATH")
end

local start_clock = os.clock()
local function now()
    return os.clock() - start_clock
end

-- Minimal, hand-rolled JSON line encoder -- avoids depending on a Lua
-- JSON library that may not be loaded in this sandbox. Only needs to
-- handle the flat {string: number|string|boolean|nil} tables this
-- script itself builds, not general JSON.
local function write_json(tbl)
    if not file then
        return
    end
    local parts = {}
    for k, v in pairs(tbl) do
        local vs
        if type(v) == "string" then
            vs = string.format("%q", v)
        elseif type(v) == "boolean" then
            vs = tostring(v)
        elseif v == nil then
            vs = "null"
        else
            vs = tostring(v)
        end
        table.insert(parts, string.format('"%s":%s', k, vs))
    end
    file:write("{" .. table.concat(parts, ",") .. "}\n")
    file:flush()
end

-- ==== Writer-site breakpoints ====
-- Addresses are gcrts.spu_audio_path's own already-verified
-- SPUCNT_WRITER_SITES / KEY_WRITER_SITES constants, copied here (not
-- re-derived) so this script and the Python side never drift apart --
-- if you change one, change the other and re-run
-- tests/test_spu_playback_trace.py's cross-check.
local WRITER_SITES = {
    { pc = 0x80081BB8, register = "SPUCNT", family = "CD_INIT" },
    { pc = 0x8008E75C, register = "SPUCNT", family = "GENERIC_SPU_DRIVER" },
    { pc = 0x800866A8, register = "KEY_ON", family = "PERIODIC_VOICE_SYNC" },
    { pc = 0x800866A0, register = "KEY_OFF", family = "PERIODIC_VOICE_SYNC" },
    { pc = 0x8008E9D8, register = "KEY_ON", family = "GENERIC_SPU_DRIVER" },
    { pc = 0x8008E934, register = "KEY_OFF", family = "GENERIC_SPU_DRIVER" },
    { pc = 0x8008EB84, register = "KEY_OFF", family = "GENERIC_SPU_DRIVER" },
}

local breakpoints = {}

for _, site in ipairs(WRITER_SITES) do
    local bp = PCSX.addBreakpoint(site.pc, "Exec", 4, "spu_playback_trace", function(address, width, cause)
        -- $a0 at the exact write instruction: the SAME evidence class
        -- this project's own GDB-based captures already used
        -- successfully for the Key ON/OFF sites (see
        -- gcrts.spu_audio_path's LIVE_CORRELATION_RUNS). SPUCNT's own
        -- calling convention was only established via static
        -- disassembly before now (never independently re-verified via
        -- a live register read at this exact PC) -- assumed
        -- consistent with the Key sites' convention, flagged here so
        -- a reader knows this specific field is a slightly weaker
        -- claim than the Key ON/OFF one.
        local regs = PCSX.getRegisters()
        local a0 = regs.GPR.n.a0
        local pc = regs.pc
        if site.register == "SPUCNT" then
            write_json({ event = "SPUCNT_WRITE", t = now(), write_pc = site.pc, value = tonumber(a0), cpu_pc = tonumber(pc) })
        else
            write_json({
                event = "SPU_KEY_WRITE", t = now(), write_pc = site.pc, family = site.family,
                register = site.register, voice_mask = tonumber(a0), cpu_pc = tonumber(pc),
            })
        end
        return false -- do NOT call PCSX.pauseEmulator(); just log and let execution continue
    end, site.register .. "@" .. string.format("0x%08X", site.pc))
    table.insert(breakpoints, bp)
end

-- ==== CD-ROM command-write sites ====
-- Addresses are gcrts.cdrom_setfilter's own already-live-confirmed call
-- sites (SETFILTER_CALL_SITE_ADDR, OTHER_COMMAND_WRITE_SITES) plus
-- gcrts.cdrom_driver_map's COMMAND_ISSUE_ROUTINE_ADDR -- not re-derived,
-- copied here the same way WRITER_SITES is. At each, $v0 was already
-- confirmed (via an earlier static scan, not guessed) to hold the
-- command byte about to be written to the real hardware command
-- register. $a0/$a1 are also captured raw (often a parameter count and
-- a pointer to the parameter buffer, per the Setfilter capture that
-- established this call site -- see that module's own docstring) but
-- are not dereferenced here (this script never reads beyond the CPU's
-- own registers into an arbitrary pointed-to buffer, to keep the
-- in-process hook simple and safe).
local CD_COMMAND_SITES = { 0x8008182C, 0x80081AC8, 0x80081C2C, 0x80081C00 }

for _, pc in ipairs(CD_COMMAND_SITES) do
    local bp = PCSX.addBreakpoint(pc, "Exec", 4, "spu_playback_trace", function(address, width, cause)
        local regs = PCSX.getRegisters()
        write_json({
            event = "CD_COMMAND", t = now(), call_site_addr = pc,
            command_byte = tonumber(regs.GPR.n.v0), a0 = tonumber(regs.GPR.n.a0), a1 = tonumber(regs.GPR.n.a1),
            cpu_pc = tonumber(regs.pc),
        })
        return false
    end, "CD_CMD@" .. string.format("0x%08X", pc))
    table.insert(breakpoints, bp)
end

-- ==== Heartbeat: per-vsync snapshot of the already-known, already- ====
-- ==== reliable CD-audio-lifecycle CPU RAM fields (main RAM only,   ====
-- ==== never an SPU MMIO read)                                      ====

local mem = PCSX.getMemPtr()

local function ram_offset(addr)
    return bit.band(addr, 0x1FFFFF) -- KUSEG/KSEG0/KSEG1 mirror -> physical RAM offset, same masking gcrts.runtime_visual_provider._ram_slice already uses
end

local function read_u8(addr)
    return mem[ram_offset(addr)]
end

local function read_u32_le(addr)
    local b = ram_offset(addr)
    return mem[b] + mem[b + 1] * 256 + mem[b + 2] * 65536 + mem[b + 3] * 16777216
end

-- gcrts.runtime_audio's own already-verified addresses (STATE_PAIR_ADDR,
-- POSITION_ADDR, LAST_REQ_PARAMS_ADDR) -- copied here, not re-derived.
local STATE_PAIR_ADDR = 0x800A6106
local POSITION_ADDR = 0x800A61AC
local LAST_REQ_PARAMS_ADDR = 0x800A6114

local heartbeat_listener = PCSX.Events.createEventListener("GPU::Vsync", function()
    write_json({
        event = "HEARTBEAT",
        t = now(),
        position_counter = tonumber(read_u32_le(POSITION_ADDR)),
        lifecycle_state_raw = tonumber(read_u8(STATE_PAIR_ADDR + 1)), -- the SECOND byte carries lifecycle info, see gcrts.runtime_audio
        last_req_params = tonumber(read_u32_le(LAST_REQ_PARAMS_ADDR)),
    })
end)

-- ==== Save-state-loaded anchor (the already-observed "t=0.0s" pattern) ====

local savestate_listener = PCSX.Events.createEventListener("ExecutionFlow::SaveStateLoaded", function()
    write_json({ event = "SAVE_STATE_LOADED", t = now() })
end)

-- ==== User marker: TARGET_BEGIN / TARGET_END, alternating ====
-- This is PCSX-Redux's own application receiving a real physical
-- keypress -- NOT an attempt to inject input into the emulated game
-- controller (already confirmed broken, see
-- gcrts.pcsx_spu_observer.synthetic_input_reaches_game_controller()).
-- Every real keypress is logged as a diagnostic PCSX.log() line (not
-- written into the JSONL trace -- that schema only recognizes the 5
-- event types gcrts.spu_playback_trace defines) so the marker key can
-- be verified/corrected without guessing.
--
-- The SAME key (MARK_KEY) is pressed twice per line: once when the
-- target line STARTS, once when it ENDS. This toggle alternates the
-- label every press so a single continuous trace naturally supports
-- repeated runs (BEGIN/END/BEGIN/END/...) without reloading the
-- script between attempts -- press it an odd number of times total in
-- one session and the LAST marker is a dangling BEGIN with no
-- matching END; gcrts.spu_trace_analyzer's target_windows() reports
-- this explicitly rather than guessing a pairing.
local next_mark_is_begin = true

local keyboard_listener = PCSX.Events.createEventListener("Keyboard", function(e)
    PCSX.log("SPU Playback Trace: keyboard event key=" .. tostring(e.key) .. " action=" .. tostring(e.action))
    if e.key == MARK_KEY and e.action == MARK_ACTION_PRESS then
        local label = next_mark_is_begin and "TARGET_BEGIN" or "TARGET_END"
        write_json({ event = "MARK", t = now(), label = label })
        PCSX.log("SPU Playback Trace: MARK " .. label .. " recorded at t=" .. tostring(now()))
        next_mark_is_begin = not next_mark_is_begin
    end
end)

PCSX.log(
    "SPU Playback Trace armed: "
        .. #breakpoints
        .. " breakpoints, heartbeat + save-state + marker listeners active. Writing to "
        .. TRACE_PATH
        .. ". Press the marker key (default F9) when the target dialogue is heard."
)
