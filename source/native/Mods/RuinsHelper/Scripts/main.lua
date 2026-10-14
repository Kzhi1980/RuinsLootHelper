-- SPDX-License-Identifier: MIT
-- Local JSON mailbox, no arbitrary command evaluation or OS input injection.
local json = require("json")
local adapter = require("game")
local engine = require("core").new(adapter)
local folder = (os.getenv("LOCALAPPDATA") or "") .. "/RuinsLootHelper/"
local function read_request()
    local file = io.open(folder.."native-request.json", "rb")
    if not file then return nil end
    local text = file:read(1048576)
    file:close()
    local ok, request = pcall(json.decode, text)
    return ok and type(request)=="table" and request or nil
end
local function publish(value)
    value.protocol, value.utc = 4, os.time()
    local ok, text = pcall(json.encode, value)
    if not ok then return end
    local temp = folder.."native-status.tmp"
    local file = io.open(temp, "wb")
    if not file then return end
    file:write(text); file:close()
    os.remove(folder.."native-status.json")
    os.rename(temp, folder.."native-status.json")
end
pcall(publish, {ready=false, state="loaded_waiting_for_helper"})
-- UE4SS async Lua callbacks share the VM with game-thread callbacks. Keep the
-- mailbox, Lua state and UObject work on one thread, with one outstanding tick.
if type(ExecuteInGameThreadWithDelay)~="function" then
    pcall(publish, {ready=false, state="adapter_error",
        error="Game-thread timer unavailable; update the bundled game component."})
    return
end
local function tick()
    local request = {}
    local ok, result = pcall(function()
        -- A missing or malformed mailbox must still expire native features.
        request = read_request() or {}
        return engine:step(request, request.monotonic or 0, os.time())
    end)
    if not ok then
        if adapter.stop_bagua then pcall(function() adapter:stop_bagua() end) end
        if adapter.stop_comfort then pcall(function() adapter:stop_comfort() end) end
        result = {ready=false, state="adapter_error", error=tostring(result)}
    end
    result.session, result.game_pid = request.session, request.game_pid
    -- A transient status-file failure must not stop future cleanup/ticks.
    pcall(publish, result)
    ExecuteInGameThreadWithDelay(50, tick)
end
ExecuteInGameThreadWithDelay(50, tick)
