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

-- ==== Baseline-safe mode ====
-- LIVE-DISCOVERED CORRECTION (see gcrts.overlay_identity's own module
-- docstring): this game loads at least 15 different .EXE overlays
-- that reuse overlapping address ranges. The 11 writer-site
-- breakpoints below were validated against ONE of them -- and it
-- turns out that one is NOT literally "PROG.EXE" (PROG.EXE's own
-- range ends at 0x8006a800, before any of these addresses even
-- begin) but one of the CAP*.EXE variants. When a DIFFERENT overlay
-- (e.g. CAP0.EXE, or the movie-player family) is the one actually
-- resident, these same addresses hold that overlay's own, different
-- code -- arming Exec breakpoints there is meaningless at best and
-- has been observed to correlate with real instability at worst.
--
-- SAFE_BASELINE_ONLY = true arms ONLY overlay-independent
-- instrumentation (heartbeat, marker, save-state event, executable
-- identity detection) -- no fixed-address breakpoints at all. Use
-- this to get a first clean, stable trace of a target line before
-- trusting any Key ON/OFF or CD-command evidence. Set to false only
-- once EXECUTABLE_ACTIVE events (see below) have confirmed the
-- currently-resident overlay actually matches the one these 11
-- addresses were validated against.
local SAFE_BASELINE_ONLY = true

-- Live-observed this session: with the executable-identity check
-- running every 60 frames (see KNOWN_OVERLAYS/identify_overlay
-- below), the heartbeat listener reliably stopped writing after a
-- few real seconds while the game itself kept running and a FRESH,
-- separately-created vsync listener (created live via the Lua
-- Console) kept counting normally -- proof the event-dispatch system
-- itself was healthy and the failure was specific to this listener's
-- own closure. Manually running the exact same signature-read logic
-- once via the console succeeded with no error, so the fault is most
-- likely cumulative (e.g. GC pressure from allocating 11 new
-- tables/strings every second) rather than a one-shot exception.
-- Disabled here (not deleted) until that's root-caused -- the
-- heartbeat/marker/save-state baseline alone has been the reliable
-- part throughout.
local CHECK_EXECUTABLE_IDENTITY = false

-- Live-tested this session: F9 (298) and other keys pressed while the
-- game viewport has focus never reach this "Keyboard" event listener
-- at all (0 log lines) -- this build only appears to forward key
-- events tied to the Lua Console/Editor's OWN text-input handling.
-- Enter (257) DID reach this listener once, with action=0 (NOT
-- GLFW_PRESS=1 as assumed) -- empirically observed, not derived from
-- the GLFW header. Using that confirmed-working combination: press
-- Enter inside the Lua Console (an empty line is fine) to mark.
local MARK_KEY = 257
local MARK_ACTION_PRESS = 0 -- empirically observed value for Enter in this build, not GLFW_PRESS

local file = io.open(TRACE_PATH, "a")
if not file then
    printError("SPU Playback Trace: could not open " .. TRACE_PATH .. " for writing -- check TRACE_PATH")
end

-- os.clock() was found (live) to NOT track wall-clock time in this
-- embedded LuaJIT context -- after a real, measured 20 real-world
-- seconds, os.clock()-based elapsed time showed only ~1.5s, a >12x
-- discrepancy. Most likely os.clock() only accumulates actual Lua-VM
-- CPU time, which is a few microseconds per vsync callback -- nearly
-- nothing compared to the real wall-clock time the emulator spends
-- rendering/running the game between callbacks. Using a vsync FRAME
-- COUNT instead, divided by the real NTSC display rate (60 Hz for
-- this US/SCPH-1001 BIOS build), tracks real elapsed time far more
-- faithfully since it advances once per actual displayed frame,
-- regardless of how little Lua-VM CPU time each callback itself uses.
local VSYNC_HZ = 60.0
local frame_count = 0
local function now()
    return frame_count / VSYNC_HZ
end

-- Minimal, hand-rolled JSON line encoder -- avoids depending on a Lua
-- JSON library that may not be loaded in this sandbox. Only needs to
-- handle the flat {string: number|string|boolean|nil} tables this
-- script itself builds, not general JSON.
-- Live-observed pattern (multiple sessions, both with and without the
-- overlay-dependent breakpoints armed -- so it is NOT those
-- breakpoints causing it): the trace file reliably stops growing
-- after a few real seconds even though the game itself keeps running.
-- Defensive fix: if a write ever fails (file:write returning a falsy
-- success value, which the plain Lua io library does on a genuine I/O
-- error), try to reopen TRACE_PATH once and retry -- guards against
-- some external process (antivirus, indexer, etc.) transiently
-- locking a file this script re-writes 10+ times per second.
local write_failure_count = 0
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
    local line = "{" .. table.concat(parts, ",") .. "}\n"
    local ok = file:write(line)
    if not ok then
        write_failure_count = write_failure_count + 1
        PCSX.log("SPU Playback Trace: write failed (" .. tostring(write_failure_count) .. " total) -- reopening " .. TRACE_PATH)
        file = io.open(TRACE_PATH, "a")
        if file then
            file:write(line)
        end
    end
    if file then
        file:flush()
    end
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

if not SAFE_BASELINE_ONLY then
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

if not SAFE_BASELINE_ONLY then
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

-- ==== Overlay/executable identity ====
-- gcrts.overlay_identity's own already-established real signatures --
-- copied here, not re-derived (see that module's docstring: this
-- game loads at least 15 different .EXE overlays reusing overlapping
-- address ranges; the 11 writer-site breakpoints above are only
-- meaningful while an overlay that actually matches their own
-- validation context is resident). Checked once per second (not every
-- frame) to keep this cheap; an EXECUTABLE_ACTIVE event is written
-- ONLY when the detected identity actually changes, never every check.
local KNOWN_OVERLAYS = {
    { name = "PROG.EXE", pc0 = 0x8004718C, sig = "07801c3c50a69c27280f010800000000" },
    { name = "CAP0.EXE", pc0 = 0x80077D18, sig = "0a801c3ce03b9c27f1d1010800000000" },
    { name = "CAP1.EXE", pc0 = 0x8007431C, sig = "0a801c3ce4289c2772c3010800000000" },
    { name = "CAP2.EXE", pc0 = 0x80070034, sig = "0a801c3cdce79c27b8b2010800000000" },
    { name = "CAP3.EXE", pc0 = 0x8007599C, sig = "0a801c3cf4369c2712c9010800000000" },
    { name = "CAP4.EXE", pc0 = 0x80074398, sig = "0a801c3c8c369c2791c3010800000000" },
    { name = "CAPX.EXE", pc0 = 0x80067E08, sig = "09801c3c44339c272d92010800000000" },
    { name = "MPRO.EXE (or MYOKO.EXE)", pc0 = 0x80102654, sig = "13801c3c40c19c27f103040800000000" },
    { name = "MKUBI.EXE (or MNINO.EXE/MRIKA.EXE)", pc0 = 0x80102680, sig = "13801c3c6cc19c27fc03040800000000" },
    { name = "MOP.EXE", pc0 = 0x801026CC, sig = "13801c3c08c29c270f04040800000000" },
    { name = "MOVER.EXE", pc0 = 0x80102658, sig = "13801c3c44c19c27f203040800000000" },
}
local SIGNATURE_LENGTH = 16

local function read_signature_hex(addr)
    local b = ram_offset(addr)
    local parts = {}
    for i = 0, SIGNATURE_LENGTH - 1 do
        table.insert(parts, string.format("%02x", mem[b + i]))
    end
    return table.concat(parts)
end

local function identify_overlay()
    for _, profile in ipairs(KNOWN_OVERLAYS) do
        if read_signature_hex(profile.pc0) == profile.sig then
            return profile.name
        end
    end
    return nil
end

local last_known_overlay = nil -- sentinel distinct from nil/false so the FIRST real check always logs
local overlay_checked_once = false

-- ==== Fixed-duration auto-recording window ====
-- Simplest possible workflow: no manual marker needed at all. The
-- window is exactly [0, RECORDING_DURATION] seconds from script load
-- -- printed clearly at start and end so it's obvious in the log
-- exactly what got captured and when, without the user needing to
-- press anything.
local RECORDING_DURATION = 20.0
local recording_finished_announced = false

PCSX.log("SPU Playback Trace: RECORDING STARTED -- capturing for " .. tostring(RECORDING_DURATION) .. "s, starting now (t=0.0). Play normally; no marker key needed.")

-- Live-observed: writing on EVERY vsync (60 Hz) correlated with the
-- trace reliably stopping after a few real seconds, in multiple
-- sessions, independent of which breakpoints were armed. Writing at
-- 10 Hz instead (every 6th frame) cuts real file I/O by 6x while
-- still resolving position/lifecycle-state changes far faster than
-- they actually occur -- a defensive reduction in I/O pressure, not a
-- claim about the exact root cause.
local HEARTBEAT_EVERY_N_FRAMES = 6

local heartbeat_listener = PCSX.Events.createEventListener("GPU::Vsync", function()
    frame_count = frame_count + 1
    local t = now()
    if frame_count % HEARTBEAT_EVERY_N_FRAMES == 0 then
        write_json({
            event = "HEARTBEAT",
            t = t,
            position_counter = tonumber(read_u32_le(POSITION_ADDR)),
            lifecycle_state_raw = tonumber(read_u8(STATE_PAIR_ADDR + 1)), -- the SECOND byte carries lifecycle info, see gcrts.runtime_audio
            last_req_params = tonumber(read_u32_le(LAST_REQ_PARAMS_ADDR)),
        })
    end
    if CHECK_EXECUTABLE_IDENTITY and (frame_count % 60 == 0 or not overlay_checked_once) then
        overlay_checked_once = true
        local current_overlay = identify_overlay()
        if current_overlay ~= last_known_overlay then
            write_json({ event = "EXECUTABLE_ACTIVE", t = t, name = current_overlay })
            PCSX.log("SPU Playback Trace: EXECUTABLE_ACTIVE = " .. tostring(current_overlay) .. " at t=" .. tostring(t))
            last_known_overlay = current_overlay
        end
    end
    if not recording_finished_announced and t >= RECORDING_DURATION then
        recording_finished_announced = true
        write_json({ event = "MARK", t = t, label = "RECORDING_FINISHED" })
        PCSX.log("SPU Playback Trace: RECORDING FINISHED -- " .. tostring(RECORDING_DURATION) .. "s elapsed (t=" .. tostring(t) .. "). You can now run: python -m gcrts.spu_trace_analyzer spu_playback_trace.jsonl")
    end
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
    "SPU Playback Trace armed ("
        .. (SAFE_BASELINE_ONLY and "SAFE_BASELINE_ONLY=true, overlay-independent instrumentation only" or "full mode")
        .. "): "
        .. #breakpoints
        .. " breakpoints, heartbeat + save-state + marker + executable-identity listeners active. Writing to "
        .. TRACE_PATH
        .. ". Press the marker key (default F9) when the target dialogue is heard."
)
