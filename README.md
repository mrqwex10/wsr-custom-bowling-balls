<p align="center"><img src="previews/banner.png" alt="WSR Custom Bowling Balls"></p>

# WSR Custom Bowling Balls

**New bowling balls, alleys and a ball trail for Wii Sports Resort**, loaded with Riivolution / Friivolution.

- **6 animated Pro orbs** for players at Pro rank (1000+ skill): a different one each game, or pick your favourite
- **2 prestige tiers**: an animated **Gold** ball and the **Prismatic Diamond**
- **8 designs for everyone else**: every non-Pro player gets a random one each time Bowling loads
- **5 animated alley themes** *(new in v2.0)*, each with its own room lighting; pick one or let Random choose
- **Ball trail** *(new in v2.0)*: the rolling ball leaves a trail of particles on its way to the pins, made for each ball (a starry aura for Galaxy, embers for Inferno, a rainbow for the Prismatic Diamond...)

No save data is touched; turn the options off and the game is completely stock.

## Animated Pro orbs

<p align="center"><img src="previews/pro_orbs.gif" alt="Animated Pro orbs"></p>

Holographic · Venom Swirl · Inferno · Black Hole · Arcane Void · Dragon's Eye

## Gold & Prismatic Diamond

<p align="center"><img src="previews/tiers.gif" alt="Gold and Prismatic Diamond"></p>

Upgrade a Pro player's ball once they've earned it: **Gold at 1500 skill, Prismatic Diamond at 2000**
(you set it in the Riivolution menu, see below).

## Random balls for non-Pro players

<p align="center"><img src="previews/random_pool.png" alt="Random ball designs"></p>

Riptide · Galaxy · Tie-Dye · Hyperspin · Smiley · Emerald 420 · Stained Glass · Synthwave

## Alley themes

<p align="center"><img src="previews/alleys.gif" alt="Alley themes"></p>

| Theme | Look | Animated |
|---|---|---|
| **Cosmic Glow** | Blacklight space alley: glitter lanes, neon arrows, a ringed bowling-ball planet | Drifting nebula, comet, chase-light gutters |
| **Synthwave Sunset** | 80s neon grid, chrome gutters, retro sun behind palm trees | Scrolling grid, sliding sun stripes, gutter pulse |
| **Aurora Ice** | Frozen lanes, frosted gutters, snowy peaks under the northern lights | Rippling aurora, twinkling stars |
| **Lava Forge** | Obsidian lanes split by lava seams, an erupting volcano | Lava flowing in the lane seams and gutters, eruption |
| **Whiteout** | Bright gallery alley with dark pins | Ink ball rolling into the rack |

<p align="center"><img src="previews/alleys_grid.jpg" alt="Alley themes at the pins"></p>

Pick one, or let **Random** choose: a new alley every game, never the same one twice in a row. Each alley also tints the room's lights to match,
and Whiteout's dark pins come in a random colourway: onyx, navy, garnet or forest.
The pins on the lanes in play match the alley too (dark pins in Whiteout) when a Ball mod choice is on.
The 100-Pin alley stays stock. *(Previews are rendered from the game's real alley model with the mod's textures.)*

## Requirements

- **Wii Sports Resort, USA version (RZTE01)**. Developed and tested on the USA **Rev 1** disc.
- A Wii with the Homebrew Channel and **Riivolution** (or **Friivolution**)
- An SD card

## Installation

1. Download `WSR_Custom_Bowling_Balls_vX.Y.zip` from [Releases](../../releases).
2. Copy the **`riivolution`** and **`WSR_ball_mod`** folders from the zip to the **root of your SD card**
   (merge with an existing `riivolution` folder if you have one).
3. Start Riivolution / Friivolution and choose Wii Sports Resort.
4. Under **WSR Custom Bowling Balls**, set **Ball mod** (recommended: *Pro: random orb each game*),
   an **Alley** (try *Random*), **Ball trail** (*Match ball (Auto)*), and, if you like, a **Pro ball tier** for your player number.
5. Launch the game and play Bowling.

## Menu options

**Ball mod**

| Choice | What you get |
|---|---|
| **Pro: random orb each game** *(recommended)* | Pro players get a random animated orb each time Bowling loads |
| Pro: Holographic / Venom Swirl / Inferno / Black Hole / Arcane Void / Dragon's Eye | Pro players always get that orb (smoother 16-frame animation) |
| TEST: non-Pro balls get the random orbs | See the animated orbs without being Pro |

With every choice except TEST, non-Pro players get a random design from the regular set.

**Alley**

| Choice | What you get |
|---|---|
| Cosmic Glow / Synthwave Sunset / Aurora Ice / Lava Forge / Whiteout | Always that alley |
| **Random** | A new alley every game, never the same one twice in a row |

**Ball trail** (Disabled / Match ball (Auto) / Aura / Sparks): the thrown ball leaves a trail of particles while it rolls toward the pins.
*Match ball (Auto)* (recommended) gives every ball its own trail: an aura, sparks or both, in that ball's colours
(Galaxy: violet aura + white stars, Inferno: fire + embers, Gold: gold + glitter, Prismatic Diamond: rainbow + sparkle...).
*Aura* and *Sparks* use one effect for everyone:
in the ball's colour: each Pro orb has its own (Venom = lime, Inferno = orange, ...), gold for Gold,
a cycling rainbow for the Prismatic Diamond, and the ball colour for everyone else.

**P1 / P2 / P3 / P4 Pro ball tier** (Disabled / Gold / Prismatic Diamond)

Upgrades that player number's Pro ball to the **Gold** or **Prismatic Diamond** ball.
The intended rule: unlock Gold at **1500** skill and Diamond at **2000**. It's an honour system, so set it yourself when you get there.
It only affects players who are Pro; everyone else is unchanged.

### Good to know
- **Pro** means 1000+ Bowling skill; that's the game's own rule for who gets a Pro ball.
- **Player number = the order Miis are picked** (P1 is the first Mii). Pick your Mii first to keep your P1 tier.
- The random ball and the random alley are picked each time Bowling loads.
- Every option works on its own, in any combination.

## Troubleshooting

- **The game crashes or the screen stays black when Bowling loads:** try one of the single-orb choices or a single alley
  (they use a little less memory) and let me know.
- **Balls look normal:** check that *Ball mod* is set (not Disabled) and that your game is the USA version.
  The code patch checks the game's code before applying, so other versions/regions won't change.

## How it works (for the curious)

The textures live in the game's Bowling archive (`Common/BwlScene/common.carc`), which Riivolution swaps for a modified copy.
Animation and random picks come from a small PowerPC patch on `GXLoadTexObj` (the function that hands every texture to the GPU):
when it sees one of the mod's tagged ball textures it points the GPU at the right animation frame / random design for that one draw,
then restores the original, so the game's own data never changes. Gold/Diamond are chosen by a per-player byte that the Riivolution
tier options write. The patch is tested in a PowerPC emulator ([unicorn](https://www.unicorn-engine.org/)) against the game's real code.

The alleys replace the Bowling stage archive (`Stage/BwlScene/Normal.carc`); their animations use the same texture patch,
and the room lighting is a tint of the stage's own scene lights. *Random* / *Next* add every theme to the game's file system and
redirect the one call that loads the alley. The **ball trail** is an effect Nintendo left in the game but never used
(`WS2_bwl_balltail`): The **ball trail** uses particle effects that are already in the game's Bowling effects: a small patch creates a pool of them
when Bowling sets up and, while the ball rolls toward the pins, drops a tinted burst at the ball every other frame.
Every alley is built to exactly the stock alley's size (in memory and on disc), so the game can swap one for another on every
restart just like it reloads the stock alley - bigger alleys left gaps in the game's memory and hung it after a couple of restarts.

See [BUILDING.md](BUILDING.md) to rebuild everything from your own copy of the game.

## Credits

- Made by qwex10, built with Claude (Anthropic)
- Built with [Wiimms ISO / SZS Tools](https://wiimm.de/)
- Loaded by [Riivolution](https://rvlution.net/)

All ball designs are original procedural art made for this mod.

## Disclaimer

Not affiliated with or endorsed by Nintendo. *Wii Sports Resort* is a trademark of Nintendo.
You need your own copy of the game. The release download contains modified copies of the game's Bowling archive
(as is usual for Wii Sports Resort mods); this repository itself contains only the mod's own code and artwork.
