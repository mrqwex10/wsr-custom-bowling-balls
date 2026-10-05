"""GXLoadTexObj hook: animated + random bowling-ball textures.

Every texture the game draws goes through GXLoadTexObj(obj, mapId). The hook
looks at the texture's image address; if the 64-byte TEX0 header just before
the image data carries our tag, the address is swapped for the right frame /
random pick for this one load, then restored, so the game's own data never
changes (except the random 'stamp' kept in our own header).

Tag layout in TEX0 header bytes 0x30..0x3F (unused by the game):
  0x30  'BANM' animated  |  'BRND' random design  |  'BRAN' random animated set
  BANM/BRND:
    0x34  u16 count        (frames / designs)
    0x36  u16 BANM: frame period in 1/60 s   |  BRND: chosen index, 0xFFFF = not chosen yet
    0x38  u32 stride       bytes between frames / designs (each a full mip chain)
  BRAN (pool = sets*frames images, set-major):
    0x34  u8 sets, u8 frames per set
    0x36  u16 chosen set, 0xFFFF = not chosen yet
    0x38  u16 frame period in 1/60 s, u16 stride >> 5
  0x3C  s32 rel          pool start relative to this texture's own image data
  BTIR (per-player Pro tier, chosen in the Riivolution menu): redirects to another
  tagged TEX0 depending on TIER_CFG[slot]: 'G' = Gold, 'D' = Diamond, anything else = orb
    0x34  u8 slot (0..3 = P1..P4), u8 0
    0x36  s16 base header rel / 32
    0x38  s32 Gold header rel           (bytes, relative to this image data)
    0x3C  s32 Diamond header rel

  BTHM (alley theme): pool index = THEME_CUR (current alley theme, 0 = stock); layout as BRND;
       Whiteout (5) -> 5 + PIN_VAR (one of PIN_VARIANTS dark pin colourways)
  BPIN (Whiteout far-lane pins): pool index = PIN_VAR

The Gold/Diamond tier per player is set by Riivolution memory patches (TIER_CFG).
(v2.0 removed the BDBG/BPAG diagnostic modes to make room for the alley loader and ball trail.)

Also here (v2.0):
  stage   - Bowling stage loader shim: picks the alley theme for Random / Next, and creates
            the ball-trail effect object for this Bowling session.
  trail   - (build_trail, at TRAIL_ADDR) wraps the ball model's per-frame update: while a ball rolls
            down the lane toward the pins, the game's own (unused) 'WS2_bwl_balltail' effect follows
            it, tinted for the player (Diamond = rainbow).
"""
from ppcasm import Asm, branch

GXLOADTEXOBJ = 0x80037780        # stwu r1,-0x10(r1) ; mflr r0 ; ...
GXLOADTEXOBJ_FIRST = 0x9421FFF0  # the instruction we replace
HOOK_ADDR = 0x80001A00           # free low-memory area (same area loaders/codehandlers use)
TB_SHIFT_TICKS_PER_60TH = 989    # (60.75 MHz / 60) >> 10
BOWLING_CODE = (0x80489000, 0x80510000)
TIER_CFG = 0x80001F20            # 4 bytes, one per player; written by the Riivolution tier options
DATA = 0x80001F00                # zeroed at boot:
NORM_IMG = DATA                  # 4 words: per colour slot, the regular-ball image last drawn (BRND: rolled design)
DATA_SIZE = 0x10
# --- alley themes (Random / Next each game) ---------------------------------------------
# The Bowling scene loads its alley at 0x804c79f8: bl LoadStage("Normal.carc" or "100Pin.carc").
# That call is redirected to 'alley', which swaps "Normal.carc" for one of the theme files
# (added to the disc by Riivolution) when THEME_MODE is 'R' (random, never the same alley
# twice in a row) or 'N' (next theme each game).
STAGE_CALL = 0x804c79f8
STAGE_LOAD = 0x80231710
NORMAL_NAME = 0x806818c0         # "Normal.carc" (0x806818cc = "100Pin.carc", left alone)
THEME_MODE, THEME_LAST, THEME_KEY = 0x80001F24, 0x80001F25, 0x80001F26   # KEY must be 0xA5
TRAIL_KEY = 0x80001F27           # 0xA5 = ball trail option on
ALLEY_NAMES = 0x80001F40         # 16-byte name slots
ALLEY_REC = 0x80001F28           # cache record of the themed alley we loaded last (see 'stage')
THEME_CUR, THEME_CUR_KEY = 0x80001F2C, 0x80001F2D   # current alley theme 1..5 (0 = stock) for BTHM, KEY 0xA5
PIN_VAR = 0x80001F2E             # Whiteout pin colourway 0..3 (0xFF = roll on next use), shared by BTHM + BPIN
PIN_VARIANTS, WHITEOUT = 4, 5
PRO_IMG = 0x80001F30             # 4 words: per colour slot, the Pro ball image the tier redirect last resolved
                                 # (BRAN header -> chosen orb set; BANM header byte 0x34 = orb id + 1)
# The game caches loaded archives by path (resource manager [r13-0x3470], list 0 at +4, records:
# path +0x18, data +0x9c) in a heap that lives across games. Stock always asks for 'Normal.carc'
# (cache hit), but Random/Next ask for a new name each game -> the 3rd alley no longer fit (hang).
# So before loading the next theme, the previous theme's record is destroyed and its data freed.
RES_MGR_SDA = -0x3470
RES_FIND = 0x80231af4            # (mgr, list, path) -> record or 0
LIST_NEXT = 0x8010bc00           # (list, obj) -> next (obj 0 = first)
RECORD_DTOR = 0x8024095c         # (record, 1): unlink from the cache, free the record
FREE = 0x801c1c90                # operator delete
KEY = 0xA5
# --- ball trail ------------------------------------------------------------------------
BALL_UPDATE = 0x804d0e38         # ball model per-frame update (virtual); world matrix at obj+0x44
BALL_UPDATE_FIRST = 0x9421FF30   # stwu r1,-0xd0(r1)
NEW = 0x801c1c48                 # operator new(size)
EFFECT_CTOR = 0x8023ea98         # (obj, name, 0) - same as the pins' 'WS2_bwl_pinltail'
EFFECT_SIZE = 0x118
EFFECT_START, EFFECT_KILL = 0x8023e91c, 0x8023e82c   # kill = stop emitting, particles finish, effect released
EFFECT_SET_MTX, EFFECT_UPDATE = 0x8023e47c, 0x8023e28c
EFFECT_SET_COLOR = 0x8023e5e0    # (obj, r, g, b, a, 3): multiplies the effect's colours
TRAIL_ADDR = 0x80002000          # trail code (free low memory after our data block); starts with trail_init
TRAIL_END = 0x80002700           # code limit; trail matrix + effect name follow
# trail colours: P1..P4 normal ball (the stock ball colours), Pro orb, Gold; Diamond = cycling rainbow
TRAIL_COLORS = [(70, 150, 255), (255, 70, 70), (70, 230, 100), (255, 220, 50), (190, 110, 255), (255, 190, 50)]
# Pro orbs, in make_orbs.ORDER (holo, venom, inferno, blackhole, arcane, dragoneye): the trail matches the orb
ORB_COLORS = [(120, 220, 255), (170, 255, 40), (255, 100, 20), (255, 50, 190), (150, 70, 255), (255, 170, 0)]
LANE_HALF = 0x41100000           # 9.0: only the player's own lane (x = 0); CPU Miis bowl on the neighbouring lanes
RAINBOW_SHIFT = 16               # hue step = time base >> 16 (~0.9 kHz): one full cycle every ~1.7 s
TRAIL_N = 5                      # particle bursts in flight (pool of effect objects, reused round-robin)
TRAIL_POOL = 0x80002760          # the effect objects live here (TRAIL_N x EFFECT_SIZE, up to 0x80002CD8):
                                 # allocating them each Bowling load fragmented the heap the alleys share,
                                 # and the 3rd/4th alley load hung - so nothing is allocated any more
TRAIL_SPACING = 2                # a new burst every 2nd frame while the ball rolls
TRAIL_EFFS = 0x80001F90          # TRAIL_N pointers
TRAIL_ON, TRAIL_OBJ, TRAIL_Z = 0x80001FC0, 0x80001FC4, 0x80001FC8
TRAIL_TICK, TRAIL_NEXT, TRAIL_TINT = 0x80001FCC, 0x80001FD0, 0x80001FD4   # mode byte: 0 own colours,
                                 # 1 = tint to the ball, 2 = match the ball (style + colour per design)
TRAIL_PX, TRAIL_PY, TRAIL_PZ = 0x80001FD8, 0x80001FDC, 0x80001FE0          # ball position last frame
TRAIL_LEAD = 0x80001FE4          # float: bursts are dropped this many frames ahead of the ball
LEAD_FRAMES = 2.0                # (a burst takes a few frames to show; a fast ball would outrun it)
TRAIL_EFF = TRAIL_EFFS
TRAIL_MTX = 0x80002700           # 3x4: identity rotation + burst position
TRAIL_NAME = 0x80002730          # effect name (32 bytes), written by the Ball trail choice
# Ball trail styles: (menu label, effect in Effect/BwlScene/effect.carc, tint to the ball colour)
TRAIL_STYLES = [('Match ball (Auto)', 'WS2_bwl_pin_hit_a', 2), ('Aura', 'WS2_bwl_pin_hit_a', 1), ('Sparks', 'WS2_bwl_pin_hit_b', 1)]
NAME_LETTER = 16                 # 'WS2_bwl_pin_hit_a' (aura) / '..._b' (sparks): only this letter differs
# Match ball: (aura, sparks) per design, each None, (r, g, b) or 'rainbow'; balls with both alternate them.
# design ids: 0-7 regular pool (make_pool.POOL order), 8-13 Pro orbs (make_orbs.ORDER), 14 Gold, 15 Diamond
WHITE = (255, 255, 255)
MATCH_PROFILES = [
    ((40, 190, 255), (220, 250, 255)),   # riptide: ocean + spray
    ((110, 80, 255), WHITE),             # galaxy: nebula + stars
    ('rainbow', None),                   # tie-dye
    ('rainbow', 'rainbow'),              # hyperspin
    ((255, 215, 30), None),              # smiley
    ((40, 230, 90), (255, 215, 60)),     # emerald 420: green + gold flecks
    (None, 'rainbow'),                   # stained glass: coloured glints
    ((255, 60, 200), (60, 230, 255)),    # synthwave: pink + cyan
    ((120, 220, 255), WHITE),            # holographic
    ((170, 255, 40), None),              # venom swirl
    ((255, 100, 20), (255, 200, 40)),    # inferno: fire + embers
    ((255, 50, 190), WHITE),             # black hole: + stars
    ((150, 70, 255), (200, 160, 255)),   # arcane void
    ((255, 170, 0), (255, 90, 20)),      # dragon's eye
    ((255, 190, 50), (255, 245, 200)),   # gold: + glitter
    ('rainbow', WHITE),                  # prismatic diamond: + sparkle
]
POOL_SIZE, ORB_COUNT = 8, 6
# (short bursts only: a long effect still alive when Bowling reloads hung the game - 'Stars'/perfect_kira did)
Z_FOUL, Z_PINS, Y_MIN = 0xBF800000, 0xC33A0000, 0x3F000000   # -1.0, -186.0, +0.5 (float bits)
STAGE_ADDR = 0x80002CE0          # the stage shim (own block, up to 0x80003000)
ALLEY_FILES = ['Cosmic.carc', 'Synthwave.carc', 'Aurora.carc', 'Lava.carc', 'Whiteout.carc']


def _frame(a, tag):
    """r5 = (time / period) % count ; period in r8 (1/60 s), count in r9. Clobbers r6-r8."""
    a.label('tb' + tag)
    a.mftbu('r5')
    a.mftb('r6')
    a.mftbu('r7')
    a.cmpw('r5', 'r7')
    a.bne('tb' + tag)
    a.slwi('r5', 'r5', 22)
    a.srwi('r6', 'r6', 10)
    a.orr('r5', 'r5', 'r6')             # time base >> 10 (wraps after ~20 hours)
    a.mulli('r8', 'r8', TB_SHIFT_TICKS_PER_60TH)
    a.divwu('r5', 'r5', 'r8')
    a.divwu('r7', 'r5', 'r9')
    a.mullw('r7', 'r7', 'r9')
    a.subf('r5', 'r7', 'r5')


def _roll(a):
    """r5 = pseudo-random % r9, mixed with the slot address so players differ. Clobbers r6, r7."""
    a.mftb('r6')
    a.xor('r6', 'r6', 'r11')
    a.lis('r7', 0x9E37)
    a.ori('r7', 'r7', 0x79B1)
    a.mullw('r6', 'r6', 'r7')
    a.srwi('r6', 'r6', 16)
    a.divwu('r7', 'r6', 'r9')
    a.mullw('r7', 'r7', 'r9')
    a.subf('r5', 'r7', 'r6')


def _pin_var(a, tag):
    """r5 = Whiteout pin colourway 0..PIN_VARIANTS-1, rolled once and kept in PIN_VAR. Clobbers r6-r9."""
    a.lis('r8', PIN_VAR >> 16)
    a.lbz('r5', PIN_VAR & 0xFFFF, 'r8')
    a.cmplwi('r5', PIN_VARIANTS)
    a.blt('pvok_' + tag)
    a.li('r9', PIN_VARIANTS)
    _roll(a)
    a.lis('r8', PIN_VAR >> 16)
    a.stb('r5', PIN_VAR & 0xFFFF, 'r8')
    a.label('pvok_' + tag)


def _mark(a):
    """Remember (time-base upper) that one of our ball textures is being drawn. Clobbers r5, r6."""
    a.mftbu('r6')
    a.lis('r5', DATA >> 16)
    a.stw('r6', ACTIVE & 0xFFFF, 'r5')


def build():
    a = Asm(HOOK_ADDR)
    a.label('hook')                     # r3 = GXTexObj*, r4 = map id (keep both!)
    a.lwz('r12', 0x0C, 'r3')            # image3: low 24 bits = phys >> 5
    a.rlwinm('r11', 'r12', 5, 3, 26)    # r11 = physical address of image data
    # --- only look at addresses whose header we can read safely ---
    a.lis('r10', 0x0180)
    a.cmplw('r11', 'r10')
    a.bge('mem2')
    a.cmplwi('r11', 0x4000)             # MEM1: 0x4000 .. 0x017FFFFF
    a.blt('passthru')
    a.b('have')
    a.label('mem2')                     # MEM2: 0x10000100 .. 0x13FFFFFF
    a.lis('r10', 0x1000)
    a.addi('r10', 'r10', 0x100)
    a.cmplw('r11', 'r10')
    a.blt('passthru')
    a.lis('r10', 0x1400)
    a.cmplw('r11', 'r10')
    a.bge('passthru')
    a.label('have')
    a.oris('r11', 'r11', 0x8000)        # -> cached virtual address
    a.label('dispatch')                 # (tier redirects come back here with a new r11)
    a.lwz('r10', -0x40, 'r11')          # must be a TEX0 header...
    a.lis('r9', 0x5445)
    a.ori('r9', 'r9', 0x5830)           # 'TEX0'
    a.cmpw('r10', 'r9')
    a.bne('passthru')
    a.lwz('r10', -0x10, 'r11')          # ...with one of our tags
    a.lis('r9', 0x4241)
    a.ori('r9', 'r9', 0x4E4D)           # 'BANM'
    a.cmpw('r10', 'r9')
    a.beq('anim')
    a.lis('r9', 0x4252)
    a.ori('r9', 'r9', 0x4E44)           # 'BRND'
    a.cmpw('r10', 'r9')
    a.beq('rnd')
    a.lis('r9', 0x4254)
    a.ori('r9', 'r9', 0x4952)           # 'BTIR'
    a.cmpw('r10', 'r9')
    a.beq('tier')
    a.lis('r9', 0x4254)
    a.ori('r9', 'r9', 0x484D)           # 'BTHM'
    a.cmpw('r10', 'r9')
    a.beq('theme')
    a.lis('r9', 0x4250)
    a.ori('r9', 'r9', 0x494E)           # 'BPIN'
    a.cmpw('r10', 'r9')
    a.beq('pinvar')
    a.lis('r9', 0x4252)
    a.ori('r9', 'r9', 0x414E)           # 'BRAN'
    a.cmpw('r10', 'r9')
    a.bne('passthru')

    # --- random animated set: roll a set once per load, then animate it ---
    a.lbz('r9', -0x0C, 'r11')           # sets
    a.lhz('r5', -0x0A, 'r11')           # chosen set
    a.cmplwi('r5', 0xFFFF)
    a.bne('ran_ok')
    _roll(a)
    a.sth('r5', -0x0A, 'r11')
    a.label('ran_ok')
    a.lbz('r9', -0x0B, 'r11')           # frames per set
    a.mullw('r10', 'r5', 'r9')          # first frame of the set
    a.lhz('r8', -0x08, 'r11')           # period
    _frame(a, '_ran')
    a.add('r5', 'r5', 'r10')
    a.lhz('r8', -0x06, 'r11')
    a.slwi('r8', 'r8', 5)               # stride
    a.lwz('r7', -0x04, 'r11')           # rel
    a.b('subst')

    # --- Pro tier per player: pick orb / Gold / Diamond header, then dispatch it
    a.label('tier')
    a.lbz('r9', -0x0C, 'r11')           # player slot 0..3
    a.lis('r8', TIER_CFG >> 16)
    a.addi('r8', 'r8', TIER_CFG & 0xFFFF)
    a.add('r8', 'r8', 'r9')
    a.lbz('r8', 0, 'r8')                # chosen tier for this player
    a.cmpwi('r8', ord('D'))
    a.beq('tier2')
    a.cmpwi('r8', ord('G'))
    a.beq('tier1')
    a.lha('r7', -0x0A, 'r11')           # base orb
    a.slwi('r7', 'r7', 5)
    a.b('tier_go')
    a.label('tier1')
    a.lwz('r7', -0x08, 'r11')
    a.b('tier_go')
    a.label('tier2')
    a.lwz('r7', -0x04, 'r11')
    a.label('tier_go')
    a.add('r11', 'r11', 'r7')           # -> target TEX0 header
    a.addi('r11', 'r11', 0x40)          # -> its image data
    a.slwi('r10', 'r9', 2)              # remember it for this slot (the ball trail matches the orb)
    a.lis('r8', 0x8000)
    a.add('r8', 'r8', 'r10')
    a.stw('r11', PRO_IMG & 0xFFFF, 'r8')
    a.b('dispatch')

    # --- random design: pick once per load, remember in the header ---------
    a.label('rnd')
    a.lbz('r9', -0x0B, 'r11')           # count (byte 0x35; 0x34 = colour slot + 1)
    a.lhz('r5', -0x0A, 'r11')           # stamp
    a.cmplwi('r5', 0xFFFF)
    a.bne('rnd_ok')
    _roll(a)
    a.sth('r5', -0x0A, 'r11')
    a.label('rnd_ok')
    a.lbz('r10', -0x0C, 'r11')          # remember this slot's ball (the ball trail matches the design)
    a.cmpwi('r10', 0)
    a.beq('rnd_go')
    a.slwi('r10', 'r10', 2)
    a.lis('r8', 0x8000)
    a.add('r8', 'r8', 'r10')
    a.stw('r11', (NORM_IMG - 4) & 0xFFFF, 'r8')
    a.label('rnd_go')
    a.lwz('r8', -0x08, 'r11')           # stride
    a.lwz('r7', -0x04, 'r11')           # rel
    a.b('subst')

    # --- alley theme: pool index = current alley theme (0 = stock), e.g. the live pins ---
    a.label('theme')
    a.lhz('r9', -0x0C, 'r11')           # count
    a.lis('r8', THEME_CUR >> 16)
    a.lbz('r5', THEME_CUR & 0xFFFF, 'r8')
    a.lbz('r6', THEME_CUR_KEY & 0xFFFF, 'r8')
    a.cmpwi('r6', KEY)
    a.bne('theme_0')
    a.cmplw('r5', 'r9')
    a.blt('theme_ok')
    a.label('theme_0')
    a.li('r5', 0)
    a.label('theme_ok')
    a.cmpwi('r5', WHITEOUT)             # Whiteout: one of the dark pin colourways
    a.bne('theme_go')
    _pin_var(a, 'th')
    a.addi('r5', 'r5', WHITEOUT)
    a.label('theme_go')
    a.lwz('r8', -0x08, 'r11')           # stride
    a.lwz('r7', -0x04, 'r11')           # rel
    a.b('subst')

    # --- Whiteout far-lane pins (in the alley): pool index = the same pin colourway ---
    a.label('pinvar')
    _pin_var(a, 'pv')
    a.lhz('r9', -0x0C, 'r11')           # count
    a.cmplw('r5', 'r9')
    a.blt('pv_go')
    a.li('r5', 0)
    a.label('pv_go')
    a.lwz('r8', -0x08, 'r11')
    a.lwz('r7', -0x04, 'r11')
    a.b('subst')

    # --- animated: frame from the time base (steady speed) ----------------
    a.label('anim')
    a.lbz('r9', -0x0B, 'r11')           # count (byte 0x35; 0x34 = orb id + 1 on Pro orbs)
    a.lhz('r8', -0x0A, 'r11')           # period, 1/60 s units
    _frame(a, '_anim')
    a.lwz('r8', -0x08, 'r11')           # stride
    a.lwz('r7', -0x04, 'r11')           # rel

    # --- swap the image address for this one load --------------------------
    a.label('subst')                    # r5 = index, r8 = stride, r7 = rel, r11 = own image data
    a.mullw('r8', 'r8', 'r5')
    a.add('r8', 'r8', 'r7')
    a.add('r8', 'r8', 'r11')            # new image virtual address
    a.rlwinm('r8', 'r8', 27, 8, 31)     # -> (phys >> 5), 24 bits
    a.rlwinm('r7', 'r12', 0, 0, 7)      # keep the register-id byte
    a.orr('r8', 'r8', 'r7')
    a.stwu('r1', -0x20, 'r1')
    a.mflr('r0')
    a.stw('r0', 0x24, 'r1')
    a.stw('r31', 0x1C, 'r1')
    a.stw('r30', 0x18, 'r1')
    a.mr('r31', 'r3')
    a.mr('r30', 'r12')
    a.stw('r8', 0x0C, 'r3')
    a.bl('tramp')                       # run the real GXLoadTexObj
    a.lwz('r0', 0x0C, 'r31')
    a.rlwimi('r0', 'r30', 0, 8, 31)     # put the original address back
    a.stw('r0', 0x0C, 'r31')
    a.lwz('r0', 0x24, 'r1')
    a.lwz('r31', 0x1C, 'r1')
    a.lwz('r30', 0x18, 'r1')
    a.mtlr('r0')
    a.addi('r1', 'r1', 0x20)
    a.blr()

    a.label('passthru')
    a.label('tramp')
    a.word(GXLOADTEXOBJ_FIRST)          # the instruction we overwrote
    a.b(GXLOADTEXOBJ + 4)

    code = a.assemble()
    assert HOOK_ADDR + len(code) <= DATA, hex(HOOK_ADDR + len(code))
    return code, a


def patches():
    """[(address, bytes, original-or-None)] for Riivolution <memory> patches."""
    code, a = build()
    return [(HOOK_ADDR, code, None),
            (DATA, bytes(DATA_SIZE), None),
            (PRO_IMG, bytes(16), None),
            (GXLOADTEXOBJ, branch(GXLOADTEXOBJ, HOOK_ADDR).to_bytes(4, 'big'), GXLOADTEXOBJ_FIRST)]


def build_trail():
    """Trail code (separate block at TRAIL_ADDR).
      trail_init (TRAIL_ADDR, called by 'stage' when Bowling sets up): TRAIL_N effect objects
      trail      wraps the ball model's per-frame update: while a ball rolls down the lane toward the
                 pins, every TRAIL_SPACING frames one effect object is restarted at the ball (a particle
                 burst that stays where it was dropped), tinted for the ball (Diamond = rainbow)."""
    a = Asm(TRAIL_ADDR)
    a.label('trail_init')               # (re)build the effect objects in place, every Bowling load
    a.stwu('r1', -0x20, 'r1')
    a.mflr('r0')
    a.stw('r0', 0x24, 'r1')
    a.stw('r31', 0x1C, 'r1')
    a.stw('r30', 0x18, 'r1')
    a.lis('r31', 0x8000)
    a.li('r30', 0)
    a.label('ti_loop')
    a.mulli('r3', 'r30', EFFECT_SIZE)
    a.lis('r4', TRAIL_POOL >> 16)
    a.ori('r4', 'r4', TRAIL_POOL & 0xFFFF)
    a.add('r3', 'r3', 'r4')
    a.lis('r4', TRAIL_NAME >> 16)
    a.ori('r4', 'r4', TRAIL_NAME & 0xFFFF)
    a.li('r5', 0)
    a.bl(EFFECT_CTOR)
    a.slwi('r4', 'r30', 2)
    a.add('r4', 'r4', 'r31')
    a.stw('r3', TRAIL_EFFS & 0xFFFF, 'r4')
    a.addi('r30', 'r30', 1)
    a.cmpwi('r30', TRAIL_N)
    a.blt('ti_loop')
    a.li('r0', 0)
    for addr in (TRAIL_ON, TRAIL_OBJ, TRAIL_TICK, TRAIL_NEXT):
        a.stw('r0', addr & 0xFFFF, 'r31')
    a.lwz('r0', 0x24, 'r1')
    a.lwz('r31', 0x1C, 'r1')
    a.lwz('r30', 0x18, 'r1')
    a.mtlr('r0')
    a.addi('r1', 'r1', 0x20)
    a.blr()

    a.label('trail')                    # entry of the ball update is patched with 'b trail'
    a.stwu('r1', -0x20, 'r1')
    a.mflr('r0')
    a.stw('r0', 0x24, 'r1')
    a.stw('r31', 0x1C, 'r1')
    a.mr('r31', 'r3')
    a.bl('ball_orig')                   # the real update first (args untouched)
    a.mr('r3', 'r31')
    a.bl('trail_logic')
    a.lwz('r0', 0x24, 'r1')
    a.lwz('r31', 0x1C, 'r1')
    a.mtlr('r0')
    a.addi('r1', 'r1', 0x20)
    a.blr()
    a.label('ball_orig')
    a.word(BALL_UPDATE_FIRST)
    a.b(BALL_UPDATE + 4)

    a.label('trail_logic')              # r3 = ball object
    a.stwu('r1', -0x30, 'r1')
    a.mflr('r0')
    a.stw('r0', 0x34, 'r1')
    a.stw('r31', 0x2C, 'r1')
    a.stw('r30', 0x28, 'r1')
    a.stw('r29', 0x24, 'r1')
    a.stw('r28', 0x20, 'r1')
    a.mr('r29', 'r3')
    a.lis('r31', 0x8000)
    a.lwz('r0', TRAIL_EFFS & 0xFFFF, 'r31')
    a.cmpwi('r0', 0)
    a.beq('t_out')                      # no effect objects this session
    a.lwz('r5', 0x70, 'r29')            # z (float bits)
    a.lwz('r6', 0x60, 'r29')            # y
    a.li('r7', 0)                       # rolling on the lane between foul line and pins?
    a.lis('r8', Z_FOUL >> 16)
    a.cmplw('r5', 'r8')
    a.ble('t_zone')                     # z >= -1 (or positive)
    a.lis('r8', Z_PINS >> 16)
    a.cmplw('r5', 'r8')
    a.bge('t_zone')                     # z <= -186
    a.lwz('r9', 0x50, 'r29')            # |x| < 9: the player's own lane
    a.rlwinm('r9', 'r9', 0, 1, 31)
    a.lis('r8', LANE_HALF >> 16)
    a.cmplw('r9', 'r8')
    a.bge('t_zone')
    a.cmpwi('r6', 0)
    a.blt('t_zone')                     # y < 0: a reflection / the ball return
    a.lis('r8', Y_MIN >> 16)
    a.cmplw('r6', 'r8')
    a.blt('t_zone')                     # y < 0.5
    a.li('r7', 1)
    a.label('t_zone')
    a.lwz('r8', TRAIL_OBJ & 0xFFFF, 'r31')
    a.cmplw('r8', 'r29')
    a.beq('t_same')
    a.cmpwi('r7', 0)                    # another ball: only take it over if it's on the lane...
    a.beq('t_out')
    a.lwz('r0', TRAIL_ON & 0xFFFF, 'r31')
    a.cmpwi('r0', 0)
    a.bne('t_out')                      # ...and no roll is in progress
    a.stw('r29', TRAIL_OBJ & 0xFFFF, 'r31')
    a.stw('r5', TRAIL_Z & 0xFFFF, 'r31')
    for off, prev in ((0x50, TRAIL_PX), (0x60, TRAIL_PY), (0x70, TRAIL_PZ)):
        a.lwz('r9', off, 'r29')
        a.stw('r9', prev & 0xFFFF, 'r31')
    a.b('t_out')
    a.label('t_same')
    a.lwz('r8', TRAIL_Z & 0xFFFF, 'r31')
    a.cmplw('r5', 'r8')
    a.beq('t_out')                      # not moved (second update this frame / paused): change nothing
    a.stw('r5', TRAIL_Z & 0xFFFF, 'r31')
    a.cmpwi('r7', 0)
    a.beq('t_off')
    a.cmplw('r5', 'r8')
    a.blt('t_off')                      # |z| shrinking: moving back toward the player
    # burst position = ball + (ball - last frame) * LEAD   (slightly ahead along its path)
    a.lfs('f4', TRAIL_LEAD & 0xFFFF, 'r31')
    for off, prev, m in ((0x50, TRAIL_PX, 0x0C), (0x60, TRAIL_PY, 0x1C), (0x70, TRAIL_PZ, 0x2C)):
        a.lfs('f1', off, 'r29')
        a.lfs('f2', prev & 0xFFFF, 'r31')
        a.fsubs('f3', 'f1', 'f2')
        a.fmadds('f3', 'f3', 'f4', 'f1')
        a.stfs('f3', (TRAIL_MTX + m) & 0xFFFF, 'r31')
        a.stfs('f1', prev & 0xFFFF, 'r31')
    a.li('r0', 1)
    a.stw('r0', TRAIL_ON & 0xFFFF, 'r31')
    a.lwz('r9', TRAIL_TICK & 0xFFFF, 'r31')
    a.addi('r10', 'r9', 1)
    a.stw('r10', TRAIL_TICK & 0xFFFF, 'r31')
    a.li('r10', TRAIL_SPACING)
    a.divwu('r28', 'r9', 'r10')         # burst number (its parity alternates aura / sparks)
    a.mullw('r11', 'r28', 'r10')
    a.cmplw('r11', 'r9')
    a.bne('t_out')                      # not a burst frame
    # --- next effect object, round-robin ---
    a.lwz('r12', TRAIL_NEXT & 0xFFFF, 'r31')
    a.addi('r10', 'r12', 1)
    a.cmpwi('r10', TRAIL_N)
    a.blt('t_nx')
    a.li('r10', 0)
    a.label('t_nx')
    a.stw('r10', TRAIL_NEXT & 0xFFFF, 'r31')
    a.slwi('r9', 'r12', 2)
    a.add('r9', 'r9', 'r31')
    a.lwz('r30', TRAIL_EFFS & 0xFFFF, 'r9')
    a.cmpwi('r30', 0)
    a.beq('t_out')
    # --- colour (r4, r5, r6) and effect letter (r7, 0 = keep) for this burst ---
    a.li('r4', 255)
    a.li('r5', 255)
    a.li('r6', 255)
    a.li('r7', 0)
    a.lbz('r0', TRAIL_TINT & 0xFFFF, 'r31')
    a.cmpwi('r0', 0)
    a.beq('c_store')                    # this style keeps its own colours
    a.lwz('r9', 0x78, 'r29')
    a.rlwinm('r10', 'r9', 0, 30, 31)    # slot
    a.rlwinm('r11', 'r9', 0, 29, 29)    # Pro?
    a.cmpwi('r0', 2)
    a.bne('c_ball')
    # ---- match ball: find the design id (r10) ----
    a.cmpwi('r11', 0)
    a.bne('m_pro')
    a.rlwinm('r11', 'r9', 2, 28, 29)    # regular ball: rolled design of this slot
    a.lis('r12', 0x8000)
    a.add('r12', 'r12', 'r11')
    a.lwz('r12', NORM_IMG & 0xFFFF, 'r12')
    a.cmpwi('r12', 0)
    a.beq('m_default')
    a.lwz('r11', -0x10, 'r12')
    a.lis('r8', 0x4252)
    a.ori('r8', 'r8', 0x4E44)           # 'BRND'
    a.cmpw('r11', 'r8')
    a.bne('m_default')
    a.lhz('r10', -0x0A, 'r12')
    a.cmplwi('r10', POOL_SIZE)
    a.bge('m_default')
    a.b('m_profile')
    a.label('m_pro')
    a.lis('r12', TIER_CFG >> 16)
    a.ori('r12', 'r12', TIER_CFG & 0xFFFF)
    a.add('r12', 'r12', 'r10')
    a.lbz('r12', 0, 'r12')
    a.li('r10', POOL_SIZE + ORB_COUNT + 1)    # Diamond
    a.cmpwi('r12', ord('D'))
    a.beq('m_profile')
    a.li('r10', POOL_SIZE + ORB_COUNT)        # Gold
    a.cmpwi('r12', ord('G'))
    a.beq('m_profile')
    a.rlwinm('r11', 'r9', 2, 28, 29)
    a.lis('r12', 0x8000)
    a.add('r12', 'r12', 'r11')
    a.lwz('r12', PRO_IMG & 0xFFFF, 'r12')
    a.cmpwi('r12', 0)
    a.beq('m_default')
    a.lwz('r11', -0x10, 'r12')
    a.lis('r8', 0x4252)
    a.ori('r8', 'r8', 0x414E)           # 'BRAN': random orb set
    a.cmpw('r11', 'r8')
    a.bne('m_banm')
    a.lhz('r10', -0x0A, 'r12')
    a.cmplwi('r10', ORB_COUNT)
    a.bge('m_default')
    a.addi('r10', 'r10', POOL_SIZE)
    a.b('m_profile')
    a.label('m_banm')
    a.lis('r8', 0x4241)
    a.ori('r8', 'r8', 0x4E4D)           # 'BANM' + orb id
    a.cmpw('r11', 'r8')
    a.bne('m_default')
    a.lbz('r10', -0x0C, 'r12')
    a.cmpwi('r10', 0)
    a.beq('m_default')
    a.cmplwi('r10', ORB_COUNT)
    a.bgt('m_default')
    a.addi('r10', 'r10', POOL_SIZE - 1)
    a.label('m_profile')                # r10 = design id -> profile entry (aura rgb+flags, sparks rgb+flags)
    a.slwi('r10', 'r10', 3)
    a.lis('r12', 0)                     # (patched below to the profile table)
    a.label('m_tab_lo')
    a.ori('r12', 'r12', 0)
    a.add('r12', 'r12', 'r10')
    a.lbz('r8', 3, 'r12')               # aura flags
    a.lbz('r11', 7, 'r12')              # sparks flags
    a.li('r7', ord('a'))
    a.cmpwi('r11', 0)
    a.beq('m_pick')                     # aura only
    a.li('r7', ord('b'))
    a.addi('r12', 'r12', 4)
    a.cmpwi('r8', 0)
    a.beq('m_pick')                     # sparks only
    a.rlwinm('r8', 'r28', 0, 31, 31)    # both: alternate burst by burst (r28 = burst number)
    a.cmpwi('r8', 0)
    a.bne('m_pick')
    a.li('r7', ord('a'))
    a.addi('r12', 'r12', -4)
    a.label('m_pick')
    a.lbz('r8', 3, 'r12')
    a.rlwinm('r8', 'r8', 0, 30, 30)     # flag 2: rainbow
    a.cmpwi('r8', 0)
    a.bne('c_rainbow')
    a.lbz('r4', 0, 'r12')
    a.lbz('r5', 1, 'r12')
    a.lbz('r6', 2, 'r12')
    a.b('c_store')
    a.label('m_default')                # unknown design: aura in the ball's colour
    a.li('r7', ord('a'))
    a.lwz('r9', 0x78, 'r29')
    a.rlwinm('r10', 'r9', 0, 30, 31)
    a.rlwinm('r11', 'r9', 0, 29, 29)
    # ---- tint to the ball (mode 1, and match-ball fallback) ----
    a.label('c_ball')
    a.cmpwi('r11', 0)
    a.beq('c_table')                    # regular ball: its colour slot
    a.lis('r12', TIER_CFG >> 16)
    a.ori('r12', 'r12', TIER_CFG & 0xFFFF)
    a.add('r12', 'r12', 'r10')
    a.lbz('r12', 0, 'r12')
    a.cmpwi('r12', ord('D'))
    a.beq('c_rainbow')
    a.li('r10', 5)                      # Gold
    a.cmpwi('r12', ord('G'))
    a.beq('c_table')
    a.li('r10', 4)                      # Pro orb (default when it can't be identified)
    a.rlwinm('r11', 'r9', 2, 28, 29)    # slot * 4
    a.lis('r12', 0x8000)
    a.add('r12', 'r12', 'r11')
    a.lwz('r12', PRO_IMG & 0xFFFF, 'r12')
    a.cmpwi('r12', 0)
    a.beq('c_table')
    a.lwz('r11', -0x10, 'r12')
    a.lis('r8', 0x4252)
    a.ori('r8', 'r8', 0x414E)           # 'BRAN': random orb -> the set rolled for this slot
    a.cmpw('r11', 'r8')
    a.bne('c_banm')
    a.lhz('r11', -0x0A, 'r12')
    a.cmplwi('r11', len(ORB_COLORS))
    a.bge('c_table')
    a.addi('r10', 'r11', len(TRAIL_COLORS))
    a.b('c_table')
    a.label('c_banm')
    a.lis('r8', 0x4241)
    a.ori('r8', 'r8', 0x4E4D)           # 'BANM' with an orb id
    a.cmpw('r11', 'r8')
    a.bne('c_table')
    a.lbz('r11', -0x0C, 'r12')
    a.cmpwi('r11', 0)
    a.beq('c_table')
    a.cmplwi('r11', len(ORB_COLORS))
    a.bgt('c_table')
    a.addi('r10', 'r11', len(TRAIL_COLORS) - 1)
    a.label('c_table')
    a.slwi('r10', 'r10', 2)
    a.lis('r12', 0)                     # (patched below to the table address)
    a.label('c_tab_lo')
    a.ori('r12', 'r12', 0)
    a.add('r12', 'r12', 'r10')
    a.lbz('r4', 0, 'r12')
    a.lbz('r5', 1, 'r12')
    a.lbz('r6', 2, 'r12')
    a.b('c_store')
    a.label('c_rainbow')                # hue 0..1535 from the time base: 6 segments of 256
    a.mftb('r9')
    a.srwi('r9', 'r9', RAINBOW_SHIFT)
    a.li('r10', 1536)
    a.divwu('r11', 'r9', 'r10')
    a.mullw('r11', 'r11', 'r10')
    a.subf('r9', 'r11', 'r9')
    a.srwi('r10', 'r9', 8)              # segment
    a.rlwinm('r11', 'r9', 0, 24, 31)    # f
    a.li('r12', 255)
    a.subf('r12', 'r11', 'r12')         # 255 - f
    a.li('r4', 255)                     # seg 0: 255, f, 0
    a.mr('r5', 'r11')
    a.li('r6', 0)
    a.cmpwi('r10', 1)
    a.blt('c_store')
    a.mr('r4', 'r12')                   # seg 1: 255-f, 255, 0
    a.li('r5', 255)
    a.beq('c_store')
    a.li('r4', 0)                       # seg 2: 0, 255, f
    a.mr('r6', 'r11')
    a.cmpwi('r10', 2)
    a.beq('c_store')
    a.mr('r5', 'r12')                   # seg 3: 0, 255-f, 255
    a.li('r6', 255)
    a.cmpwi('r10', 3)
    a.beq('c_store')
    a.mr('r4', 'r11')                   # seg 4: f, 0, 255
    a.li('r5', 0)
    a.cmpwi('r10', 4)
    a.beq('c_store')
    a.li('r4', 255)                     # seg 5: 255, 0, 255-f
    a.mr('r6', 'r12')
    a.label('c_store')
    a.stw('r4', 0x08, 'r1')
    a.stw('r5', 0x0C, 'r1')
    a.stw('r6', 0x10, 'r1')
    a.cmpwi('r7', 0)
    a.beq('c_named')
    a.stb('r7', 4 + NAME_LETTER, 'r30')  # aura / sparks for this burst (the effect is looked up by name)
    a.label('c_named')
    a.mr('r3', 'r30')
    a.bl(EFFECT_KILL)                   # its previous burst stops emitting (particles finish)
    a.mr('r3', 'r30')
    a.bl(EFFECT_START)                  # a new burst
    a.lwz('r4', 0x08, 'r1')
    a.lwz('r5', 0x0C, 'r1')
    a.lwz('r6', 0x10, 'r1')
    a.li('r7', 255)
    a.li('r8', 3)
    a.mr('r3', 'r30')
    a.bl(EFFECT_SET_COLOR)
    a.mr('r3', 'r30')
    a.lis('r4', TRAIL_MTX >> 16)
    a.ori('r4', 'r4', TRAIL_MTX & 0xFFFF)
    a.bl(EFFECT_SET_MTX)
    a.mr('r3', 'r30')
    a.bl(EFFECT_UPDATE)                 # place it; it stays there
    a.b('t_out')
    a.label('t_off')
    for off, prev in ((0x50, TRAIL_PX), (0x60, TRAIL_PY), (0x70, TRAIL_PZ)):
        a.lwz('r9', off, 'r29')
        a.stw('r9', prev & 0xFFFF, 'r31')
    a.lwz('r0', TRAIL_ON & 0xFFFF, 'r31')
    a.cmpwi('r0', 0)
    a.beq('t_out')
    a.li('r0', 0)                       # roll over: stop every burst emitter (particles finish)
    a.stw('r0', TRAIL_ON & 0xFFFF, 'r31')
    a.stw('r0', TRAIL_TICK & 0xFFFF, 'r31')
    a.li('r28', 0)
    a.label('t_kill_all')
    a.slwi('r9', 'r28', 2)
    a.add('r9', 'r9', 'r31')
    a.lwz('r3', TRAIL_EFFS & 0xFFFF, 'r9')
    a.cmpwi('r3', 0)
    a.beq('t_kill_next')
    a.bl(EFFECT_KILL)
    a.label('t_kill_next')
    a.addi('r28', 'r28', 1)
    a.cmpwi('r28', TRAIL_N)
    a.blt('t_kill_all')
    a.label('t_out')
    a.lwz('r0', 0x34, 'r1')
    a.lwz('r31', 0x2C, 'r1')
    a.lwz('r30', 0x28, 'r1')
    a.lwz('r29', 0x24, 'r1')
    a.lwz('r28', 0x20, 'r1')
    a.mtlr('r0')
    a.addi('r1', 'r1', 0x30)
    a.blr()
    a.label('c_colors')
    for r, g, b in TRAIL_COLORS + ORB_COLORS:
        a.word((r << 24) | (g << 16) | (b << 8) | 0xFF)
    a.label('m_profiles')
    for prof in MATCH_PROFILES:
        for part in prof:
            if part is None:
                a.word(0)
            elif part == 'rainbow':
                a.word(0xFFFFFF03)
            else:
                r, g, b = part
                a.word((r << 24) | (g << 16) | (b << 8) | 0x01)
    code = bytearray(a.assemble())
    import struct
    for lab, tab in (('c_tab_lo', a.addr('c_colors')), ('m_tab_lo', a.addr('m_profiles'))):
        lo = a.addr(lab) - TRAIL_ADDR                      # fix up lis/ori with the table address
        struct.pack_into('>I', code, lo - 4, (15 << 26) | (12 << 21) | (tab >> 16))
        struct.pack_into('>I', code, lo, (24 << 26) | (12 << 21) | (12 << 16) | (tab & 0xFFFF))
    assert len(MATCH_PROFILES) == POOL_SIZE + ORB_COUNT + 2
    assert a.addr('trail_init') == TRAIL_ADDR
    assert TRAIL_NAME + 32 <= TRAIL_POOL and TRAIL_POOL + TRAIL_N * EFFECT_SIZE <= STAGE_ADDR
    assert TRAIL_ADDR + len(code) <= TRAIL_END, hex(TRAIL_ADDR + len(code))
    return bytes(code), a


def build_stage():
    """'stage' (STAGE_ADDR): called instead of LoadStage(name, -1, 0) while Bowling sets up.
      - trail on: rebuild the trail effect objects (trail_init)
      - Normal.carc with the Random alley ('V'): while the theme loaded last is still in the game's
        archive cache (it keeps archives for the whole Bowling session), keep it - a cache hit, exactly
        like the stock game reusing Normal.carc; otherwise roll a new one (never the same twice).
        (Loading a different alley on every restart hung the game on the 3rd load, even when the
        previous one was evicted and freed - so nothing is ever unloaded.)"""
    a = Asm(STAGE_ADDR)
    a.label('stage')
    a.stwu('r1', -0x30, 'r1')
    a.mflr('r0')
    a.stw('r0', 0x34, 'r1')
    a.stw('r3', 0x08, 'r1')
    a.stw('r4', 0x0C, 'r1')
    a.stw('r5', 0x10, 'r1')
    a.stw('r31', 0x2C, 'r1')
    a.stw('r30', 0x28, 'r1')
    a.li('r0', 0)
    a.stw('r0', 0x14, 'r1')             # 1 = a theme file is being loaded
    a.lis('r11', 0x8000)
    a.lbz('r10', TRAIL_KEY & 0xFFFF, 'r11')
    a.cmpwi('r10', KEY)
    a.bne('stage_alley')
    a.bl(TRAIL_ADDR)                    # trail_init
    a.label('stage_alley')
    a.lwz('r3', 0x08, 'r1')
    a.lis('r12', NORMAL_NAME >> 16)
    a.ori('r12', 'r12', NORMAL_NAME & 0xFFFF)
    a.cmplw('r3', 'r12')
    a.bne('stage_go')                   # 100-Pin: leave alone
    a.lis('r11', 0x8000)
    a.lbz('r10', THEME_KEY & 0xFFFF, 'r11')
    a.cmpwi('r10', KEY)
    a.bne('stage_go')
    a.lbz('r10', THEME_MODE & 0xFFFF, 'r11')
    a.cmpwi('r10', ord('V'))
    a.bne('stage_go')
    a.bl('find_rec')                    # the alley picked on entering Bowling is still cached: keep it
    a.cmpwi('r3', 0)                    # (a restart is then a cache hit, exactly like the stock game;
    a.beq('alley_rand')                 #  loading another alley each restart hung the game)
    a.lis('r11', 0x8000)
    a.lbz('r7', THEME_LAST & 0xFFFF, 'r11')
    a.cmplwi('r7', len(ALLEY_FILES))
    a.blt('alley_pick')
    a.label('alley_rand')
    a.lis('r11', 0x8000)
    a.li('r9', len(ALLEY_FILES))
    a.lbz('r6', THEME_LAST & 0xFFFF, 'r11')
    a.mr('r0', 'r9')                    # roll over every theme...
    a.cmplw('r6', 'r9')
    a.bge('alley_roll')
    a.addi('r0', 'r9', -1)              # ...or over the others when the last one is known
    a.label('alley_roll')
    a.mftb('r8')
    a.lis('r7', 0x9E37)
    a.ori('r7', 'r7', 0x79B1)
    a.mullw('r8', 'r8', 'r7')
    a.srwi('r8', 'r8', 16)
    a.divwu('r7', 'r8', 'r0')
    a.mullw('r7', 'r7', 'r0')
    a.subf('r7', 'r7', 'r8')            # r7 = roll % r0
    a.cmplw('r6', 'r9')
    a.bge('alley_new')
    a.cmplw('r7', 'r6')
    a.blt('alley_new')
    a.addi('r7', 'r7', 1)               # never the same alley twice in a row
    a.label('alley_new')
    a.lis('r11', 0x8000)
    a.li('r8', 0xFF)
    a.stb('r8', PIN_VAR & 0xFFFF, 'r11')     # new alley: Whiteout pins roll a new colourway
    a.label('alley_pick')
    a.lis('r11', 0x8000)
    a.stb('r7', THEME_LAST & 0xFFFF, 'r11')
    a.addi('r8', 'r7', 1)
    a.stb('r8', THEME_CUR & 0xFFFF, 'r11')   # live pins follow the alley
    a.slwi('r7', 'r7', 4)
    a.lis('r3', ALLEY_NAMES >> 16)
    a.ori('r3', 'r3', ALLEY_NAMES & 0xFFFF)
    a.add('r3', 'r3', 'r7')
    a.stw('r3', 0x08, 'r1')
    a.li('r0', 1)
    a.stw('r0', 0x14, 'r1')
    a.label('stage_load')
    a.lwz('r3', 0x08, 'r1')
    a.label('stage_go')
    a.lwz('r4', 0x0C, 'r1')
    a.lwz('r5', 0x10, 'r1')
    a.bl(STAGE_LOAD)
    a.lwz('r0', 0x14, 'r1')
    a.cmpwi('r0', 0)
    a.beq('stage_ret')
    a.stw('r3', 0x18, 'r1')             # keep the loader's result
    a.lwz('r3', RES_MGR_SDA, 'r13')     # remember the record this theme is cached under
    a.addi('r5', 'r3', 0x28)            # (the loader built the full path here)
    a.li('r4', 0)
    a.bl(RES_FIND)
    a.lis('r4', 0x8000)
    a.stw('r3', ALLEY_REC & 0xFFFF, 'r4')
    a.lwz('r3', 0x18, 'r1')
    a.label('stage_ret')
    a.lwz('r0', 0x34, 'r1')
    a.lwz('r31', 0x2C, 'r1')
    a.lwz('r30', 0x28, 'r1')
    a.mtlr('r0')
    a.addi('r1', 'r1', 0x30)
    a.blr()

    a.label('find_rec')                 # -> r3 = ALLEY_REC if it is still in the cache (list 0), else 0
    a.stwu('r1', -0x20, 'r1')
    a.mflr('r0')
    a.stw('r0', 0x24, 'r1')
    a.stw('r31', 0x1C, 'r1')
    a.lis('r31', 0x8000)
    a.lwz('r31', ALLEY_REC & 0xFFFF, 'r31')
    a.cmpwi('r31', 0)
    a.beq('fr_none')
    a.lwz('r3', RES_MGR_SDA, 'r13')
    a.addi('r3', 'r3', 4)               # cache list 0
    a.stw('r3', 0x08, 'r1')
    a.li('r4', 0)
    a.label('fr_walk')
    a.bl(LIST_NEXT)
    a.cmpwi('r3', 0)
    a.beq('fr_none')
    a.cmplw('r3', 'r31')
    a.beq('fr_ret')
    a.mr('r4', 'r3')
    a.lwz('r3', 0x08, 'r1')
    a.b('fr_walk')
    a.label('fr_none')
    a.li('r3', 0)
    a.label('fr_ret')
    a.lwz('r0', 0x24, 'r1')
    a.lwz('r31', 0x1C, 'r1')
    a.mtlr('r0')
    a.addi('r1', 'r1', 0x20)
    a.blr()
    code = a.assemble()
    assert STAGE_ADDR + len(code) <= 0x80003000, hex(STAGE_ADDR + len(code))
    return code, a


def stage_patch():
    code, a = build_stage()
    call = branch(STAGE_CALL, a.addr('stage')) | 1
    return (STAGE_CALL, call.to_bytes(4, 'big'), branch(STAGE_CALL, STAGE_LOAD) | 1)


def alley_patches(mode='V'):
    """Memory patches for the Random alley."""
    code, a = build()
    names = b''.join(n.encode().ljust(16, b'\0') for n in ALLEY_FILES)
    assert all(len(n) < 16 for n in ALLEY_FILES) and ALLEY_NAMES + len(names) <= TRAIL_EFFS
    scode, _ = build_stage()
    return [(HOOK_ADDR, code, None),
            (STAGE_ADDR, scode, None),
            (ALLEY_NAMES, names, None),
            (THEME_MODE, bytes([ord(mode), 0xFF, KEY]), None),
            (THEME_CUR, bytes([0, KEY, 0xFF]), None),
            stage_patch()]


def trail_patches(style=0):
    """Memory patches for the Ball trail option (style = index into TRAIL_STYLES)."""
    import struct
    code, a = build()
    tcode, t = build_trail()
    _, effect, tint = TRAIL_STYLES[style]
    one = struct.pack('>f', 1.0)
    z = bytes(4)
    mtx = one + z + z + z + z + one + z + z + z + z + one + z
    name = effect.encode().ljust(32, b'\0')
    assert len(effect) < 32 and TRAIL_MTX + 0x30 == TRAIL_NAME and TRAIL_NAME + 32 <= 0x80002800
    state = bytes(TRAIL_TINT - TRAIL_EFFS) + bytes([tint, 0, 0, 0]) + bytes(12) + struct.pack('>f', LEAD_FRAMES)
    assert TRAIL_EFFS + len(state) == TRAIL_LEAD + 4 <= 0x80002000
    scode, _ = build_stage()
    return [(HOOK_ADDR, code, None),
            (STAGE_ADDR, scode, None),
            (TRAIL_ADDR, tcode, None),
            (TRAIL_EFFS, state, None),
            (TRAIL_MTX, mtx + name, None),
            (TRAIL_KEY, bytes([KEY]), None),
            stage_patch(),
            (BALL_UPDATE, branch(BALL_UPDATE, t.addr('trail')).to_bytes(4, 'big'), BALL_UPDATE_FIRST)]


def theme_patch(index):
    """Fixed alley choice: tell the BTHM textures (live pins) which theme is on (index 1..5)."""
    return (THEME_CUR, bytes([index, KEY, 0xFF]), None)


def tier_patch(slot, tier):
    """Riivolution memory patch for 'P<slot+1> Pro ball: Gold/Diamond'."""
    return (TIER_CFG + slot, tier.encode(), None)


if __name__ == '__main__':
    import capstone
    code, a = build()
    md = capstone.Cs(capstone.CS_ARCH_PPC, capstone.CS_MODE_32 | capstone.CS_MODE_BIG_ENDIAN)
    inv = {v: k for k, v in a.labels.items()}
    for i in md.disasm(code, HOOK_ADDR):
        lab = inv.get(i.address, '')
        print(f'{lab:>9s} {i.address:08x}: {i.mnemonic:8s} {i.op_str}')
    print(len(code), 'bytes, ends at', hex(HOOK_ADDR + len(code)))
