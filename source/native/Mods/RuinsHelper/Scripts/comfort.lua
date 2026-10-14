-- SPDX-License-Identifier: MIT
-- Verified against build 25669660. Runtime-only overrides; no asset/save writes.
local M = {}
local THEMES = {beige={.62,.55,.43},sage={.46,.57,.48},slate={.36,.40,.47}}
local LAND = '/Game/land/Materials/landscape/MI_landscape_Inst.MI_landscape_Inst'
local WHIRL = '/Game/Characters/Mannequin_UE4/Animations/攻击/0旋风斩/'
local WHIRL_EFFECT = 'NiagaraSystem /Game/怪物/熊怪/熊冲击粒子.熊冲击粒子'
local HALFMOON = '/Game/Characters/Mannequin_UE4/Animations/攻击/0半月斩/'
local HALFMOON_EFFECT = 'NiagaraSystem /Game/粒子/0近战/半月.半月'
-- Resolved from the live 组播半月斩特效 bytecode; automatic procs use a
-- different Niagara system from the manually cast animation notifies.
local AUTO_HALFMOON_EFFECT = 'NiagaraSystem /Game/Hack_And_Slash_FX/VFX_Niagara/Slashes/自动.自动'
local SPAWN_EFFECT = '/Script/Niagara.NiagaraFunctionLibrary:SpawnSystemAtLocation'
local function valid(o) return o and o:IsValid() end
local function same(a,b) return valid(a) and valid(b) and a:GetAddress()==b:GetAddress() end
local function color(v) return {R=v.R,G=v.G,B=v.B,A=v.A} end
local function vector(v) return {X=v.X,Y=v.Y,Z=v.Z} end
local function finite(v) return type(v)=='number' and v==v and math.abs(v)<100000 end
local function identity(o) return {address=o:GetAddress(),path=o:GetFullName()} end
local function matches(o,id)
    return id and valid(o) and o:GetAddress()==id.address and o:GetFullName()==id.path
end
local function owns_materials(c,r,partial)
    local arr=c.MaterialInstancesDynamic
    local n=arr:GetArrayNum()
    if n~=#r.materials and not (partial and r.created and n<#r.materials) then return false end
    for i=1,n do if not matches(arr[i],r.materials[i]) then return false end end
    return true
end
local function current_material(c,r,i)
    -- Never retain a MID wrapper between ticks. Resolve the component's current
    -- slot and check it before invoking ProcessEvent on the material.
    local mid=c:GetMaterialInstanceDynamic(i-1)
    assert(matches(mid,r.materials[i]),'Landscape material changed during update')
    return mid
end
local function refresh_render(c)
    local old=c.bRenderCustomDepth
    assert(type(old)=='boolean','Missing render flag')
    c:SetRenderCustomDepth(not old)
    c:SetRenderCustomDepth(old)
end
local function exact_whirl(o)
    local path=o:GetFullName()
    local rest=path:match('^AnimNotify_PlayNiagaraEffect '..WHIRL..'(.*)$')
    if not rest then return false end
    -- GetFullName uses ':' for asset subobjects; reflection captures used '.'.
    -- Accept either separator while retaining the exact animation allowlist.
    local asset,outer=rest:match('^(旋风斩%d*)%.(旋风斩%d*)[:.]AnimNotify_PlayNiagaraEffect_%d+$')
    return asset~=nil and asset==outer
end
local function exact_halfmoon(o)
    local path=o:GetFullName()
    local rest=path:match('^AnimNotify_PlayNiagaraEffect '..HALFMOON..'(.*)$')
    if not rest then return false end
    local asset,outer=rest:match('^(半月斩范围%d+)%.(半月斩范围%d+)[:.]AnimNotify_PlayNiagaraEffect_%d+$')
    return asset~=nil and asset==outer
end

function M.new()
    local self={snow={},proxies={},whirl={},halfmoon={},snow_queue={},whirl_queue={},halfmoon_queue={},hooks={},
        snow_mode='off',whirl_mode='off',halfmoon_mode='off',whirl_spawns=0,halfmoon_spawns=0,world=nil,player=nil,now=0}

    function self:apply_skill_spawn(...)
        local req=self.whirl_request
        if (self.whirl_mode=='off' and self.halfmoon_mode=='off') or not req
                or type(req.expires)~='number' or os.time()>req.expires
                or not valid(self.player) then return end
        assert(select('#',...)==9,'Unsupported Niagara spawn signature')
        local context,template,location,rotation,scale=...
        -- 组播旋风斩特效 and 组播半月斩特效 spawn directly with their
        -- skill component as WorldContextObject. Never suppress a shared
        -- bear asset globally, or touch skill range/damage/animation playback.
        if not same(context:get(),self.player['技能组件']) then return end
        if self.player:IsLocallyControlled()~=true then return end
        local effect=template:get()
        if not valid(effect) then return end
        local path=effect:GetFullName()
        local kind=path==WHIRL_EFFECT and 'whirl'
            or (path==HALFMOON_EFFECT or path==AUTO_HALFMOON_EFFECT) and 'halfmoon' or nil
        if not kind or self[kind..'_mode']=='off' or self[kind..'_error'] then return end
        local ok,err=pcall(function()
            if self[kind..'_mode']=='hidden' then
                template:set(nil)
                assert(not valid(template:get()),'Skill effect template readback failed')
            else
                local s=vector(scale:get())
                assert(finite(s.X) and finite(s.Y) and finite(s.Z),'Invalid spawned effect scale')
                scale:set({X=s.X*.35,Y=s.Y*.35,Z=s.Z*.35})
                local applied=scale:get()
                assert(math.abs(applied.X-s.X*.35)<.000001
                    and math.abs(applied.Y-s.Y*.35)<.000001
                    and math.abs(applied.Z-s.Z*.35)<.000001,'Skill effect scale readback failed')
            end
        end)
        if ok then self[kind..'_spawns']=self[kind..'_spawns']+1
        else self[kind..'_error']=tostring(err) end
    end

    function self:hook_whirl_spawn()
        if self.whirl_spawn_ids then return end
        assert(valid(StaticFindObject(SPAWN_EFFECT)),'Niagara spawn function unavailable')
        -- Native /Script hooks run before spawning; Blueprint hooks run after
        -- their effects have already been created. Keep one inert hook when off.
        local first,last=RegisterHook(SPAWN_EFFECT,function(_, ...)
            local ok,err=pcall(self.apply_skill_spawn,self,...)
            if not ok then
                for _,kind in ipairs({'whirl','halfmoon'}) do
                    if self[kind..'_mode']~='off' then self[kind..'_error']=tostring(err) end
                end
            end
        end)
        assert(type(first)=='number' and type(last)=='number','Niagara spawn hook unavailable')
        self.whirl_spawn_ids={first,last}
    end

    function self:restore_return()
        local r=self.return_override
        if r and valid(r.player) and r.player:HasAuthority()==true and r.player:IsLocallyControlled()==true
                and r.player['服务器正在回城']==true and r.player['回城读条']==1 then
            r.player['回城读条']=math.max(1,r.original-math.floor(math.max(0,self.now-r.at)))
        end
        self.return_override=nil
        self.last_remaining=nil
    end

    function self:return_step(player,req,now)
        if req.fast_return~=true then self:restore_return();return {state='off'} end
        if player:HasAuthority()~=true or player:IsLocallyControlled()~=true then
            self.return_override=nil;self.last_remaining=nil
            return {state='host_only'}
        end
        local remaining=player['回城读条']
        local running=player['服务器正在回城']
        if not finite(remaining) or remaining%1~=0 or remaining<0 or remaining>5
                or type(running)~='boolean' then
            self:restore_return();return {state='unsupported'}
        end
        -- Native cancellation resets the count to 5. Successful return can
        -- leave the server flag true, so use the 5 -> 4 countdown transition.
        if remaining~=1 or running~=true then self.return_override=nil end
        local previous=self.last_remaining
        self.last_remaining=remaining
        if req.active~=true then return {state='inactive'} end
        if player['已死亡']~=false or player['移动中']~=false then return {state='waiting'} end
        if previous==5 and remaining==4 and running then
            self.return_override={player=player,original=4,at=now}
            player['回城读条']=1
            self.last_remaining=1
            return {state='shortened'}
        end
        return {state=self.return_override and 'shortened' or 'ready'}
    end

    function self:restore_notifies(kind)
        for id,r in pairs(self[kind]) do
            if valid(r.object) and r.object:GetFullName()==r.path then
                -- Restore only our own override; do not overwrite another mod.
                if r.hidden and not valid(r.object.Template) then
                    -- Lua wrappers do not keep UObject assets alive through GC.
                    local template=r.template
                    if not valid(template) then template=LoadAsset(r.template_path) end
                    assert(valid(template),'Original skill effect could not be reloaded')
                    r.object.Template=template
                end
                if not r.hidden then
                    local s=r.object.Scale
                    if s.X==r.scale.X*.35 and s.Y==r.scale.Y*.35 and s.Z==r.scale.Z*.35 then
                        r.object.Scale=r.scale
                    end
                end
            end
            self[kind][id]=nil
        end
        self[kind..'_queue']={}
    end
    function self:restore_whirl() self:restore_notifies('whirl') end
    function self:restore_halfmoon() self:restore_notifies('halfmoon') end

    function self:restore_snow()
        local foreign,refresh={},{}
        for id,r in pairs(self.snow) do
            local c=r.object
            if valid(c) then
                if c:GetFullName()~=r.path then
                    -- The address now belongs to another component. Its proxy
                    -- mode is no longer ours to restore, even without a retint.
                    foreign[r.proxy_id]=true
                elseif owns_materials(c,r,true) then
                    if r.created then
                        c.MaterialInstancesDynamic:Empty()
                        refresh[#refresh+1]=r
                    else
                        for i,original in ipairs(r.colors) do
                            current_material(c,r,i):SetVectorParameterValue(FName('冰color'),original)
                        end
                    end
                else foreign[r.proxy_id]=true end
            end
            self.snow[id]=nil
        end
        for id,r in pairs(self.proxies) do
            if not foreign[id] and not r.foreign and valid(r.object)
                    and r.object:GetFullName()==r.path and r.object.bUseDynamicMaterialInstance==true then
                r.object.bUseDynamicMaterialInstance=r.original
            end
            self.proxies[id]=nil
        end
        -- Refresh only after the proxy's original material mode is restored.
        for _,r in ipairs(refresh) do
            if valid(r.object) and r.object:GetFullName()==r.path then refresh_render(r.object) end
        end
        self.snow_queue={}
    end

    function self:stop()
        self.whirl_request=nil
        -- Each restoration is independent, so one stale object cannot prevent
        -- the other features from returning to their original state.
        local errors={}
        for _,name in ipairs({'restore_return','restore_whirl','restore_halfmoon','restore_snow'}) do
            local ok,err=pcall(function() self[name](self) end)
            if not ok then errors[#errors+1]=tostring(err) end
        end
        self.snow_mode,self.whirl_mode,self.halfmoon_mode='off','off','off'
        self.snow_error,self.whirl_error,self.halfmoon_error=nil,nil,nil
        if #errors>0 then error(table.concat(errors,'; ')) end
    end

    function self:queue(kind,o,delay)
        if not valid(o) then return end
        local q=self[kind..'_queue']
        if #q<2048 then q[#q+1]={object=o,delay=delay or 0} end
    end

    function self:discover(kind,class,path)
        if not self.hooks[kind] then
            self.hooks[kind]=true
            NotifyOnNewObject(path,function(o)
                if self[kind..'_mode']~='off' then self:queue(kind,o,3) end
            end)
        end
        for _,o in ipairs(FindAllOf(class) or {}) do self:queue(kind,o) end
    end

    function self:apply_notify(kind,o)
        if not (kind=='whirl' and exact_whirl(o) or kind=='halfmoon' and exact_halfmoon(o)) then return end
        local id=o:GetAddress()
        if self[kind][id] then return end
        if not valid(o.Template) then return end
        local scale=vector(o.Scale)
        assert(finite(scale.X) and finite(scale.Y) and finite(scale.Z),'Invalid effect scale')
        local template_path=o.Template:GetFullName():match('^NiagaraSystem (.+)$')
        assert(template_path,'Unexpected skill effect template type')
        local r={object=o,path=o:GetFullName(),template=o.Template,template_path=template_path,
            scale=scale,hidden=self[kind..'_mode']=='hidden'}
        self[kind][id]=r
        if r.hidden then o.Template=nil
        else o.Scale={X=scale.X*.35,Y=scale.Y*.35,Z=scale.Z*.35} end
    end
    function self:apply_whirl(o) self:apply_notify('whirl',o) end
    function self:apply_halfmoon(o) self:apply_notify('halfmoon',o) end

    function self:apply_snow(c)
        if not same(c:GetWorld(),self.world) then return end
        local proxy=c:GetOuter()
        if not valid(proxy) or not valid(proxy.LandscapeMaterial)
                or proxy.LandscapeMaterial:GetFullName()~='MaterialInstanceConstant '..LAND
                or proxy.bEnableNanite~=false or c.bNaniteActive~=false then return end
        if type(proxy.bUseDynamicMaterialInstance)~='boolean' then error('Missing dynamic-material flag') end
        local id=c:GetAddress();local r=self.snow[id]
        if r and (c:GetFullName()~=r.path or not owns_materials(c,r)) then
            -- Streaming/rebuilds can replace or clear the array while the
            -- component stays valid. Do not touch its former material objects.
            if c.MaterialInstancesDynamic:GetArrayNum()>0 and self.proxies[r.proxy_id] then
                self.proxies[r.proxy_id].foreign=true
            end
            self.snow[id]=nil;r=nil
        end
        if not r then
            local base,dynamic=c.MaterialInstances,c.MaterialInstancesDynamic
            local n=base:GetArrayNum();local dn=dynamic:GetArrayNum()
            assert(n>=1 and n<=8 and (dn==0 or dn==n),'Unsupported landscape material layout')
            local pid=proxy:GetAddress()
            local p=self.proxies[pid]
            if not p or p.path~=proxy:GetFullName() then
                self.proxies[pid]={object=proxy,path=proxy:GetFullName(),original=proxy.bUseDynamicMaterialInstance}
            end
            r={object=c,path=c:GetFullName(),proxy_id=pid,materials={},colors={},created=dn==0}
            self.snow[id]=r
            local created={}
            local lib=dn==0 and StaticFindObject('/Script/Engine.Default__KismetMaterialLibrary') or nil
            if dn==0 then assert(valid(lib),'Material library unavailable') end
            for i=1,n do
                assert(valid(base[i]),'Missing landscape parent')
                local mid=dn>0 and dynamic[i] or lib:CreateDynamicMaterialInstance(c,base[i],FName('None'),0)
                assert(valid(mid),'Dynamic material creation failed')
                r.materials[i]=identity(mid)
                if dn==0 then
                    -- A Lua reference is not a GC root. Attach each new MID to
                    -- the engine-owned array before the next native operation.
                    created[i]=mid
                    c.MaterialInstancesDynamic=created
                    assert(c.MaterialInstancesDynamic:GetArrayNum()==i
                        and matches(c.MaterialInstancesDynamic[i],r.materials[i]),'Dynamic material assignment failed')
                end
                local original=color(mid:K2_GetVectorParameterValue(FName('冰color')))
                assert(finite(original.R) and finite(original.G) and finite(original.B) and finite(original.A),'Invalid snow color')
                r.colors[i]=original
            end
            proxy.bUseDynamicMaterialInstance=true
            if dn==0 then refresh_render(c) end
        end
        local tint=THEMES[self.snow_mode]
        for i,old in ipairs(r.colors) do
            local mid=current_material(c,r,i)
            mid:SetVectorParameterValue(FName('冰color'),{R=old.R*tint[1],G=old.G*tint[2],B=old.B*tint[3],A=old.A})
        end
        r.mode=self.snow_mode
    end

    function self:visual_step(kind,mode)
        local old=self[kind..'_mode']
        if old~=mode then
            if kind~='snow' then self['restore_'..kind](self)
            elseif mode=='off' then self:restore_snow() end
            self[kind..'_mode']=mode
            self[kind..'_error']=nil
            if mode~='off' then
                if kind~='snow' then
                    self[kind..'_spawns']=0
                    local ok,err=pcall(self.hook_whirl_spawn,self)
                    if not ok then self[kind..'_error']=tostring(err) end
                end
                if old=='off' or kind~='snow' then
                    self:discover(kind,kind=='snow' and 'LandscapeComponent' or 'AnimNotify_PlayNiagaraEffect',
                        kind=='snow' and '/Script/Landscape.LandscapeComponent' or '/Script/NiagaraAnimNotifies.AnimNotify_PlayNiagaraEffect')
                else
                    for _,r in pairs(self.snow) do self:queue('snow',r.object) end
                end
            end
        end
        if mode=='off' then return {state='off'} end
        if self[kind..'_error'] then return {state='error',error=self[kind..'_error']} end
        local q=self[kind..'_queue']
        -- Bounded batches; discovery is once per enable, then creation events.
        for _=1,math.min(3,#q) do
            local entry=table.remove(q,1)
            if entry.delay>0 then entry.delay=entry.delay-1;q[#q+1]=entry
            elseif valid(entry.object) then
                local ok,err=pcall(function() self['apply_'..kind](self,entry.object) end)
                if not ok then
                    self[kind..'_error']=tostring(err)
                    local restored,restore_error=pcall(function() self['restore_'..kind](self) end)
                    if not restored then self[kind..'_error']=self[kind..'_error']..'; '..tostring(restore_error) end
                    break
                end
            end
        end
        local count=0
        for _,r in pairs(self[kind]) do if valid(r.object) then count=count+1 end end
        return {state=self[kind..'_error'] and 'error' or (#q>0 and 'applying' or count>0 and 'applied' or 'waiting'),
            count=count,error=self[kind..'_error']}
    end

    function self:step(player,req,now)
        self.now=now
        local world=player:GetWorld()
        if self.player and (not same(player,self.player) or not same(world,self.world)) then self:stop() end
        self.player,self.world=player,world
        self.whirl_request=req
        local snow=THEMES[req.snow_theme] and req.snow_theme or 'off'
        local whirl=(req.whirlwind_mode=='soft' or req.whirlwind_mode=='hidden') and req.whirlwind_mode or 'off'
        local halfmoon=(req.halfmoon_mode=='soft' or req.halfmoon_mode=='hidden') and req.halfmoon_mode or 'off'
        local status={}
        local ok,result=pcall(function() return self:return_step(player,req,now) end)
        status.fast_return=ok and result or {state='error',error=tostring(result)}
        for key,mode in pairs({snow=snow,whirl=whirl,halfmoon=halfmoon}) do
            ok,result=pcall(function() return self:visual_step(key,mode) end)
            status[key=='whirl' and 'whirlwind' or key]=ok and result or {state='error',error=tostring(result)}
        end
        status.whirlwind.spawn_count=self.whirl_spawns
        status.halfmoon.spawn_count=self.halfmoon_spawns
        return status
    end
    return self
end
return M
