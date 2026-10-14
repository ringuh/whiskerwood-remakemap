"""Generates the Blueprint paste text (T3D) for the RemakeMap mod into tools/out/.
Usage: JMAP=path/to/Whiskerwood-x.jmap.gz python tools/remakemap_build.py

Assets (/Game/Mods/RemakeMap/):
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

v3 (1.1): no mod option (BP_Startup removed). The button is no longer added to the viewport (it showed over
loading screens and menus) but placed inside the game's HUD: PlayHud ->
the HUD's hideable area = parent of PlayHud.m_toolbar (the FireWatch route: GetAllWidgetsOfClass(PlayHud,
TopLevelOnly=true)[0].m_toolbar.GetParent -> PanelWidget.AddChild). Canvas slot: anchor (0.5, 0.08),
alignment (0.5, 0), position (0, 50) (= 50 px lower than 1.0), auto size. Overlay slot: centre / top, top
padding 136. v3 (TopLevelOnly=false + typed Canvas/Overlay casts) never placed it: "no HUD canvas found".
v4 log: at the start of a new game PlayHud exists but m_toolbar is None (toolbar=false for 30 tries).
v5: target = toolbar parent if the toolbar exists, else the HUD's top-most panel (FindDecendentsOfClasses(PlayHud,
[PanelWidget])[0]); placed once m_uiHasFadedIn (loading screen gone) or after 20 tries; up to 40 tries.
Debug also lists the target panel's children.
v9 dump: GetAllWidgetsOfClass sees only LoadingScreen_C, BP_PlayHud_C and 1 hidden widget (top level only).
v10: walk the HUD tree breadth-first to find the Toolbar, place the button 200 px above it in its parent.
v10 log: nothing after setup (no placed / not-ready / retry lines): the WhileLoop macro pasted from text (no GraphGuid)
stopped the chain. v11: the same walk unrolled level by level (14 levels) with ForEachLoop only.
v11 log: "walking HUD <blank>", level 0 = no class/name although HUDs=1 -> the GetArrayItem on GetAllWidgetsOfClass's
FoundWidgets returned None (same in v4/v5: toolbar=false, no panels). v12: take the HUD with a ForEachLoop instead.
v12 log: found 'Toolbar' (BottomToolbar_C) in HideableElements (CanvasPanel) at try 0, but its size was 0x0 and its
anchors are stretched -> copying them made the button cover the whole screen. v13: wait until the toolbar has a
height; our anchors bottom-centre (0.5, 1), alignment (0.5, 1), position (0, -(height + 200)).
v5 log: PlayHud stays not faded in (m_uiHasFadedIn false), no toolbar, and FindDecendentsOfClasses(PlayHud,
[PanelWidget]) is empty before the dock is placed -> nothing to attach to.
v6: back on the viewport but at ZOrder -100, under all game UI (loading screen, menus, HUD draw over it);
anchors (0.5, 0.08), alignment (0.5, 0), render translation (0, 50).
v6 test: still drawn over everything -> AddToViewport content is a layer above the game's own UI whatever the
ZOrder. v7: AddToPlayerScreen(ZOrder -100) = the player layer the game UI presumably uses (not tested: user asked
for the toolbar binding instead).
v8: child of the bottom toolbar widget (found by class), 200 px above it - see the PlaceButton section.
v8 log: GetAllWidgetsOfClass(Toolbar, TopLevelOnly=false) = 0 on every try although the bottom bar is on screen.
v9: same + a one-time debug dump at try 3: every visible UserWidget (TopLevelOnly true and false) with class,
name and parent name. It hides and fades with the HUD. If the HUD isn't there yet (new game), a one-shot 1 s timer
retries up to 30 times.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from rm_common import *

BUILD = 'v17'
TRACE = False         # test build: every log line ungated. Release builds: False (Debug = RemakeMapConfig\debug.txt)
OUT = os.path.join(os.path.dirname(__file__), 'out')
os.makedirs(OUT, exist_ok=True)

MAPLOAD, BTN = M + 'BP_MapLoad', M + 'WBP_RemakeButton'
HUDW = PA + 'PlayHud'
CANVAS = '/Script/UMG.CanvasPanel'
BTN_CLS, BTN_T = wbp_cls(BTN), wbp_t(BTN)
GI = PA + 'ArcoGameInstance'
META = PA + 'MetaSave'
META_T = OBJ(META)
ARCO, WTIME = PA + 'ArcoSystems', PA + 'WorldTime'
AGC = PA + 'AgentCharacteristics'
LABEL = 'Remake map'
LABEL_ARMED = 'Click again to remake the map'


def write(name, g):
    open(os.path.join(OUT, name + '.txt'), 'w', encoding='utf-8').write(g.text())


def L(g, x, y, msg_pin=None, msg=None, name='Log'):
    return log(g, x, y, msg_pin=msg_pin, msg=msg, name=name, trace=TRACE)


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
dmS = l1
# new colony on day 1 -> create the button, then place it in the HUD
X, Y = 4400, -3600
dayOk = g.call(KML + ':LessEqual_IntInt', 'FirstDay', X + 100, Y + 350, B='1')
link(oget(WTIME, 'm_day', INT, oget(ARCO, 'm_worldTime', OBJ(WTIME), arc(X - 200, Y + 350, 'W2'), X - 100, Y + 350, 'ArcoWorldTime2'), X, Y + 450, 'WorldDay2'), dayOk['A'])
showOk = andb(g, notb(g, isg['ReturnValue'], X + 100, Y + 550, 'NewColony'), dayOk['ReturnValue'], X + 300, Y + 350, 'ShowButtonOk')
bOn = g.branch(X + 300, Y, 'BrShowButton'); link(showOk, bOn['Condition']); ex(dmS, bOn)
lOff = L(g, X + 550, Y + 400, msg='RemakeMap: no button (loaded save or not day 1)', name='LogNoButton'); ex(bOn, lOff, 'else')
pc = g.call('/Script/Engine.GameplayStatics:GetPlayerController', 'PC', X + 450, Y + 250)
cw = g.create_widget(BTN, X + 600, Y, name='CreateButton'); cw['ReturnValue'].t = BTN_T
link(pc['ReturnValue'], cw['OwningPlayer']); ex(bOn, cw)
sb = sv('Button', BTN_T, X + 850, Y, cw['ReturnValue']); ex(cw, sb)
sl = set_label(LABEL, X + 1100, Y, 'Idle', sb)
btn = bp_get(g, BTN_CLS, 'Btn', OBJ('/Script/UMG.Button'), gv('Button', BTN_T, X + 1350, Y + 300, 'D'), X + 1450, Y + 300, 'BtnGet')
bc = bind(g, MAPLOAD, btn['Btn'], '/Script/UMG.Button', 'OnClicked', PKG('/Script/UMG'), 'OnButtonClickedEvent__DelegateSignature', evC, X + 1500, Y, 'BindClick')
ex(sl, bc)

# ---- put the button next to the bottom toolbar, 200 px above it (user, 18:49), in the toolbar's own container so
# it hides with it. The toolbar is nested in BP_PlayHud, and GetAllWidgetsOfClass only sees top-level widgets
# (v9 dump: LoadingScreen_C, BP_PlayHud_C, 1 hidden), NaviUi.FindDecendentsOfClasses matches exact classes only
# (v5: [PanelWidget] found nothing). So walk the HUD tree breadth-first: panels -> GetAllChildren, user widgets ->
# FindDecendentsOfClasses(w, [concrete panel classes]). The first widget that casts to Toolbar is the bar.
# Then AddChild to the bar's parent: canvas -> same anchors as the bar, alignment (0.5, 1), position = the bar's
# top centre - 200 px; overlay -> centre / bottom, bottom padding = bar height + 200; other parents: not added.
# Retry (one-shot 1 s, max 60) until the bar exists and is visible.
TOOLBAR = PA + 'Toolbar'
PANELW_ = '/Script/UMG.PanelWidget'
PANEL_CLASSES = ['/Script/UMG.' + c for c in ('CanvasPanel', 'Overlay', 'HorizontalBox', 'VerticalBox', 'GridPanel', 'UniformGridPanel',
                                               'WrapBox', 'ScrollBox', 'SizeBox', 'Border', 'ScaleBox', 'SafeZone', 'NamedSlot',
                                               'WidgetSwitcher', 'InvalidationBox', 'RetainerBox', 'StackBox', 'BackgroundBlur')]
WA = ARR(WIDGET_T)
evP = g.custom_event('OnPlaceButton', [], X + 1500, Y - 600)
pj = knot(g, X + 1850, Y, 'PlaceJoin'); link(bc['then'], pj['InputPin']); link(evP['then'], pj['InputPin'])
X, Y = 6400, -3600
bPl = g.branch(X, Y, 'BrPlaced')
link(orb(g, gv('Placed', BOOL, X - 200, Y + 200), notb(g, is_valid(g, gv('Button', BTN_T, X - 300, Y + 300, 'P'), X - 150, Y + 300, 'ButtonValidP'), X - 50, Y + 300, 'NoButton'),
         X - 50, Y + 200, 'NothingToPlace'), bPl['Condition'])
link(pj['OutputPin'], bPl['execute'])
ga2 = g.call('/Script/UMG.WidgetBlueprintLibrary:GetAllWidgetsOfClass', 'FindPlayHud', X + 250, Y, WidgetClass=HUDW, TopLevelOnly='true')
ga2['FoundWidgets'].t = ARR(OBJ(HUDW))
link(self_node(g, X + 150, Y + 200, 'MeHud')['self'], ga2['WorldContextObject']); ex(bPl, ga2, 'else')
hn = arrfn(g, 'Array_Length', OBJ(HUDW), X + 450, Y + 250, 'HudCount', arr_pin=ga2['FoundWidgets'])
hasHud = g.call(KML + ':Greater_IntInt', 'HasHud', X + 600, Y + 250, B='0'); link(hn['ReturnValue'], hasHud['A'])
bH = g.branch(X + 550, Y, 'BrHud'); link(hasHud['ReturnValue'], bH['Condition']); ex(ga2, bH)
# take the HUD with a ForEachLoop (GetArrayItem on this out-param array returned None in v4-v11; ForEach works, v9)
ch_ = sv('Hud', UWT, X + 650, Y - 700, tag='Clear')
lpH = foreach(g, ga2['FoundWidgets'], OBJ(HUDW), X + 900, Y - 700, 'HudLoop')
shd = sv('Hud', UWT, X + 1150, Y - 900, lpH['Array Element']); ex(lpH, shd, 'LoopBody')
hud = gv('Hud', UWT, X + 600, Y + 400, 'Use')
# walk level by level (unrolled, ForEachLoop only; a WhileLoop macro pasted from text stopped the chain in v10)
LEVELS = 4
lWk = L(g, X + 700, Y - 400, msg_pin=concat(g, X + 700, Y - 250, 'RemakeMap: walking HUD ', nm(g, hud, X + 600, Y - 150, 'WalkHudName'), ', try ',
                                              istr(g, gv('HudTries', INT, X + 500, Y - 100, 'WK'), X + 600, Y - 100, 'WalkTryStr')), name='LogWalkStart')
ex(bH, ch_); ex(ch_, lpH, 'then', 'Exec'); ex(lpH, lWk, 'Completed')
q0 = arrfn(g, 'Array_Clear', WIDGET_T, X + 800, Y, 'ClearLevel', arr_pin=gv('Level', WA, X + 750, Y + 180, 'C')); ex(lWk, q0)
q1 = arrfn(g, 'Array_Add', WIDGET_T, X + 1050, Y, 'LevelHud', arr_pin=gv('Level', WA, X + 1000, Y + 200, 'Q1'), item_pin=hud); ex(q0, q1)
q3 = sv('TB', WIDGET_T, X + 1550, Y, tag='Clear'); ex(q1, q3)
def append(dst, src_pin, x, y, name):
    n = arrfn(g, 'Array_Append', WIDGET_T, x, y, name, arr_pin=gv(dst, WA, x - 100, y + 200, name))
    t = ARR(WIDGET_T); t['ref'] = True; t['const'] = True; n['SourceArray'].t = t; n['SourceArray'].default = None
    link(src_pin, n['SourceArray'])
    return n
prev = q3
endj = knot(g, X + 1800 + 3400 * LEVELS, Y, 'WalkDone')
for lv in range(LEVELS):
    BX, BY = X + 1800 + 3400 * lv, Y - 900
    t = 'L%d' % lv
    # stop when found or the level is empty
    go = andb(g, notb(g, is_valid(g, gv('TB', WIDGET_T, BX - 300, BY + 1100, 'G' + t), BX - 200, BY + 1100, 'TBValid' + t), BX - 100, BY + 1100, 'TBNot' + t),
              g.call(KML + ':Greater_IntInt', 'LevelHasItems' + t, BX - 100, BY + 1250, B='0')['ReturnValue'], BX, BY + 1150, 'Go' + t)
    link(arrfn(g, 'Array_Length', WIDGET_T, BX - 250, BY + 1300, 'LevelLen' + t, arr_pin=gv('Level', WA, BX - 350, BY + 1350, 'N' + t))['ReturnValue'],
         [n_ for n_ in g.nodes if n_.name == 'LevelHasItems' + t][0]['A'])
    bGo = g.branch(BX, BY + 900, 'BrLevel' + t); link(go, bGo['Condition']); ex(prev, bGo)
    link(bGo['else'], endj['InputPin'])
    cn = arrfn(g, 'Array_Clear', WIDGET_T, BX + 250, BY + 900, 'ClearNext' + t, arr_pin=gv('Next', WA, BX + 200, BY + 1100, 'C' + t)); ex(bGo, cn)
    lp = foreach(g, gv('Level', WA, BX + 350, BY + 1100, 'F' + t), WIDGET_T, BX + 500, BY + 900, 'LevelLoop' + t); ex(cn, lp, 'then', 'Exec')
    el = lp['Array Element']
    dj = knot(g, BX + 1700, BY, 'BodyStart' + t); link(lp['LoopBody'], dj['InputPin'])
    # the bottom bar = class BottomToolbar_C (MetaToolbarButton_C etc. also derive from Toolbar); keep the first
    isBar = andb(g, streq(g, clsname(g, el, BX + 1650, BY + 300, 'BarCls' + t), 'BottomToolbar_C', BX + 1800, BY + 300, 'IsBottomBar' + t),
                 notb(g, is_valid(g, gv('TB', WIDGET_T, BX + 1700, BY + 450, 'K' + t), BX + 1800, BY + 450, 'TBSet' + t), BX + 1900, BY + 450, 'TBFree' + t),
                 BX + 2000, BY + 350, 'TakeBar' + t)
    ctb = g.branch(BX + 1850, BY, 'BrBottomBar' + t); link(isBar, ctb['Condition']); link(dj['OutputPin'], ctb['execute'])
    stb = sv('TB', WIDGET_T, BX + 2100, BY - 200, el, tag='Found' + t); ex(ctb, stb)
    tj = knot(g, BX + 2350, BY, 'ToolbarCheckJoin' + t); link(stb['then'], tj['InputPin']); link(ctb['else'], tj['InputPin'])
    cpw = g.cast(PANELW_, False, BX + 2450, BY, name='AsPanel' + t); link(el, cpw['Object']); link(tj['OutputPin'], cpw['execute'])
    kids = g.call(PANELW_ + ':GetAllChildren', 'Children' + t, BX + 2600, BY + 300); link(cpw['AsPanelWidget'], kids['self']); kids['ReturnValue'].t = WA
    ap1 = append('Next', kids['ReturnValue'], BX + 2800, BY, 'NextChildren' + t); ex(cpw, ap1)
    cuw = g.cast(UW, False, BX + 2700, BY + 600, name='AsUserWidget' + t); link(el, cuw['Object']); ex(cpw, cuw, 'CastFailed')
    fdp = descendants(g, cuw['AsUserWidget'], PANEL_CLASSES, BX + 2950, BY + 600, 'Panels' + t); ex(cuw, fdp)
    ap2 = append('Next', fdp['ReturnValue'], BX + 3200, BY + 600, 'NextPanels' + t); ex(fdp, ap2)
    # level done -> Level = Next
    sl_ = sv('Level', WA, BX + 700, BY + 1500, gv('Next', WA, BX + 600, BY + 1700, 'S' + t), tag=t); ex(lp, sl_, 'Completed')
    prev = sl_
link(prev['then'], endj['InputPin'])
WX, WY = X + 1800 + 3400 * LEVELS, Y
# after the walk
AX, AY = WX + 3600, WY
tbv = g.call('/Script/UMG.Widget:IsVisible', 'ToolbarVisible', AX - 100, AY + 300); link(gv('TB', WIDGET_T, AX - 200, AY + 350, 'V'), tbv['self'])
bF = g.branch(AX, AY, 'BrToolbarFound')
# (v13/v14 also waited for a non-zero desired height: BottomToolbar_C always reports 0 -> never placed. Dropped.)
link(andb(g, is_valid(g, gv('TB', WIDGET_T, AX - 200, AY + 250, 'F'), AX - 100, AY + 200, 'TBValid'), tbv['ReturnValue'], AX - 50, AY + 250, 'TBVisValid'), bF['Condition'])
link(endj['OutputPin'], bF['execute'])
tbp = lambda xx, yy, t: gv('TB', WIDGET_T, xx, yy, t)
par = g.call('/Script/UMG.Widget:GetParent', 'ToolbarParent', AX + 150, AY + 300); link(tbp(AX + 50, AY + 350, 'P'), par['self'])
bpv = g.branch(AX + 250, AY, 'BrParent'); link(is_valid(g, par['ReturnValue'], AX + 250, AY + 300, 'ParentValid'), bpv['Condition']); ex(bF, bpv)
ad = g.call(PANELW_ + ':AddChild', 'AddNextToToolbar', AX + 500, AY); link(par['ReturnValue'], ad['self'])
link(gv('Button', BTN_T, AX + 400, AY + 200, 'Add'), ad['Content']); ex(bpv, ad)
WLL = '/Script/UMG.WidgetLayoutLibrary'
ds = g.call('/Script/UMG.Widget:GetDesiredSize', 'ToolbarSize', AX + 500, AY + 500); link(tbp(AX + 400, AY + 550, 'S'), ds['self'])
dsb = g.call(KML + ':BreakVector2D', 'ToolbarSizeXY', AX + 650, AY + 500); link(ds['ReturnValue'], dsb['InVec'])
# canvas parent: copy the bar's anchors; our bottom centre = the bar's top centre - 200
tsl = g.call(WLL + ':SlotAsCanvasSlot', 'ToolbarCanvasSlot', AX + 700, AY + 300); link(tbp(AX + 600, AY + 350, 'CS'), tsl['Widget'])
osl_ = g.call(WLL + ':SlotAsCanvasSlot', 'OurCanvasSlot', AX + 700, AY + 150); link(gv('Button', BTN_T, AX + 600, AY + 150, 'CS'), osl_['Widget'])
bCs = g.branch(AX + 750, AY, 'BrCanvasSlot')
link(andb(g, is_valid(g, tsl['ReturnValue'], AX + 800, AY + 250, 'TBSlotValid'), is_valid(g, osl_['ReturnValue'], AX + 800, AY + 150, 'OurSlotValid'), AX + 900, AY + 200, 'BothCanvas'), bCs['Condition'])
ex(ad, bCs)
CS = '/Script/UMG.CanvasPanelSlot'
def dmath(fn, a, b, x, y, name):
    n = g.call(KML + ':' + fn, name, x, y)
    for pn, v in (('A', a), ('B', b)):
        if isinstance(v, str): n.set(pn, v)
        else: link(v, n[pn])
    return n['ReturnValue']
hOk_ = g.call(KML + ':Greater_DoubleDouble', 'BarHeightKnown', AX + 1150, AY + 1000, B='1.0'); link(dsb['Y'], hOk_['A'])
hSane = g.call(KML + ':Less_DoubleDouble', 'BarHeightSane', AX + 1150, AY + 1100, B='300.0'); link(dsb['Y'], hSane['A'])
hEff = g.call(KML + ':SelectFloat', 'BarHeight', AX + 1250, AY + 1000, B='100.0'); link(dsb['Y'], hEff['A'])
link(andb(g, hOk_['ReturnValue'], hSane['ReturnValue'], AX + 1250, AY + 1100, 'BarHeightUsable'), hEff['bPickA'])
mp = g.call(KML + ':MakeVector2D', 'OurPos', AX + 1500, AY + 750, X='0.0'); link(dmath('Subtract_DoubleDouble', '0.0', dmath('Add_DoubleDouble', hEff['ReturnValue'], '300.0', AX + 1300, AY + 900, 'HPlus300'), AX + 1400, AY + 900, 'MinusHPlus200'), mp['Y'])
s1 = g.call(CS + ':SetAnchors', 'SlotAnchors', AX + 1050, AY, InAnchors='(Minimum=(X=0.500000,Y=1.000000),Maximum=(X=0.500000,Y=1.000000))'); link(osl_['ReturnValue'], s1['self']); ex(bCs, s1)
s2 = g.call(CS + ':SetAlignment', 'SlotAlign', AX + 1300, AY, InAlignment='(X=0.500000,Y=1.000000)'); link(osl_['ReturnValue'], s2['self']); ex(s1, s2)
s3 = g.call(CS + ':SetPosition', 'SlotPos', AX + 1550, AY); link(osl_['ReturnValue'], s3['self']); link(mp['ReturnValue'], s3['InPosition']); ex(s2, s3)
s4 = g.call(CS + ':SetAutoSize', 'SlotAutoSize', AX + 1800, AY, InbAutoSize='true'); link(osl_['ReturnValue'], s4['self']); ex(s3, s4)
# overlay parent: centre / bottom, bottom padding = bar height + 200
ovs = g.call(WLL + ':SlotAsOverlaySlot', 'OurOverlaySlot', AX + 1000, AY + 1100); link(gv('Button', BTN_T, AX + 900, AY + 1150, 'OS'), ovs['Widget'])
bOs = g.branch(AX + 1050, AY + 900, 'BrOverlaySlot'); link(is_valid(g, ovs['ReturnValue'], AX + 1100, AY + 1100, 'OverlaySlotValid'), bOs['Condition']); ex(bCs, bOs, 'else')
OS = '/Script/UMG.OverlaySlot'
o1 = g.call(OS + ':SetHorizontalAlignment', 'OvHAlign', AX + 1300, AY + 900, InHorizontalAlignment='HAlign_Center'); link(ovs['ReturnValue'], o1['self']); ex(bOs, o1)
o2 = g.call(OS + ':SetVerticalAlignment', 'OvVAlign', AX + 1550, AY + 900, InVerticalAlignment='VAlign_Bottom'); link(ovs['ReturnValue'], o2['self']); ex(o1, o2)
mg = struct_node(g, 'Make', '/Script/SlateCore.Margin', ['Bottom'], AX + 1600, AY + 1150, 'OvMargin')
link(dmath('Add_DoubleDouble', dsb['Y'], '200.0', AX + 1450, AY + 1200, 'BarPlus200'), mg['Bottom'])
o3 = g.call(OS + ':SetPadding', 'OvPad', AX + 1800, AY + 900); link(ovs['ReturnValue'], o3['self']); link(mg['Margin'], o3['InPadding']); ex(o2, o3)
# other parent type: take it out again, log
rfo = g.call('/Script/UMG.Widget:RemoveFromParent', 'NotThisParent', AX + 1300, AY + 1500); link(gv('Button', BTN_T, AX + 1200, AY + 1650, 'RO'), rfo['self']); ex(bOs, rfo, 'else')
lO = L(g, AX + 1550, AY + 1500, msg_pin=concat(g, AX + 1550, AY + 1650, 'RemakeMap: toolbar parent ', nm(g, par['ReturnValue'], AX + 1450, AY + 1750, 'OddName'), ' (',
                                                clsname(g, par['ReturnValue'], AX + 1450, AY + 1850, 'OddClass'), ') is not a canvas/overlay, button not shown'), name='LogOddParent')
ex(rfo, lO)
spO = sv('Placed', BOOL, AX + 1850, AY + 1500, value='true', tag='Odd'); ex(lO, spO)
pk = knot(g, AX + 2100, AY, 'PlacedJoin'); link(s4['then'], pk['InputPin']); link(o3['then'], pk['InputPin'])
sp = sv('Placed', BOOL, AX + 2200, AY, value='true'); ex(pk, sp)
lS = L(g, AX + 2450, AY, msg_pin=concat(g, AX + 2450, AY + 200, 'RemakeMap: button placed above toolbar ', nm(g, tbp(AX + 2250, AY + 300, 'L'), AX + 2350, AY + 300, 'TBName'),
                                         ' (', clsname(g, tbp(AX + 2250, AY + 400, 'L2'), AX + 2350, AY + 400, 'TBClass'), ') in ', nm(g, par['ReturnValue'], AX + 2350, AY + 500, 'ParName'),
                                         ' (', clsname(g, par['ReturnValue'], AX + 2350, AY + 600, 'ParClass'), '), canvas=', bstr(g, is_valid(g, tsl['ReturnValue'], AX + 2250, AY + 700, 'TBSlotValidL'), AX + 2350, AY + 700, 'CanvasStr'),
                                         ', bar ', conv(g, 'Conv_Vector2dToString', ds['ReturnValue'], AX + 2350, AY + 800, 'BarSizeStr'),
                                         ', try ', istr(g, gv('HudTries', INT, AX + 2250, AY + 1000, 'L'), AX + 2350, AY + 1000, 'TriesStr')), name='LogPlaced')
ex(sp, lS)
# not found / not visible yet -> retry
lF = L(g, AX + 300, AY + 2200, msg_pin=concat(g, AX + 300, AY + 2400, 'RemakeMap: toolbar not ready, try ', istr(g, gv('HudTries', INT, AX + 150, AY + 2450, 'F'), AX + 200, AY + 2450, 'TryStrF'),
                                               ': HUDs=', istr(g, hn['ReturnValue'], AX + 200, AY + 2550, 'HudCountF'), ' found=', bstr(g, is_valid(g, tbp(AX + 100, AY + 2650, 'F'), AX + 150, AY + 2650, 'TBFoundF'), AX + 200, AY + 2650, 'TBFoundStr')), name='LogNoToolbar')
rj0 = knot(g, AX + 100, AY + 2200, 'NotReadyJoin'); link(bF['else'], rj0['InputPin']); link(bpv['else'], rj0['InputPin']); link(bH['else'], rj0['InputPin'])
link(rj0['OutputPin'], lF['execute'])
rj = knot(g, AX + 700, AY + 2200, 'RetryJoin'); link(lF['then'], rj['InputPin'])
tg = gv('HudTries', INT, AX + 700, AY + 2450, 'R')
tl = g.call(KML + ':Less_IntInt', 'TriesLeft', AX + 850, AY + 2450, B='60'); link(tg, tl['A'])
bT = g.branch(AX + 900, AY + 2200, 'BrRetry'); link(tl['ReturnValue'], bT['Condition']); link(rj['OutputPin'], bT['execute'])
ta = g.call(KML + ':Add_IntInt', 'TriesPlus', AX + 1050, AY + 2400, B='1'); link(tg, ta['A'])
st = sv('HudTries', INT, AX + 1150, AY + 2200, ta['ReturnValue']); ex(bT, st)
tm = g.call(KSL + ':K2_SetTimer', 'RetryPlace', AX + 1400, AY + 2200, FunctionName='OnPlaceButton', Time='1.000000', bLooping='false')
link(self_node(g, AX + 1300, AY + 2400, 'MePlace')['self'], tm['Object']); ex(st, tm)
lG = L(g, AX + 1200, AY + 2600, msg='RemakeMap: no toolbar found, button not shown', name='LogGaveUp'); ex(bT, lG, 'else')

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
stp = sv('Placed', BOOL, X + 1000, Y + 250, value='true', tag='Day'); ex(rfp, stp)
lH = L(g, X + 1100, Y, msg='RemakeMap: day 1 is over, button removed', name='LogHidden'); ex(stp, lH)

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
dmC = lSd
ep = g.call(GI + ':EnterPlay', 'Remake', X + 5700, Y, Filename='', gameType='NEW_GENERATION', saveLocation='SAVED_GAMES', forceFullReplay='false')
link(self_node(g, X + 5550, Y + 200, 'MePlay')['self'], ep['Context']); ex(dmC, ep)
lE = L(g, X + 6000, Y, msg='RemakeMap: EnterPlay(NEW_GENERATION) called', name='LogEnterPlay'); ex(ep, lE)
write('BP_MapLoad', g)


# =========================================================================== variables list + validation
VARS = {
    'BP_MapLoad': [
        ('Debug', 'Boolean'), ('Ready', 'Boolean'), ('SetupTries', 'Integer'), ('Armed', 'Boolean'),
        ('Button', 'WBP_RemakeButton (Object Reference)'),
        ('Arco', 'Arco Systems (Object Reference)'),
        ('NewSeed', 'Integer'), ('NewRaw', 'Float'), ('Placed', 'Boolean'), ('HudTries', 'Integer'),
        ('Hud', 'User Widget (Object Reference)'), ('Level', 'Widget (Object Reference) **array**'), ('Next', 'Widget (Object Reference) **array**'), ('TB', 'Widget (Object Reference)'),
    ],
}
with open(os.path.join(OUT, 'variables.txt'), 'w') as f:
    for k, vs in VARS.items():
        f.write('## %s\n' % k)
        for n_, t_ in vs: f.write('%s\t%s\n' % (n_, t_))

import re as _re
for gname in ('BP_MapLoad',):
    p = os.path.join(OUT, gname + '.txt')
    n, bad, unl = validate(p)
    txt = open(p, encoding='utf-8').read()
    used = set(_re.findall(r'VariableReference=\(MemberName="([^"]+)",bSelfContext=True\)', txt))
    declared = set(v for v, _ in VARS.get(gname, []))
    print('%-12s %4d nodes  %s  unlinked-exec=%s  undeclared-vars=%s  unused-vars=%s  logs=%d' % (
        gname, n, 'BAD LINKS %s' % bad[:5] if bad else 'links ok', unl[:8], sorted(used - declared),
        sorted(declared - used), txt.count('MemberName="LogMessage"')))
