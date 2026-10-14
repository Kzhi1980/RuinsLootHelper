"""Run the real Lua mailbox loop with a controlled game-thread scheduler."""
from pathlib import Path
import unittest
from lupa.lua54 import LuaRuntime


class NativeMainTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().json = self.lua.execute(
            Path('native/Mods/RuinsHelper/Scripts/json.lua').read_text(encoding='utf-8'))
        self.main = Path('native/Mods/RuinsHelper/Scripts/main.lua').read_text(encoding='utf-8')
        self.lua.execute('''
            timers={};background={};phase='startup';steps=0;stops=0;bad_thread=0
            request_text='{"protocol":4,"session":"test","game_pid":123,"monotonic":1}'
            latest=nil;fail_step=false;fail_write=false;fail_read=false
            adapter={stop_comfort=function() stops=stops+1 end}
            engine={step=function(_,req)
                if phase~='game' then bad_thread=bad_thread+1 end
                steps=steps+1;last_request=req
                if fail_step then error('engine failure') end
                return {ready=req.protocol==4,state=req.protocol==4 and 'ready' or 'helper_offline'}
            end}
            package.loaded.json=json
            package.loaded.game=adapter
            package.loaded.core={new=function() return engine end}
            io.open=function(path,mode)
                if phase=='async' then bad_thread=bad_thread+1 end
                if mode=='rb' then
                    if fail_read then error('read failure') end
                    if request_text==nil then return nil end
                    return {read=function() return request_text end,close=function() end}
                end
                return {write=function(_,text)
                    if fail_write then error('write failure') end
                    latest=json.decode(text)
                end,close=function() end}
            end
            os.remove=function() return true end;os.rename=function() return true end
            function ExecuteInGameThreadWithDelay(ms,callback)
                assert(ms>=1);timers[#timers+1]=callback;return #timers
            end
            function LoopAsync(ms,callback) background[#background+1]=callback end
            function ExecuteInGameThread(callback) timers[#timers+1]=callback end
            function tick()
                assert(#timers==1,'exactly one pending game-thread callback required')
                local callback=table.remove(timers,1);phase='game';callback();phase='idle'
            end
        ''')

    def start(self):
        self.lua.execute(self.main)

    def test_mailbox_and_game_calls_use_one_serial_timer(self):
        self.start()
        self.lua.execute('''
            assert(#background==0,'must not register an unsafe asynchronous Lua loop')
            for i=1,200 do tick() end
            assert(steps==200 and #timers==1 and bad_thread==0)
            assert(latest.ready and latest.protocol==4 and latest.session=='test' and latest.game_pid==123)
        ''')

    def test_adapter_error_restores_features_and_keeps_timer_alive(self):
        self.start()
        self.lua.execute('''
            fail_step=true;tick()
            assert(stops==1 and not latest.ready and latest.state=='adapter_error')
            fail_step=false;tick();assert(latest.ready and steps==2 and #timers==1)
        ''')

    def test_missing_malformed_and_scalar_requests_still_expire_features(self):
        self.start()
        self.lua.execute('''
            for _,text in ipairs({'{','null','true','7','"text"'}) do
                request_text=text;tick()
                assert(type(last_request)=='table' and latest.state=='helper_offline')
            end
            request_text=nil;tick();assert(latest.state=='helper_offline' and #timers==1)
        ''')

    def test_read_or_status_write_failure_does_not_kill_future_ticks(self):
        self.start()
        self.lua.execute('''
            fail_read=true;tick();assert(stops==1 and latest.state=='adapter_error')
            fail_read=false;fail_write=true;tick();assert(#timers==1)
            fail_write=false;tick();assert(latest.ready and #timers==1)
        ''')

    def test_unsupported_runtime_does_not_fall_back_to_async(self):
        self.lua.execute('ExecuteInGameThreadWithDelay=nil')
        self.start()
        self.lua.execute('''
            assert(#background==0 and #timers==0 and steps==0)
            assert(not latest.ready and latest.state=='adapter_error')
        ''')


if __name__ == '__main__':
    unittest.main()
