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
                assert(path=='/Script/Engine.Default__KismetMaterialLibrary');return lib
            end
            fx=object('NiagaraSystem shared.Bear')
            notify=object('AnimNotify_PlayNiagaraEffect /Game/Characters/Mannequin_UE4/Animations/攻击/0旋风斩/旋风斩3.旋风斩3.AnimNotify_PlayNiagaraEffect_0',
                {Template=fx,Scale={X=2,Y=2,Z=1}})
            other=object('AnimNotify_PlayNiagaraEffect /Game/怪物/熊怪/攻击.攻击.Notify',{Template=fx,Scale={X=3,Y=3,Z=1}})
            lists.AnimNotify_PlayNiagaraEffect={notify,other}
            lists.LandscapeComponent={comp}
            bridge=Comfort.new()
            req={active=true,fast_return=false,snow_theme='off',whirlwind_mode='off'}
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
