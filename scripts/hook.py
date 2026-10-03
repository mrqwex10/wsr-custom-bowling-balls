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
  BDBG (skill detector test): pool index = bracket of the last Bowling skill seen
    0x34 u16 count, 0x38 u32 stride, 0x3C s32 rel (as BRND)
  BPAG (diagnostic pages): every few seconds shows the next page of numbers
    0x34 u8 pages, u8 values per page, 0x36 u16 page period (1/60 s), 0x38 stride, 0x3C rel
    page 0 = CALLS, page 1 = LAST_ANY / 100, page 2 = LAST_SKILL / 100 (clamped)

The Gold/Diamond tier per player is set by Riivolution memory patches (TIER_CFG);
BDBG/BPAG are diagnostic modes kept for debugging.
"""
from ppcasm import Asm, branch

GXLOADTEXOBJ = 0x80037780        # stwu r1,-0x10(r1) ; mflr r0 ; ...
GXLOADTEXOBJ_FIRST = 0x9421FFF0  # the instruction we replace
HOOK_ADDR = 0x80001A00           # free low-memory area (same area loaders/codehandlers use)
TB_SHIFT_TICKS_PER_60TH = 989    # (60.75 MHz / 60) >> 10
BOWLING_CODE = (0x80489000, 0x80510000)
TIER_CFG = 0x80001F20            # 4 bytes, one per player; written by the Riivolution tier options
DATA = 0x80001F00                # see below
LAST_SKILL, LAST_PRO = DATA, DATA + 4       # last Bowling skill / last Bowling skill >= 1000
CALLS, ACTIVE, LAST_ANY = DATA + 8, DATA + 0xC, DATA + 0x10   # getSkill calls, TBU when our ball last drawn, last value from anywhere
DATA_SIZE = 0x14
ACTIVE_WINDOW = 1                # in time-base-upper units (~70 s each)


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
    a.lis('r9', 0x4244)
    a.ori('r9', 'r9', 0x4247)           # 'BDBG'
    a.cmpw('r10', 'r9')
    a.beq('dbg')
    a.lis('r9', 0x4250)
    a.ori('r9', 'r9', 0x4147)           # 'BPAG'
    a.cmpw('r10', 'r9')
    a.beq('pag')
    a.lis('r9', 0x4252)
    a.ori('r9', 'r9', 0x414E)           # 'BRAN'
    a.cmpw('r10', 'r9')
    a.bne('passthru')

    # --- random animated set: roll a set once per load, then animate it ---
    _mark(a)
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
    a.b('dispatch')

    # --- skill detector: bracket of the last Bowling skill seen ---------------
    a.label('dbg')
    _mark(a)
    a.lis('r8', DATA >> 16)
    a.lwz('r8', (LAST_SKILL & 0xFFFF), 'r8')
    a.li('r5', 0)
    a.cmplwi('r8', 0)
    a.beq('dbg_go')
    a.li('r5', 1)
    a.cmplwi('r8', 1000)
    a.blt('dbg_go')
    a.li('r5', 2)
    a.cmplwi('r8', 1500)
    a.blt('dbg_go')
    a.li('r5', 3)
    a.cmplwi('r8', 2000)
    a.blt('dbg_go')
    a.li('r5', 4)
    a.label('dbg_go')
    a.lwz('r8', -0x08, 'r11')
    a.lwz('r7', -0x04, 'r11')
    a.b('subst')

    # --- diagnostic pages: page = time / period % pages, value from DATA ------
    a.label('pag')
    _mark(a)
    a.lbz('r9', -0x0C, 'r11')           # pages
    a.lhz('r8', -0x0A, 'r11')           # page period
    _frame(a, '_pag')                   # r5 = page
    a.mr('r10', 'r5')                   # keep page
    a.lis('r8', DATA >> 16)
    a.cmplwi('r10', 0)
    a.bne('pag1')
    a.lwz('r6', CALLS & 0xFFFF, 'r8')
    a.b('pag_clamp')
    a.label('pag1')
    a.cmplwi('r10', 1)
    a.bne('pag2')
    a.lwz('r6', LAST_ANY & 0xFFFF, 'r8')
    a.b('pag_div')
    a.label('pag2')
    a.lwz('r6', LAST_SKILL & 0xFFFF, 'r8')
    a.label('pag_div')
    a.li('r7', 100)
    a.divwu('r6', 'r6', 'r7')
    a.label('pag_clamp')
    a.lbz('r7', -0x0B, 'r11')           # values per page
    a.addi('r9', 'r7', -1)
    a.cmplw('r6', 'r9')
    a.ble('pag_ok')
    a.mr('r6', 'r9')
    a.label('pag_ok')
    a.mullw('r5', 'r10', 'r7')
    a.add('r5', 'r5', 'r6')
    a.lwz('r8', -0x08, 'r11')
    a.lwz('r7', -0x04, 'r11')
    a.b('subst')

    # --- random design: pick once per load, remember in the header ---------
    a.label('rnd')
    _mark(a)
    a.lhz('r9', -0x0C, 'r11')           # count
    a.lhz('r5', -0x0A, 'r11')           # stamp
    a.cmplwi('r5', 0xFFFF)
    a.bne('rnd_ok')
    _roll(a)
    a.sth('r5', -0x0A, 'r11')
    a.label('rnd_ok')
    a.lwz('r8', -0x08, 'r11')           # stride
    a.lwz('r7', -0x04, 'r11')           # rel
    a.b('subst')

    # --- animated: frame from the time base (steady speed) ----------------
    a.label('anim')
    _mark(a)
    a.lhz('r9', -0x0C, 'r11')           # count
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
            (GXLOADTEXOBJ, branch(GXLOADTEXOBJ, HOOK_ADDR).to_bytes(4, 'big'), GXLOADTEXOBJ_FIRST)]


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
