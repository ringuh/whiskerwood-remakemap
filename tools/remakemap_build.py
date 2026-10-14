"""Generates the Blueprint paste text (T3D) for the RemakeMap mod into tools/out/.
Usage: JMAP=path/to/Whiskerwood-x.jmap.gz python tools/remakemap_build.py

Assets (/Game/Mods/RemakeMap/):
  BP_Startup         Actor        mod option
  BP_MapLoad         Actor        all logic
  WBP_RemakeButton   Widget BP, designer only: Button `Btn` -> TextBlock `Label` (both Is Variable)
  PAL_RemakeMap      Primary Asset Label, chunk 30

How the game does it (jmap 0.7.207):
  - The new-game menu stores its choices in the MetaSave (ArcoGameInstance.GetMetaSave): newMapExtents,
    newMapColonyName, newStartingAgents (AgentCharacteristics array), difficulty_debtMultiplier,
    newMapRawPreferences (Name -> Float), newMapPreferenceNames (Name -> Name). Setters: SetNewMap*.
  - ArcoGameInstance.EnterPlay(Context, Filename, gameType, saveLocation, forceFullReplay) starts a map;
    gameType NEW_GENERATION = a freshly generated map.
  - No map seed is visible to Blueprints, so a remake is a new random map with the same settings.
  - Day number: ArcoSystems (GetArcoSys).m_worldTime.m_day; ModAPI.onDayStart(day).

  - The map seed is one of the new-map preferences: rule "Seed", choice name = the seed number as a Name
    (e.g. 7265501), raw value a float (e.g. 110.86). v1 (EnterPlay alone) rebuilt the exact same map.

v2: the second click rolls a new seed (SetNewMapPreference "Seed" = random 1..9999999, raw = random 0..1000),
then EnterPlay(NEW_GENERATION). Everything else (size, islands, scenario, difficulty, whiskers) comes from
the MetaSave unchanged. The button only shows in a new (not loaded) colony on day 1 (m_day <= 1) and is
removed at the first onDayStart with day > 1.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from rm_common import *

BUILD = 'v2'
TRACE = False         # test build: every log line ungated. Release builds: False (Debug = RemakeMapConfig\debug.txt)
OUT = os.path.join(os.path.dirname(__file__), 'out')
os.makedirs(OUT, exist_ok=True)

STARTUP, MAPLOAD, BTN = M + 'BP_Startup', M + 'BP_MapLoad', M + 'WBP_RemakeButton'
BTN_CLS, BTN_T = wbp_cls(BTN), wbp_t(BTN)
GI = PA + 'ArcoGameInstance'
META = PA + 'MetaSave'
META_T = OBJ(META)
ARCO, WTIME = PA + 'ArcoSystems', PA + 'WorldTime'
AGC = PA + 'AgentCharacteristics'
OPT_BTN = 'RemakeMap_Button'
LABEL = 'Remake map'
LABEL_ARMED = 'Click again to remake the map'


def write(name, g):
    open(os.path.join(OUT, name + '.txt'), 'w', encoding='utf-8').write(g.text())


def L(g, x, y, msg_pin=None, msg=None, name='Log'):
    return log(g, x, y, msg_pin=msg_pin, msg=msg, name=name, trace=TRACE)


# =========================================================================== BP_Startup (Actor)
g = Graph(STARTUP)
bp = g.event('/Script/Engine.Actor', 'ReceiveBeginPlay', [], 'Begin', 0, 0)
vals = g.add(BG + 'K2Node_MakeArray', 'Vals0', ['NumInputs=2'], 300, 250)
vals.pin('Array', ARR(STR), out=True)
vals.pin('[0]', STR, default='On'); vals.pin('[1]', STR, default='Off')
reg = api_call(g, 'RegisterModOptions', 600, 0, name='Reg0', optionId=OPT_BTN,
               optionDisplayName='Remake Map - day 1 button',
               DefaultValue='On',
               optionDescription='Shows a Remake button on the first day of a new colony. Clicking it twice starts a fresh map '
                                 'with the same new-game settings and the same starting whiskers.')
link(vals['Array'], reg['Values']); ex(bp, reg)
write('BP_Startup', g)


# =========================================================================== BP_MapLoad (Actor)
g = Graph(MAPLOAD)


def gv(var, t, x, y, tag=''):
    return g.get(var, t, x, y, name=var + 'Get' + tag)[var]


def sv(var, t, x, y, val_pin=None, value=None, tag=''):
    n = g.setv(var, t, x, y, value=value, name='Set' + var + tag)
    if val_pin is not None: link(val_pin, n[var])
    return n


def oget(owner, var, t, target_pin, x, y, name):
    """read a native property of another object"""
    n = g.get(var, t, x, y, owner=owner, name=name)
    link(target_pin, n['self'])
    return n[var]


def fstr(pin, x, y, name):
    return conv(g, 'Conv_DoubleToString', pin, x, y, name)


def set_label(text, x, y, tag, prev, prev_pin='then'):
    lb = bp_get(g, BTN_CLS, 'Label', TXT_T, gv('Button', BTN_T, x - 150, y + 200, 'Lbl' + tag), x, y + 200, 'LabelGet' + tag)
    tt = g.call(KTXT + ':Conv_StringToText', 'LabelText' + tag, x, y + 350, InString=text)
    st = g.call('/Script/UMG.TextBlock:SetText', 'SetLabel' + tag, x + 250, y); link(lb['Label'], st['self']); link(tt['ReturnValue'], st['InText'])
    ex(prev, st, prev_pin)
    return st


def map_t(kt, vt):
    return MAP(kt, vt)


def retype(pin, t):
    """wildcard map-library pins: set the real type, drop the int default the jmap placeholder gave them"""
    pin.t = dict(t); pin.default = None


def dump_meta(prev, prev_pin, x, y, tag):
    """GetMetaSave -> Meta; log extents, colony name, debt, agent count, every agent (name, guild),
    every map preference (key = choice name / raw value). Returns the node whose 'then' continues."""
    gm = g.call(GI + ':GetMetaSave', 'GetMeta' + tag, x, y)
    link(self_node(g, x - 150, y + 150, 'MeMeta' + tag)['self'], gm['Context']); ex(prev, gm, prev_pin)
    sm = sv('Meta', META_T, x + 250, y, gm['ReturnValue'], tag=tag); ex(gm, sm)
    mt = lambda xx, yy, tt: gv('Meta', META_T, xx, yy, tt + tag)
    ext = oget(META, 'newMapExtents', STRUCT('/Script/CoreUObject.IntVector'), mt(x + 300, y + 300, 'E'), x + 450, y + 300, 'MetaExtents' + tag)
    nam = oget(META, 'newMapColonyName', STR, mt(x + 300, y + 400, 'N'), x + 450, y + 400, 'MetaName' + tag)
    dbt = oget(META, 'difficulty_debtMultiplier', FLT, mt(x + 300, y + 500, 'D'), x + 450, y + 500, 'MetaDebt' + tag)
    ags = oget(META, 'newStartingAgents', ARR(STRUCT(AGC)), mt(x + 300, y + 600, 'A'), x + 450, y + 600, 'MetaAgents' + tag)
    agn = arrfn(g, 'Array_Length', STRUCT(AGC), x + 650, y + 600, 'AgentCount' + tag, arr_pin=ags)
    msg = concat(g, x + 800, y + 300, 'RemakeMap: [', tag, '] MetaSave valid=',
                 bstr(g, is_valid(g, mt(x + 500, y + 800, 'V'), x + 650, y + 800, 'MetaValid' + tag), x + 750, y + 800, 'MetaValidStr' + tag),
                 ' extents=', conv(g, 'Conv_IntVectorToString', ext, x + 650, y + 300, 'ExtStr' + tag),
                 ' colony=', nam,
                 ' debt=', fstr(dbt, x + 650, y + 500, 'DebtStr' + tag),
                 ' agents=', istr(g, agn['ReturnValue'], x + 750, y + 600, 'AgentCountStr' + tag))
    l1 = L(g, x + 500, y, msg_pin=msg, name='LogMeta' + tag); ex(sm, l1)
    # every starting whisker
    lp = foreach(g, oget(META, 'newStartingAgents', ARR(STRUCT(AGC)), mt(x + 900, y + 200, 'L'), x + 1000, y + 200, 'MetaAgentsL' + tag),
                 STRUCT(AGC), x + 1100, y, 'AgentLoop' + tag)
    ex(l1, lp, 'then', 'Exec')
    br = struct_node(g, 'Break', AGC, ['agentName', 'guild', 'ID'], x + 1300, y + 250, 'BreakAgent' + tag)
    link(lp['Array Element'], br['AgentCharacteristics'])
    la = L(g, x + 1500, y, msg_pin=concat(g, x + 1500, y + 200, 'RemakeMap: [', tag, '] whisker ',
                                           istr(g, lp['Array Index'], x + 1400, y + 450, 'AgentIdx' + tag), ': ', br['agentName'],
                                           ' guild=', nstr(g, br['guild'], x + 1400, y + 550, 'GuildStr' + tag),
                                           ' id=', istr(g, br['ID'], x + 1400, y + 650, 'AgentIdStr' + tag)), name='LogAgent' + tag)
    ex(lp, la, 'LoopBody')
    # every new-map preference: key = choice name (raw value)
    pmap_t = map_t(NAME, NAME); rmap_t = map_t(NAME, FLT)
    pn = oget(META, 'newMapPreferenceNames', pmap_t, mt(x + 1700, y + 300, 'P'), x + 1850, y + 300, 'MetaPrefNames' + tag)
    mk = g.call('/Script/Engine.BlueprintMapLibrary:Map_Keys', 'PrefKeys' + tag, x + 2000, y)
    tm = dict(pmap_t); tm['ref'] = True; tm['const'] = True; retype(mk['TargetMap'], tm)
    retype(mk['Keys'], ARR(NAME))
    link(pn, mk['TargetMap']); ex(lp, mk, 'Completed')
    sk = sv('PrefKeys', ARR(NAME), x + 2250, y, mk['Keys'], tag=tag); ex(mk, sk)
    lk = foreach(g, gv('PrefKeys', ARR(NAME), x + 2300, y + 200, 'L' + tag), NAME, x + 2500, y, 'PrefLoop' + tag)
    ex(sk, lk, 'then', 'Exec')
    f1 = g.call('/Script/Engine.BlueprintMapLibrary:Map_Find', 'PrefFindName' + tag, x + 2700, y + 300)
    t1 = dict(pmap_t); t1['ref'] = True; t1['const'] = True; retype(f1['TargetMap'], t1)
    k1 = dict(NAME); k1['ref'] = True; k1['const'] = True; retype(f1['Key'], k1); retype(f1['Value'], NAME)
    link(oget(META, 'newMapPreferenceNames', pmap_t, mt(x + 2500, y + 400, 'P2'), x + 2550, y + 400, 'MetaPrefNames2' + tag), f1['TargetMap'])
    link(lk['Array Element'], f1['Key'])
    f2 = g.call('/Script/Engine.BlueprintMapLibrary:Map_Find', 'PrefFindRaw' + tag, x + 2700, y + 550)
    t2 = dict(rmap_t); t2['ref'] = True; t2['const'] = True; retype(f2['TargetMap'], t2)
    retype(f2['Key'], k1); retype(f2['Value'], FLT)
    link(oget(META, 'newMapRawPreferences', rmap_t, mt(x + 2500, y + 650, 'R'), x + 2550, y + 650, 'MetaPrefRaw' + tag), f2['TargetMap'])
    link(lk['Array Element'], f2['Key'])
    lpf = L(g, x + 2900, y, msg_pin=concat(g, x + 2900, y + 200, 'RemakeMap: [', tag, '] pref ',
                                            nstr(g, lk['Array Element'], x + 2750, y + 800, 'PrefKeyStr' + tag), ' = ',
                                            nstr(g, f1['Value'], x + 2950, y + 400, 'PrefNameStr' + tag), ' (raw ',
                                            fstr(f2['Value'], x + 2950, y + 550, 'PrefRawStr' + tag), ')'), name='LogPref' + tag)
    ex(lk, lpf, 'LoopBody')
    # raw prefs that have no choice name
    rk = g.call('/Script/Engine.BlueprintMapLibrary:Map_Length', 'RawPrefCount' + tag, x + 3200, y + 300)
    t3 = dict(rmap_t); t3['ref'] = True; t3['const'] = True; retype(rk['TargetMap'], t3)
    link(oget(META, 'newMapRawPreferences', rmap_t, mt(x + 3000, y + 400, 'R2'), x + 3050, y + 400, 'MetaPrefRaw2' + tag), rk['TargetMap'])
    lc = L(g, x + 3300, y, msg_pin=concat(g, x + 3300, y + 200, 'RemakeMap: [', tag, '] prefs: ',
                                           istr(g, arrfn(g, 'Array_Length', NAME, x + 3150, y + 550, 'PrefCount' + tag,
                                                         arr_pin=gv('PrefKeys', ARR(NAME), x + 3050, y + 600, 'C' + tag))['ReturnValue'], x + 3250, y + 550, 'PrefCountStr' + tag),
                                           ' named, ', istr(g, rk['ReturnValue'], x + 3250, y + 650, 'RawCountStr' + tag), ' raw'), name='LogPrefCount' + tag)
    ex(lk, lc, 'Completed')
    return lc


# ---- BeginPlay: bind onLoadingFinished + onDayStart, then the setup guard (new games don't deliver onLoadingFinished)
bp = g.event('/Script/Engine.Actor', 'ReceiveBeginPlay', [], 'Begin', 0, -4000)
api = modapi(g, 200, -3850, name='BindApi')
evL = g.custom_event('OnLoaded', [], 0, -3600)
evD = g.custom_event('OnDayStart', [('day', INT)], 0, 1500)
evC = g.custom_event('OnRemakeClick', [], 0, 0)
b1 = bind(g, MAPLOAD, api['ReturnValue'], API, 'onLoadingFinished', PKG('/Script/SystemCore'), 'ModAPI_OnEvent__DelegateSignature', evL, 400, -4000, 'BindLoaded')
ex(bp, b1)
b2 = bind(g, MAPLOAD, api['ReturnValue'], API, 'onDayStart', PKG('/Script/SystemCore'), 'ModAPI_OnDayStart__DelegateSignature', evD, 650, -4000, 'BindDay')
ex(b1, b2)
if TRACE:
    trb = api_call(g, 'LogMessage', 900, -4000, name='TraceBegin', doPrependDate='true', Msg='RemakeMap TRACE BeginPlay (%s)' % BUILD)
    ex(b2, trb); pre_guard = trb
else:
    pre_guard = b2
trl = None
if TRACE:
    trl = api_call(g, 'LogMessage', 200, -3600, name='TraceLoaded', doPrependDate='true', Msg='RemakeMap TRACE onLoadingFinished / retry')
    ex(evL, trl)

gr = g.branch(-300, -3300, 'BrReady'); link(g.get('Ready', BOOL, -450, -3150, name='ReadyGet')['Ready'], gr['Condition'])
ex(pre_guard, gr); ex(trl if trl else evL, gr)
pcG = g.call('/Script/Engine.GameplayStatics:GetPlayerController', 'PCGuard', -300, -3000)
pcv = g.call(KSL + ':IsValid', 'PCGuardValid', -150, -3000); link(pcG['ReturnValue'], pcv['Object'])
gp = g.branch(-50, -3300, 'BrHavePC'); link(pcv['ReturnValue'], gp['Condition']); ex(gr, gp, 'else')
srd = g.setv('Ready', BOOL, 150, -3300, value='true', name='SetReady'); ex(gp, srd)
stg0 = g.get('SetupTries', INT, 0, -2800, name='SetupTriesGet')
stl = g.call(KML + ':Less_IntInt', 'SetupTriesLeft', 150, -2800, B='10'); link(stg0['SetupTries'], stl['A'])
bst = g.branch(150, -3000, 'BrSetupRetry'); link(stl['ReturnValue'], bst['Condition']); ex(gp, bst, 'else')
sta = g.call(KML + ':Add_IntInt', 'SetupTriesPlus', 300, -2850, B='1'); link(stg0['SetupTries'], sta['A'])
sst = g.setv('SetupTries', INT, 400, -3000, name='SetSetupTries'); link(sta['ReturnValue'], sst['SetupTries']); ex(bst, sst)
stm = g.call(KSL + ':K2_SetTimer', 'RetrySetup', 650, -3000, FunctionName='OnLoaded', Time='1.000000', bLooping='false')
link(self_node(g, 500, -2850, 'MeSetupTimer')['self'], stm['Object']); ex(sst, stm)

# ---- setup
X, Y = 300, -3600
rdf = api_call(g, 'ReadModTextFile', X, Y, name='ReadDebugFile', modName=CFG, Filename='debug'); ex(srd, rdf)
dfe = g.call(KSTR + ':IsEmpty', 'DebugFileEmpty', X + 250, Y + 200); link(rdf['ReturnValue'], dfe['InString'])
sdb = sv('Debug', BOOL, X + 300, Y, notb(g, dfe['ReturnValue'], X + 450, Y + 200, 'DebugFileThere')); ex(rdf, sdb)
l0 = L(g, X + 700, Y, msg='RemakeMap ready (%s)' % BUILD, name='LogReady'); ex(sdb, l0)
# colony state: save game? day? name? debt?
ga = g.call(ARCO + ':GetArcoSys', 'GetArco', X + 1000, Y); ex(l0, ga)
sa = sv('Arco', OBJ(ARCO), X + 1250, Y, ga['ReturnValue']); ex(ga, sa)
isg = g.call(ARCO + ':IsSaveGame', 'IsSave', X + 1500, Y); link(gv('Arco', OBJ(ARCO), X + 1400, Y + 200, 'S'), isg['self']); ex(sa, isg)
arc = lambda xx, yy, tt: gv('Arco', OBJ(ARCO), xx, yy, tt)
wt = oget(ARCO, 'm_worldTime', OBJ(WTIME), arc(X + 1500, Y + 450, 'W'), X + 1650, Y + 450, 'ArcoWorldTime')
day = oget(WTIME, 'm_day', INT, wt, X + 1850, Y + 450, 'WorldDay')
cn = g.call(ARCO + ':GetColonyName', 'ColonyName', X + 1650, Y + 600); link(arc(X + 1500, Y + 600, 'N'), cn['self'])
dm = g.call(ARCO + ':GetDebtMultiplier', 'DebtMult', X + 1650, Y + 700); link(arc(X + 1500, Y + 700, 'D'), dm['self'])
l1 = L(g, X + 1800, Y, msg_pin=concat(g, X + 1900, Y + 200, 'RemakeMap: arco valid=', bstr(g, ga['out_isValid'], X + 1750, Y + 250, 'ArcoValidStr'),
                                       ' save game=', bstr(g, isg['ReturnValue'], X + 1750, Y + 350, 'IsSaveStr'),
                                       ' day=', istr(g, day, X + 2000, Y + 450, 'DayStr'),
                                       ' colony=', cn['ReturnValue'],
                                       ' debt=', fstr(dm['ReturnValue'], X + 1850, Y + 700, 'ColDebtStr')), name='LogColony')
ex(isg, l1)
dmS = dump_meta(l1, 'then', X + 2300, Y, 'Load')
# option on -> create the button
X, Y = 4400, -3600
oo = api_call(g, 'ReadModOptionValue', X, Y, name='ReadOptButton', optionId=OPT_BTN, fallbackValue='On'); ex(dmS, oo)
dayOk = g.call(KML + ':LessEqual_IntInt', 'FirstDay', X + 100, Y + 350, B='1')
link(oget(WTIME, 'm_day', INT, oget(ARCO, 'm_worldTime', OBJ(WTIME), arc(X - 200, Y + 350, 'W2'), X - 100, Y + 350, 'ArcoWorldTime2'), X, Y + 450, 'WorldDay2'), dayOk['A'])
showOk = andb(g, andb(g, streq(g, oo['ReturnValue'], 'On', X + 100, Y + 200, 'OptOn'), notb(g, isg['ReturnValue'], X + 100, Y + 550, 'NewColony'), X + 250, Y + 250, 'OnAndNew'),
              dayOk['ReturnValue'], X + 300, Y + 350, 'ShowButtonOk')
bOn = g.branch(X + 300, Y, 'BrShowButton'); link(showOk, bOn['Condition']); ex(oo, bOn)
lOff = L(g, X + 550, Y + 400, msg='RemakeMap: no button (option off, loaded save or not day 1)', name='LogNoButton'); ex(bOn, lOff, 'else')
pc = g.call('/Script/Engine.GameplayStatics:GetPlayerController', 'PC', X + 450, Y + 250)
cw = g.create_widget(BTN, X + 600, Y, name='CreateButton'); cw['ReturnValue'].t = BTN_T
link(pc['ReturnValue'], cw['OwningPlayer']); ex(bOn, cw)
sb = sv('Button', BTN_T, X + 850, Y, cw['ReturnValue']); ex(cw, sb)
sl = set_label(LABEL, X + 1100, Y, 'Idle', sb)
an = g.call(UW + ':SetAnchorsInViewport', 'Anchor', X + 1450, Y,
            Anchors='(Minimum=(X=0.500000,Y=0.080000),Maximum=(X=0.500000,Y=0.080000))')
link(gv('Button', BTN_T, X + 1350, Y + 200, 'A'), an['self']); ex(sl, an)
al = g.call(UW + ':SetAlignmentInViewport', 'Align', X + 1700, Y, Alignment='(X=0.500000,Y=0.000000)')
link(gv('Button', BTN_T, X + 1600, Y + 200, 'B'), al['self']); ex(an, al)
av = g.call(UW + ':AddToViewport', 'ShowButton', X + 1950, Y, ZOrder='40')
link(gv('Button', BTN_T, X + 1850, Y + 200, 'C'), av['self']); ex(al, av)
btn = bp_get(g, BTN_CLS, 'Btn', OBJ('/Script/UMG.Button'), gv('Button', BTN_T, X + 2050, Y + 300, 'D'), X + 2150, Y + 300, 'BtnGet')
bc = bind(g, MAPLOAD, btn['Btn'], '/Script/UMG.Button', 'OnClicked', PKG('/Script/UMG'), 'OnButtonClickedEvent__DelegateSignature', evC, X + 2200, Y, 'BindClick')
ex(av, bc)
lS = L(g, X + 2500, Y, msg='RemakeMap: button shown', name='LogShown'); ex(bc, lS)

# ---- OnDayStart(day): log; day > 1 -> remove the button
X, Y = 300, 1500
lD = L(g, X, Y, msg_pin=concat(g, X, Y + 200, 'RemakeMap: onDayStart day=', istr(g, evD['day'], X - 100, Y + 250, 'EvDayStr'),
                                ' worldTime day=', istr(g, oget(WTIME, 'm_day', INT, oget(ARCO, 'm_worldTime', OBJ(WTIME), gv('Arco', OBJ(ARCO), X - 300, Y + 400, 'Day'),
                                                                                    X - 150, Y + 400, 'ArcoWorldTimeDay'), X, Y + 400, 'WorldDayD'), X + 150, Y + 400, 'WorldDayStr')),
       name='LogDay')
ex(evD, lD)
d2 = g.call(KML + ':Greater_IntInt', 'PastDay1', X + 300, Y + 300, B='1'); link(evD['day'], d2['A'])
bgD = gv('Button', BTN_T, X + 300, Y + 500, 'Day')
bD = g.branch(X + 600, Y, 'BrHideButton'); link(andb(g, d2['ReturnValue'], is_valid(g, bgD, X + 450, Y + 500, 'ButtonValidDay'), X + 600, Y + 400, 'HideNow'), bD['Condition'])
ex(lD, bD)
rfp = g.call('/Script/UMG.Widget:RemoveFromParent', 'HideButton', X + 850, Y); link(gv('Button', BTN_T, X + 750, Y + 200, 'Hide'), rfp['self']); ex(bD, rfp)
lH = L(g, X + 1100, Y, msg='RemakeMap: day 1 is over, button removed', name='LogHidden'); ex(rfp, lH)

# ---- OnRemakeClick: first click arms (label changes), second click remakes
X, Y = 300, 0
bA = g.branch(X, Y, 'BrArmed'); link(gv('Armed', BOOL, X - 150, Y + 150), bA['Condition']); ex(evC, bA)
sA = sv('Armed', BOOL, X + 250, Y + 300, value='true'); ex(bA, sA, 'else')
lb2 = set_label(LABEL_ARMED, X + 500, Y + 300, 'Armed', sA)
lA = L(g, X + 1000, Y + 300, msg='RemakeMap: armed (first click)', name='LogArmed'); ex(lb2, lA)
lR = L(g, X + 300, Y, msg='RemakeMap: second click, remaking', name='LogRemake'); ex(bA, lR)
ri = g.call(KML + ':RandomIntegerInRange', 'RollSeed', X + 550, Y + 200, min='1', max='9999999')
ss = sv('NewSeed', INT, X + 600, Y, ri['ReturnValue']); ex(lR, ss)
rf = g.call(KML + ':RandomFloatInRange', 'RollRaw', X + 800, Y + 200, min='0.0', max='1000.0')
sr = sv('NewRaw', DBL, X + 850, Y, rf['ReturnValue']); ex(ss, sr)
seedStr = istr(g, gv('NewSeed', INT, X + 950, Y + 300, 'S'), X + 1050, Y + 300, 'NewSeedStr')
seedName = g.call(KSTR + ':Conv_StringToName', 'NewSeedName', X + 1200, Y + 300); link(seedStr, seedName['InString'])
snp = g.call(GI + ':SetNewMapPreference', 'SetSeed', X + 1400, Y, RuleName='Seed')
link(self_node(g, X + 1250, Y + 450, 'MeSeed')['self'], snp['Context'])
link(seedName['ReturnValue'], snp['choiceName']); link(gv('NewRaw', DBL, X + 1250, Y + 550, 'S'), snp['Value']); ex(sr, snp)
lSd = L(g, X + 1700, Y, msg_pin=concat(g, X + 1700, Y + 200, 'RemakeMap: new seed ', istr(g, gv('NewSeed', INT, X + 1550, Y + 350, 'L'), X + 1650, Y + 350, 'NewSeedLog'),
                                       ' (raw ', fstr(gv('NewRaw', DBL, X + 1550, Y + 450, 'L'), X + 1650, Y + 450, 'NewRawLog'), ')'), name='LogNewSeed')
ex(snp, lSd)
dmC = dump_meta(lSd, 'then', X + 2000, Y - 900, 'Click')
ep = g.call(GI + ':EnterPlay', 'Remake', X + 5700, Y, Filename='', gameType='NEW_GENERATION', saveLocation='SAVED_GAMES', forceFullReplay='false')
link(self_node(g, X + 5550, Y + 200, 'MePlay')['self'], ep['Context']); ex(dmC, ep)
lE = L(g, X + 6000, Y, msg='RemakeMap: EnterPlay(NEW_GENERATION) called', name='LogEnterPlay'); ex(ep, lE)
write('BP_MapLoad', g)


# =========================================================================== variables list + validation
VARS = {
    'BP_MapLoad': [
        ('Debug', 'Boolean'), ('Ready', 'Boolean'), ('SetupTries', 'Integer'), ('Armed', 'Boolean'),
        ('Button', 'WBP_RemakeButton (Object Reference)'), ('Meta', 'Meta Save (Object Reference)'),
        ('Arco', 'Arco Systems (Object Reference)'), ('PrefKeys', 'Name **array**'),
        ('NewSeed', 'Integer'), ('NewRaw', 'Float'),
    ],
}
with open(os.path.join(OUT, 'variables.txt'), 'w') as f:
    for k, vs in VARS.items():
        f.write('## %s\n' % k)
        for n_, t_ in vs: f.write('%s\t%s\n' % (n_, t_))

import re as _re
for gname in ('BP_Startup', 'BP_MapLoad'):
    p = os.path.join(OUT, gname + '.txt')
    n, bad, unl = validate(p)
    txt = open(p, encoding='utf-8').read()
    used = set(_re.findall(r'VariableReference=\(MemberName="([^"]+)",bSelfContext=True\)', txt))
    declared = set(v for v, _ in VARS.get(gname, []))
    print('%-12s %4d nodes  %s  unlinked-exec=%s  undeclared-vars=%s  unused-vars=%s  logs=%d' % (
        gname, n, 'BAD LINKS %s' % bad[:5] if bad else 'links ok', unl[:8], sorted(used - declared),
        sorted(declared - used), txt.count('MemberName="LogMessage"')))
