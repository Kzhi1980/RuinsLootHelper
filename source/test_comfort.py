"""Reversible visual changes and host-only native return countdown."""
from pathlib import Path
import unittest
from lupa.lua54 import LuaRuntime
from test_native_game import EngineName


class ComfortTests(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().FName = EngineName
        self.lua.globals().Comfort = self.lua.execute(
            Path('native/Mods/RuinsHelper/Scripts/comfort.lua').read_text(encoding='utf-8'))
        self.lua.execute('''
            next_id=100; scans=0; creations=0; hooks={}; lists={}; invalid_material_calls=0
            function_hooks={}; hook_registrations=0
            function object(path,props)
                next_id=next_id+1;local id=next_id;props=props or {}
                props.GetFullName=function() return path end
                props.GetAddress=function() return id end
                props.IsValid=function() return props.alive~=false end
                return props
            end
            function array(t)
                t.GetArrayNum=function() return #t end
                t.Empty=function() for i=#t,1,-1 do t[i]=nil end end
                return t
            end
            world=object('world')
            player=object('BP_mypawn_C', {authority=true,local_player=true,
                ['回城读条']=5,['服务器正在回城']=false,['已死亡']=false,['移动中']=false})
            player.GetWorld=function() return world end
            player.HasAuthority=function() return player.authority end
            player.IsLocallyControlled=function() return player.local_player end
            function FindAllOf(name) scans=scans+1;return lists[name] or {} end
            function NotifyOnNewObject(name,callback) hooks[name]=callback end
            function RegisterHook(name,callback)
                hook_registrations=hook_registrations+1;function_hooks[name]=callback
                return 1001,1002
            end
            material=object('MaterialInstanceConstant /Game/land/Materials/landscape/MI_landscape_Inst.MI_landscape_Inst')
            original={R=1,G=.9,B=.8,A=1}
            material.K2_GetVectorParameterValue=function(_,name)
                assert(type(name)=='userdata');return original
            end
            proxy=object('LandscapeStreamingProxy map.Landscape', {
                LandscapeMaterial=material,bUseDynamicMaterialInstance=false,bEnableNanite=false})
            props={MaterialInstances=array({material}),MaterialInstancesDynamic=array({}),
                bRenderCustomDepth=false,bNaniteActive=false}
            comp=object('LandscapeComponent map.Landscape.Component',{})
            comp.GetOuter=function() return proxy end
            comp.GetWorld=function() return world end
            comp.SetRenderCustomDepth=function(_,value) props.bRenderCustomDepth=value end
            comp.GetMaterialInstanceDynamic=function(_,index)
                return props.MaterialInstancesDynamic[index+1]
            end
            setmetatable(comp,{__index=props,__newindex=function(_,key,value)
                if key=='MaterialInstancesDynamic' then
                    local copy={};for i,v in ipairs(value) do copy[i]=v end
                    props[key]=array(copy)
                else props[key]=value end
            end})
            lib=object('KismetMaterialLibrary')
            lib.CreateDynamicMaterialInstance=function(_,context,parent,name,flags)
                creations=creations+1
                local mid=object('MaterialInstanceDynamic helper.'..creations,{Parent=parent,color=original})
                mid.K2_GetVectorParameterValue=function()
                    if not mid:IsValid() then invalid_material_calls=invalid_material_calls+1;error('dead material read') end
                    return mid.color
                end
                mid.SetVectorParameterValue=function(_,key,value)
                    if not mid:IsValid() then invalid_material_calls=invalid_material_calls+1;error('dead material write') end
                    assert(type(key)=='userdata' and key:ToString()=='冰color')
                    mid.color=value
                end
                return mid
            end
            function StaticFindObject(path)
                if path=='/Script/Niagara.NiagaraFunctionLibrary:SpawnSystemAtLocation' then
                    return object('Function '..path)
                end
                assert(path=='/Script/Engine.Default__KismetMaterialLibrary');return lib
            end
            fx=object('NiagaraSystem shared.Bear')
            notify=object('AnimNotify_PlayNiagaraEffect /Game/Characters/Mannequin_UE4/Animations/攻击/0旋风斩/旋风斩3.旋风斩3:AnimNotify_PlayNiagaraEffect_0',
                {Template=fx,Scale={X=2,Y=2,Z=1}})
            other=object('AnimNotify_PlayNiagaraEffect /Game/怪物/熊怪/攻击.攻击:AnimNotify_PlayNiagaraEffect_0',{Template=fx,Scale={X=3,Y=3,Z=1}})
            lists.AnimNotify_PlayNiagaraEffect={notify,other}
            lists.LandscapeComponent={comp}
            bridge=Comfort.new()
            req={active=true,fast_return=false,snow_theme='off',whirlwind_mode='off',expires=os.time()+60}
            skill=object('技能组件_C player.技能组件');player['技能组件']=skill
            ground_fx=object('NiagaraSystem /Game/怪物/熊怪/熊冲击粒子.熊冲击粒子')
            moon_fx=object('NiagaraSystem /Game/粒子/0近战/半月.半月')
            auto_moon_fx=object('NiagaraSystem /Game/Hack_And_Slash_FX/VFX_Niagara/Slashes/自动.自动')
            sword_fx=object('NiagaraSystem /Game/Hack_And_Slash_FX/VFX_Niagara/Slashes/剑气.剑气')
            moon_notify=object('AnimNotify_PlayNiagaraEffect /Game/Characters/Mannequin_UE4/Animations/攻击/0半月斩/半月斩范围8.半月斩范围8:AnimNotify_PlayNiagaraEffect_0',
                {Template=moon_fx,Scale={X=3.95,Y=3.95,Z=1}})
            table.insert(lists.AnimNotify_PlayNiagaraEffect,moon_notify)
            function param(value)
                return {value=value,get=function(p) return p.value end,set=function(p,v) p.value=v end}
            end
            function spawn(context,effect,scale)
                local template,size=param(effect),param(scale or {X=3.95,Y=3.95,Z=3.95})
                local callback=function_hooks['/Script/Niagara.NiagaraFunctionLibrary:SpawnSystemAtLocation']
                if callback then
                    callback(param(lib),param(context),template,param({X=0,Y=0,Z=0}),
                        param({Pitch=0,Yaw=0,Roll=0}),size,param(true),param(true),param(0),param(true))
                end
                return template:get(),size:get()
            end
            function step(t) return bridge:step(player,req,t) end
        ''')

    def check(self, code):
        self.lua.execute(code)

    def test_defaults_do_not_scan_or_modify_game(self):
        self.check("for i=1,20 do step(i) end;assert(scans==0 and creations==0 and player['回城读条']==5)")

    def test_host_new_return_shortens_only_native_countdown(self):
        self.check('''
            req.fast_return=true;step(1)
            player['服务器正在回城']=true;player['回城读条']=4;step(1.05)
            assert(player['回城读条']==1)
            player['回城读条']=5;step(2.1)
            player['回城读条']=4;step(3)
            assert(player['回城读条']==1, 'successful return can leave server flag true')
        ''')

    def test_client_or_nonlocal_character_never_shortens(self):
        self.check('''
            req.fast_return=true
            for _,key in ipairs({'authority','local_player'}) do
                bridge=Comfort.new();player[key]=false;player['回城读条']=5;step(1)
                player['服务器正在回城']=true;player['回城读条']=4;step(1.05)
                assert(player['回城读条']==4);player[key]=true
            end
        ''')

    def test_enabling_mid_return_waits_for_next_return(self):
        self.check('''
            req.fast_return=true;player['服务器正在回城']=true;player['回城读条']=4
            step(1);assert(player['回城读条']==4)
        ''')

    def test_interrupt_and_disable_preserve_native_cancellation(self):
        self.check('''
            req.fast_return=true;step(1);player['服务器正在回城']=true;player['回城读条']=4;step(1.05)
            player['服务器正在回城']=false;player['回城读条']=5;step(1.1)
            assert(player['回城读条']==5)
            player['服务器正在回城']=true;player['回城读条']=4;step(2)
            req.fast_return=false;step(2.1);assert(player['回城读条']==4)
        ''')

    def test_return_rejects_dead_moving_or_background_start(self):
        self.check('''
            for _,key in ipairs({'已死亡','移动中','background'}) do
                bridge=Comfort.new();req.fast_return=true;req.active=true
                player['回城读条']=5;step(1)
                if key=='background' then req.active=false else player[key]=true end
                player['服务器正在回城']=true;player['回城读条']=4;step(1.05)
                assert(player['回城读条']==4);player[key]=false
            end
        ''')

    def test_whirlwind_only_changes_exact_animation_not_shared_effect(self):
        self.check('''
            req.whirlwind_mode='soft';step(1)
            assert(notify.Scale.X<2 and notify.Scale.X>0)
            assert(notify.Template==fx and other.Scale.X==3 and other.Template==fx)
            req.whirlwind_mode='hidden';step(2);assert(notify.Template==nil)
            req.whirlwind_mode='off';step(3)
            assert(notify.Template==fx and notify.Scale.X==2 and notify.Scale.Z==1)
        ''')

    def test_whirlwind_hides_live_skill_component_spawn(self):
        self.check('''
            req.whirlwind_mode='hidden';step(1)
            assert(spawn(skill,ground_fx)==nil,'current game spawns the ring outside animation notifies')
            assert(step(2).whirlwind.spawn_count==1)
            assert(hook_registrations==1 and ground_fx:IsValid())
        ''')

    def test_halfmoon_hides_animation_and_spawn_without_enabling_whirlwind(self):
        self.check('''
            req.halfmoon_mode='hidden';step(1)
            assert(moon_notify.Template==nil)
            assert(spawn(skill,moon_fx)==nil)
            assert(notify.Template==fx and spawn(skill,ground_fx)==ground_fx)
            assert(step(2).halfmoon.spawn_count==1 and step(2).whirlwind.state=='off')
            req.halfmoon_mode='off';step(3)
            assert(moon_notify.Template==moon_fx and spawn(skill,moon_fx)==moon_fx)
        ''')

    def test_halfmoon_soft_and_whirlwind_hidden_are_independent(self):
        self.check('''
            req.halfmoon_mode='soft';req.whirlwind_mode='hidden';step(1)
            local template,size=spawn(skill,moon_fx)
            assert(template==moon_fx and math.abs(size.X-1.3825)<.000001)
            assert(math.abs(moon_notify.Scale.X-1.3825)<.000001)
            assert(spawn(skill,ground_fx)==nil and notify.Template==nil)
            assert(spawn(other,moon_fx)==moon_fx and spawn(skill,fx)==fx)
            assert(hook_registrations==1,'both skills share one filtered native hook')
            bridge:stop()
            assert(moon_notify.Scale.X==3.95 and spawn(skill,moon_fx)==moon_fx)
        ''')

    def test_auto_halfmoon_uses_live_multicast_asset_and_restores_on_disable(self):
        self.check('''
            -- Resolved from the running skill function's bytecode: the
            -- automatic halfmoon references this asset, not moon_fx.
            req.halfmoon_mode='hidden';step(1)
            assert(spawn(skill,auto_moon_fx)==nil,'auto halfmoon uses the automatic slash asset')
            assert(step(2).halfmoon.spawn_count==1)
            assert(spawn(skill,sword_fx)==sword_fx,'sword-energy effect is a separate skill')
            assert(spawn(other,auto_moon_fx)==auto_moon_fx,'other players are out of scope')
            req.halfmoon_mode='soft';step(3)
            local original={X=3.95,Y=3.95,Z=3.95}
            local template,size=spawn(skill,auto_moon_fx,original)
            assert(template==auto_moon_fx and math.abs(size.X-1.3825)<.000001)
            assert(original.X==3.95 and auto_moon_fx:IsValid())
            req.halfmoon_mode='off';step(4)
            assert(spawn(skill,auto_moon_fx)==auto_moon_fx)
        ''')

    def test_halfmoon_keeps_lunge_animation_even_with_shared_template(self):
        self.check('''
            local path='AnimNotify_PlayNiagaraEffect /Game/Characters/Mannequin_UE4/Animations/攻击/突斩/'
                ..'突斩_Montage.突斩_Montage:AnimNotify_PlayNiagaraEffect_0'
            local lunge=object(path,{Template=moon_fx,Scale={X=2.5,Y=2.5,Z=2.5}})
            lists.AnimNotify_PlayNiagaraEffect={lunge}
            req.halfmoon_mode='soft';step(1)
            assert(lunge.Scale.X==2.5 and lunge.Template==moon_fx)
            req.halfmoon_mode='hidden';step(2)
            assert(lunge.Template==moon_fx and lunge.Scale.X==2.5)
            req.halfmoon_mode='off';step(3)
            assert(lunge.Template==moon_fx and lunge.Scale.X==2.5)
        ''')

    def test_halfmoon_all_levels_and_exact_animation_scope(self):
        self.check('''
            local targets={}
            for level=0,10 do
                local name='半月斩范围'..level
                targets[#targets+1]=object('AnimNotify_PlayNiagaraEffect /Game/Characters/Mannequin_UE4/Animations/攻击/0半月斩/'
                    ..name..'.'..name..':AnimNotify_PlayNiagaraEffect_0',{Template=moon_fx,Scale={X=2,Y=2,Z=1}})
            end
            local rejected=object('AnimNotify_PlayNiagaraEffect /Game/Other/半月斩范围8.半月斩范围8:AnimNotify_PlayNiagaraEffect_0',
                {Template=moon_fx,Scale={X=2,Y=2,Z=1}})
            lists.AnimNotify_PlayNiagaraEffect={rejected}
            for _,o in ipairs(targets) do table.insert(lists.AnimNotify_PlayNiagaraEffect,o) end
            req.halfmoon_mode='hidden'
            for i=1,4 do step(i) end
            assert(step(5).halfmoon.count==11)
            for _,o in ipairs(targets) do assert(o.Template==nil) end
            assert(rejected.Template==moon_fx)
        ''')

    def test_whirlwind_softens_only_visual_spawn_scale(self):
        self.check('''
            req.whirlwind_mode='soft';step(1)
            skill['技能范围']=8
            local original={X=3.95,Y=3.95,Z=3.95}
            local template,size=spawn(skill,ground_fx,original)
            assert(template==ground_fx and math.abs(size.X-1.3825)<.000001)
            assert(size.X==size.Y and size.Y==size.Z)
            assert(original.X==3.95 and skill['技能范围']==8)
            assert(step(2).whirlwind.spawn_count==1)
        ''')

    def test_whirlwind_spawn_scope_excludes_other_effects_players_and_monsters(self):
        self.check('''
            req.whirlwind_mode='hidden';step(1)
            for _,context in ipairs({other,object('技能组件_C other-player.技能组件'),player}) do
                local template,size=spawn(context,ground_fx)
                assert(template==ground_fx and size.X==3.95)
            end
            assert(spawn(skill,fx)==fx,'other skills and shared assets must remain unchanged')
            assert(step(2).whirlwind.spawn_count==0)
        ''')

    def test_whirlwind_spawn_is_inert_after_stop_expiry_or_disable(self):
        self.check('''
            req.whirlwind_mode='hidden';step(1)
            req.expires=os.time()-1;assert(spawn(skill,ground_fx)==ground_fx)
            req.expires=os.time()+60;player.local_player=false
            assert(spawn(skill,ground_fx)==ground_fx);player.local_player=true
            req.whirlwind_mode='off';step(2);assert(spawn(skill,ground_fx)==ground_fx)
            req.whirlwind_mode='soft';step(3);bridge:stop()
            assert(spawn(skill,ground_fx)==ground_fx)
            step(4);assert(hook_registrations==1,'mode changes must not accumulate hooks')
        ''')

    def test_whirlwind_spawn_write_failure_is_reported_without_escaping_callback(self):
        self.check('''
            req.whirlwind_mode='hidden';step(1)
            local original=param
            function param(value)
                local p=original(value)
                if value==ground_fx then p.set=function() end end
                return p
            end
            assert(spawn(skill,ground_fx)==ground_fx)
            local status=step(2).whirlwind
            assert(status.state=='error' and status.error:find('readback'))
            assert(status.spawn_count==0)
        ''')

    def test_all_whirlwind_levels_with_engine_subobject_paths(self):
        self.check('''
            local targets={}
            for level=0,10 do
                local name='旋风斩'..level
                for index=0,1 do
                    targets[#targets+1]=object(
                        'AnimNotify_PlayNiagaraEffect /Game/Characters/Mannequin_UE4/Animations/攻击/0旋风斩/'
                            ..name..'.'..name..':AnimNotify_PlayNiagaraEffect_'..index,
                        {Template=fx,Scale={X=2,Y=2,Z=1}})
                end
            end
            lists.AnimNotify_PlayNiagaraEffect=targets
            req.whirlwind_mode='soft'
            for i=1,8 do step(i) end
            assert(step(9).whirlwind.count==22,'all 22 engine paths must be recognized')
            for _,o in ipairs(targets) do
                assert(math.abs(o.Scale.X-.7)<.00001 and o.Template==fx)
            end
            req.whirlwind_mode='hidden'
            for i=10,17 do step(i) end
            for _,o in ipairs(targets) do assert(o.Template==nil and o.Scale.X==2) end
            req.whirlwind_mode='off';step(18)
            for _,o in ipairs(targets) do
                assert(o.Template==fx and o.Scale.X==2 and o.Scale.Z==1)
            end
        ''')

    def test_whirlwind_path_compatibility_does_not_broaden_effect_scope(self):
        self.check('''
            local prefix='AnimNotify_PlayNiagaraEffect /Game/Characters/Mannequin_UE4/Animations/攻击/0旋风斩/'
            local captured=object(prefix..'旋风斩3.旋风斩3.AnimNotify_PlayNiagaraEffect_0',
                {Template=fx,Scale={X=2,Y=2,Z=1}})
            local rejected={other}
            for _,path in ipairs({
                prefix..'旋风斩3.旋风斩4:AnimNotify_PlayNiagaraEffect_0',
                prefix..'旋风斩3.旋风斩3:AnimNotify_PlayNiagaraEffect_0.Other',
                prefix..'旋风斩3.旋风斩3:Other_0',
                prefix..'旋风斩3.旋风斩3/AnimNotify_PlayNiagaraEffect_0',
                'AnimNotify_PlayNiagaraEffect /Game/Other/旋风斩3.旋风斩3:AnimNotify_PlayNiagaraEffect_0'
            }) do
                rejected[#rejected+1]=object(path,{Template=fx,Scale={X=3,Y=3,Z=1}})
            end
            lists.AnimNotify_PlayNiagaraEffect={notify,captured}
            for _,o in ipairs(rejected) do table.insert(lists.AnimNotify_PlayNiagaraEffect,o) end
            req.whirlwind_mode='hidden'
            for i=1,4 do step(i) end
            assert(step(5).whirlwind.count==2 and notify.Template==nil and captured.Template==nil)
            for _,o in ipairs(rejected) do assert(o.Template==fx and o.Scale.X==3) end
            req.whirlwind_mode='off';step(6)
            assert(notify.Template==fx and captured.Template==fx)
        ''')

    def test_snow_uses_private_dynamic_material_and_reuses_it(self):
        self.check('''
            req.snow_theme='sage';step(1)
            assert(creations==1 and comp.MaterialInstances[1]==material)
            assert(comp.MaterialInstancesDynamic[1].color.G<original.G)
            local mid=comp.MaterialInstancesDynamic[1]
            req.snow_theme='slate';step(2);assert(creations==1 and comp.MaterialInstancesDynamic[1]==mid)
            for i=3,20 do step(i) end;assert(creations==1)
            req.snow_theme='off';step(21)
            assert(comp.MaterialInstancesDynamic:GetArrayNum()==0 and proxy.bUseDynamicMaterialInstance==false)
            assert(comp.bRenderCustomDepth==false)
        ''')

    def test_unrelated_material_nanite_and_other_world_are_untouched(self):
        self.check('''
            for _,case in ipairs({'material','nanite','world'}) do
                bridge=Comfort.new();req.snow_theme='beige'
                proxy.LandscapeMaterial=case=='material' and other or material
                proxy.bEnableNanite=case=='nanite'
                comp.GetWorld=function() return case=='world' and other or world end
                step(1);assert(creations==0)
            end
        ''')

    def test_replaced_material_is_reacquired_before_changing_theme(self):
        self.check('''
            req.snow_theme='beige';step(1)
            local old=comp.MaterialInstancesDynamic[1]
            local current=lib:CreateDynamicMaterialInstance(comp,material,FName('replacement'),0)
            comp.MaterialInstancesDynamic={current};old.alive=false
            req.snow_theme='sage';local result=step(2)
            assert(invalid_material_calls==0,'must not invoke a dead cached material')
            assert(result.snow.state=='applied' and math.abs(current.color.G-.513)<.00001)
            bridge:stop()
            assert(comp.MaterialInstancesDynamic[1]==current and current.color.G==.9)
            assert(proxy.bUseDynamicMaterialInstance,'must preserve replacement material rendering')
        ''')

    def test_live_but_detached_material_is_not_modified_or_restored(self):
        self.check('''
            req.snow_theme='beige';step(1)
            local old=comp.MaterialInstancesDynamic[1];local old_color=old.color
            local current=lib:CreateDynamicMaterialInstance(comp,material,FName('replacement'),0)
            comp.MaterialInstancesDynamic={current}
            req.snow_theme='sage';step(2)
            assert(old.color==old_color,'a valid detached material is no longer ours to change')
            assert(math.abs(current.color.G-.513)<.00001)
            bridge:stop();assert(old.color==old_color and current.color.G==.9)
        ''')

    def test_discarded_dynamic_array_is_recreated_without_reusing_dead_material(self):
        self.check('''
            req.snow_theme='beige';step(1)
            local old=comp.MaterialInstancesDynamic[1];old.alive=false
            comp.MaterialInstancesDynamic={}
            req.snow_theme='sage';step(2)
            assert(invalid_material_calls==0 and creations==2)
            assert(math.abs(comp.MaterialInstancesDynamic[1].color.G-.513)<.00001)
            bridge:stop()
            assert(comp.MaterialInstancesDynamic:GetArrayNum()==0 and not proxy.bUseDynamicMaterialInstance)
        ''')

    def test_reused_component_address_does_not_reuse_previous_materials(self):
        self.check('''
            req.snow_theme='beige';step(1)
            local old=comp.MaterialInstancesDynamic[1];old.alive=false
            comp.GetFullName=function() return 'LandscapeComponent map.NewLandscape.Component' end
            comp.MaterialInstancesDynamic={}
            req.snow_theme='sage';step(2)
            assert(invalid_material_calls==0 and creations==2)
            assert(math.abs(comp.MaterialInstancesDynamic[1].color.G-.513)<.00001)
        ''')

    def test_material_replacement_before_disable_preserves_new_owner(self):
        self.check('''
            req.snow_theme='beige';step(1)
            local old=comp.MaterialInstancesDynamic[1];old.alive=false
            local current=lib:CreateDynamicMaterialInstance(comp,material,FName('replacement'),0)
            comp.MaterialInstancesDynamic={current}
            req.snow_theme='off';step(2)
            assert(invalid_material_calls==0 and current.color==original)
            assert(comp.MaterialInstancesDynamic[1]==current and proxy.bUseDynamicMaterialInstance)
        ''')

    def test_reused_component_address_before_disable_preserves_new_owner(self):
        self.check('''
            req.snow_theme='beige';step(1)
            local old=comp.MaterialInstancesDynamic[1];old.alive=false
            comp.GetFullName=function() return 'LandscapeComponent map.NewLandscape.Component' end
            local current=lib:CreateDynamicMaterialInstance(comp,material,FName('replacement'),0)
            comp.MaterialInstancesDynamic={current}
            req.snow_theme='off';step(2)
            assert(invalid_material_calls==0 and current.color==original)
            assert(comp.MaterialInstancesDynamic[1]==current and proxy.bUseDynamicMaterialInstance,
                'must not disable rendering owned by a replacement component')
        ''')

    def test_destroyed_world_objects_are_discarded_without_restoration_calls(self):
        self.check('''
            req.snow_theme='beige';step(1)
            local old=comp.MaterialInstancesDynamic[1];old.alive=false
            comp.alive=false;proxy.alive=false;world.alive=false
            comp.GetFullName=function() error('destroyed component access') end
            proxy.GetAddress=function() error('destroyed proxy access') end
            local nextworld=object('nextworld');player.GetWorld=function() return nextworld end
            lists.LandscapeComponent={};step(2)
            assert(invalid_material_calls==0 and next(bridge.snow)==nil)
        ''')

    def test_each_created_material_is_engine_owned_before_next_allocation(self):
        self.check('''
            comp.MaterialInstances=array({material,material})
            local create=lib.CreateDynamicMaterialInstance
            lib.CreateDynamicMaterialInstance=function(...)
                assert(comp.MaterialInstancesDynamic:GetArrayNum()==creations,
                    'previous allocation must already have an engine-owned reference')
                return create(...)
            end
            req.snow_theme='sage';local result=step(1)
            assert(result.snow.state=='applied' and creations==2)
            bridge:stop();assert(comp.MaterialInstancesDynamic:GetArrayNum()==0)
        ''')

    def test_failed_second_allocation_rolls_back_first_material(self):
        self.check('''
            comp.MaterialInstances=array({material,material})
            local create=lib.CreateDynamicMaterialInstance
            lib.CreateDynamicMaterialInstance=function(...)
                if creations==1 then error('allocation failure') end
                return create(...)
            end
            req.snow_theme='sage';local result=step(1)
            assert(result.snow.state=='error' and creations==1)
            assert(comp.MaterialInstancesDynamic:GetArrayNum()==0)
            assert(not proxy.bUseDynamicMaterialInstance and next(bridge.snow)==nil)
        ''')

    def test_replacement_during_render_refresh_is_not_tinted(self):
        self.check('''
            local replacement=nil;local old=nil
            comp.SetRenderCustomDepth=function(_,value)
                if replacement==nil then
                    old=comp.MaterialInstancesDynamic[1];old.alive=false
                    replacement=lib:CreateDynamicMaterialInstance(comp,material,FName('replacement'),0)
                    comp.MaterialInstancesDynamic={replacement}
                end
                props.bRenderCustomDepth=value
            end
            req.snow_theme='sage';local result=step(1)
            assert(result.snow.state=='error' and invalid_material_calls==0)
            assert(comp.MaterialInstancesDynamic[1]==replacement and replacement.color==original)
        ''')

    def test_stop_restores_both_visual_features_and_return(self):
        self.check('''
            req.snow_theme='beige';req.whirlwind_mode='hidden';req.fast_return=true;step(1)
            player['服务器正在回城']=true;player['回城读条']=4;step(1.05)
            bridge:stop()
            assert(notify.Template==fx and notify.Scale.X==2)
            assert(comp.MaterialInstancesDynamic:GetArrayNum()==0 and not proxy.bUseDynamicMaterialInstance)
            assert(player['回城读条']==4)
        ''')

    def test_world_change_restores_previous_objects(self):
        self.check('''
            req.snow_theme='beige';req.fast_return=true;step(1)
            player['服务器正在回城']=true;player['回城读条']=4;step(1.05)
            local nextworld=object('nextworld');player.GetWorld=function() return nextworld end
            step(1.1)
            assert(comp.MaterialInstancesDynamic:GetArrayNum()==0 and not proxy.bUseDynamicMaterialInstance)
            assert(player['回城读条']==4)
        ''')

    def test_existing_dynamic_material_is_restored_without_replacement(self):
        self.check('''
            local mid=lib:CreateDynamicMaterialInstance(comp,material,FName('existing'),0)
            comp.MaterialInstancesDynamic={mid};proxy.bUseDynamicMaterialInstance=true
            req.snow_theme='sage';step(1)
            assert(creations==1 and mid.color.R<original.R)
            bridge:stop()
            assert(comp.MaterialInstancesDynamic[1]==mid and mid.color.R==original.R)
            assert(proxy.bUseDynamicMaterialInstance==true)
        ''')

    def test_visual_failure_rolls_back_partial_snow_change(self):
        self.check('''
            req.snow_theme='sage'
            local create=lib.CreateDynamicMaterialInstance
            lib.CreateDynamicMaterialInstance=function(...)
                local mid=create(...)
                mid.SetVectorParameterValue=function() error('simulated material failure') end
                return mid
            end
            local status=step(1)
            assert(status.snow.state=='error')
            assert(comp.MaterialInstancesDynamic:GetArrayNum()==0 and proxy.bUseDynamicMaterialInstance==false)
        ''')

    def test_hidden_template_can_be_restored_after_asset_collection(self):
        self.check('''
            req.whirlwind_mode='hidden';step(1);fx.alive=false
            local replacement=object('NiagaraSystem shared.Bear')
            LoadAsset=function(path) assert(path=='shared.Bear');return replacement end
            req.whirlwind_mode='off';step(2)
            assert(notify.Template==replacement)
        ''')

    def test_new_objects_are_queued_without_continuous_full_scans(self):
        self.check('''
            req.whirlwind_mode='hidden';step(1);local before=scans
            for i=2,20 do step(i) end;assert(scans==before)
            local new=object(notify:GetFullName(),{Template=fx,Scale={X=4,Y=4,Z=1}})
            hooks['/Script/NiagaraAnimNotifies.AnimNotify_PlayNiagaraEffect'](new)
            for i=21,24 do step(i) end;assert(new.Template==nil)
            bridge:stop();assert(new.Template==fx)
        ''')


if __name__ == '__main__':
    unittest.main()
