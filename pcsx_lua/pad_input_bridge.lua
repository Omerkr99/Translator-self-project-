-- Pad Input Bridge -- direct, hardware-level controller override,
-- driven by an external Python process through a command file.
--
-- WHY THIS EXISTS: this project spent a long time on OS-level input
-- injection (SendKeys, SendInput, a real vgamepad/ViGEmBus XInput
-- device) and found all of it structurally unreliable against this
-- game -- confirmed via direct A/B test against real physical presses
-- (see docs/tooling/PCSX_REDUX_CAPTURE_PROTOCOL.md sections 8 and 12).
-- This script instead uses PCSX-Redux's OWN Lua-exposed pad override,
-- confirmed directly against the real pcsx-redux source
-- (src/core/pad.cc): `poll()` computes
-- `buttonStatus = pad.buttonStatus & pad.overrides` (line ~811) and
-- packs that value directly into the SIO response bytes the BIOS/game
-- read (~lines 842-871). `setOverride(button)` clears that button's
-- bit in `overrides`, which forces the AND result to 0 for that bit
-- (0 = pressed, PS1's active-low convention) REGARDLESS of real
-- keyboard/gamepad state. `clearOverride(button)` restores passthrough.
-- This never touches GLFW/ImGui/window focus at all, so none of this
-- project's previous input-automation failure modes apply here.
--
-- HOW TO LOAD (one-time per PCSX-Redux launch -- there is no remote
-- Lua-exec HTTP endpoint in this build, confirmed in
-- docs/audio/SPU_OBSERVATION_CHANNEL.md): Debug > Show Lua Console,
-- then:
--   dofile("pcsx_lua/pad_input_bridge.lua")
--
-- COMMAND PROTOCOL: the Python side (gcrts.pcsx_pad_bridge) overwrites
-- COMMAND_PATH with exactly one JSON object per press request:
--   {"id": 3, "button": "CIRCLE", "hold_frames": 8}
-- `id` must strictly increase across requests (a millisecond
-- timestamp is fine). This script polls that file at 10Hz while idle
-- (not every vsync -- continuous per-frame file I/O was already found
-- to correlate with real instability in this same Lua environment,
-- see pcsx_lua/spu_playback_trace.lua's own comments), applies
-- setOverride for exactly `hold_frames` real vsyncs, then
-- clearOverride, then appends one ack line to ACK_PATH:
--   {"id":3,"done":true}
-- so the Python side can block on genuine completion instead of
-- guessing a sleep duration.
--
-- LIVE-CONFIRMED PITFALL (this session): PCSX-Redux's Lua event
-- dispatcher can silently, permanently kill a "GPU::Vsync" listener --
-- same flakiness already documented in spu_playback_trace.lua's own
-- comments ("a fresh vsync listener kept counting normally" while an
-- older one died). The first `dofile` of an early version of this
-- exact script never fired even once (its ack file stayed empty for
-- 7+ real minutes with commands queued and waiting), while a
-- byte-identical replica loaded fresh moments later worked
-- immediately. Wrapping the whole per-frame body in `pcall` (below)
-- does NOT prevent this -- it was added defensively for visibility
-- (writes ERROR_PATH if the body ever throws) but the original dead
-- listener never threw an error either; it just silently stopped
-- being invoked. **If commands stop getting acked mid-session, the
-- fix is to re-run this exact `dofile` line again to get a fresh
-- listener -- don't assume the pad-override mechanism itself is
-- broken.**

local COMMAND_PATH = "pad_input_command.jsonl"
local ACK_PATH = "pad_input_ack.jsonl"
local ERROR_PATH = "pad_input_bridge_error.txt"
local POLL_EVERY_N_FRAMES = 6 -- 10Hz at 60fps NTSC, same throttle spu_playback_trace.lua uses

local pad = PCSX.SIO0.slots[1].pads[1]

local BUTTON_BY_NAME = {
    SELECT = PCSX.CONSTS.PAD.BUTTON.SELECT,
    START = PCSX.CONSTS.PAD.BUTTON.START,
    UP = PCSX.CONSTS.PAD.BUTTON.UP,
    RIGHT = PCSX.CONSTS.PAD.BUTTON.RIGHT,
    DOWN = PCSX.CONSTS.PAD.BUTTON.DOWN,
    LEFT = PCSX.CONSTS.PAD.BUTTON.LEFT,
    L2 = PCSX.CONSTS.PAD.BUTTON.L2,
    R2 = PCSX.CONSTS.PAD.BUTTON.R2,
    L1 = PCSX.CONSTS.PAD.BUTTON.L1,
    R1 = PCSX.CONSTS.PAD.BUTTON.R1,
    TRIANGLE = PCSX.CONSTS.PAD.BUTTON.TRIANGLE,
    CIRCLE = PCSX.CONSTS.PAD.BUTTON.CIRCLE,
    CROSS = PCSX.CONSTS.PAD.BUTTON.CROSS,
    SQUARE = PCSX.CONSTS.PAD.BUTTON.SQUARE,
}

local ack_file = io.open(ACK_PATH, "w")
local function ack(id)
    if not ack_file then
        ack_file = io.open(ACK_PATH, "a")
    end
    if ack_file then
        ack_file:write(string.format('{"id":%d,"done":true}\n', id))
        ack_file:flush()
    end
end

local last_seen_id = 0
local active = nil -- {id=, button=, release_at=}
local frame_count = 0

local function poll_commands()
    local file = io.open(COMMAND_PATH, "r")
    if not file then
        return
    end
    local content = file:read("*a")
    file:close()
    local id = content:match('"id"%s*:%s*(%d+)')
    local name = content:match('"button"%s*:%s*"(%a+)"')
    local hold = content:match('"hold_frames"%s*:%s*(%d+)')
    if not id or not name then
        return
    end
    id = tonumber(id)
    if id <= last_seen_id then
        return
    end
    last_seen_id = id
    local btn = BUTTON_BY_NAME[name]
    if btn == nil then
        PCSX.log("pad_input_bridge: unknown button '" .. tostring(name) .. "' (id=" .. id .. ")")
        ack(id)
        return
    end
    pad.setOverride(btn)
    active = { id = id, button = btn, release_at = frame_count + tonumber(hold or "8") }
    PCSX.log("pad_input_bridge: PRESS " .. name .. " (id=" .. id .. ", hold=" .. tostring(hold or "8") .. " frames)")
end

PCSX.Events.createEventListener("GPU::Vsync", function()
    local ok, err = pcall(function()
        frame_count = frame_count + 1
        if active == nil then
            if frame_count % POLL_EVERY_N_FRAMES == 0 then
                poll_commands()
            end
        elseif frame_count >= active.release_at then
            pad.clearOverride(active.button)
            PCSX.log("pad_input_bridge: RELEASE (id=" .. active.id .. ")")
            ack(active.id)
            active = nil
        end
    end)
    if not ok then
        local f = io.open(ERROR_PATH, "w")
        if f then
            f:write(tostring(err))
            f:close()
        end
    end
end)

PCSX.log("pad_input_bridge armed: watching " .. COMMAND_PATH .. " for hardware-level pad-override commands (bypasses keyboard/window-focus entirely).")
