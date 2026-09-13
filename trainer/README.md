# TW Trainer (Two Worlds 1, v1.7)

A trainer plugin for TWSE: godmode, infinite mana and gold, run speed,
sprint on Shift, lockpicking, kill target, teleport network unlocked, the
whole vanilla console at your fingertips. Singleplayer only, please.

Files: `tw_trainer.c` (source, builds with Tiny C Compiler),
`bin\TWSEPlugins\TWTrainer.dll` (ready to use, full build).

## Install

1. TWSE must be in place. Easiest: start `tw1_Extendet-settings.exe` from
   this repository and click **Install (TWSE + plugin)** once. That creates
   `TwoWorldsExtended.exe` and `twse.dll` in the game folder.
2. Copy `TWTrainer.dll` to `<Game>\TWSEPlugins\` (next to `TWExtended.dll`).
3. Start the game through `TwoWorldsExtended.exe` (the tool's **Start game**
   button does that). Optional: add `-TWSEdebug` to the command line to get a
   console window with the plugin log. The log also goes to `TWTrainer.log`
   in the game folder.

On the first frame after a savegame is loaded the trainer enables the game's
cheat mode itself (`TwoWorldsCheats`), so the vanilla console commands work.
If a cheat does not respond after loading a save, type `trainer.cheats` in
the console.

## Hotkeys (no Ctrl needed)

| Key | Second key (German QWERTZ) | Action |
|---|---|---|
| Numpad 0 | | overlay on/off |
| Numpad 1 | ü | lockpicking skill to 100 |
| Numpad 2 | ö | godmode on/off (HP kept full every frame) |
| Numpad 3 | | run speed 4x, then 6x, then off |
| Numpad 4 | ä | kill the targeted unit |
| Numpad 5 | | infinite gold on/off |
| Shift (held) | | sprint, 1.4x the current speed, exact reset on release |

The second keys are layout dependent (`VK_OEM_1/3/7`); on other layouts
different characters sit there, the numpad always works. The hotkeys also fire
while you type text in the game (for example a savegame name); that is a
known trade-off, the game swallows every modifier that would avoid it.

## Overlay

Two lines top left: status (godmode, mana, speed, last action) and the hotkey
legend. Numpad 0 or `trainer.overlay` toggles it. The trainer writes straight
into the game's on-screen debug buffer (addresses in the source).

## Console commands (`~` opens the game console)

Character and values:
```
trainer.gold 5000        trainer.setgold 999999
trainer.exp 5000         trainer.skill 10          (skill points)
trainer.param 10         trainer.str 100           (parameter points, strength)
trainer.speed 600        trainer.skills 10         (every skill +10)
trainer.school 1         trainer.magic <name>
trainer.bskill <name>    trainer.bpoint <name>
trainer.head <name>      trainer.neck <name>
trainer.setskill <index> <value>   trainer.skilllist
```

Life and death:
```
trainer.heal             trainer.healh             (heal target / hero)
trainer.revive           trainer.kill              (kill target)
trainer.killme           trainer.hithp 50
trainer.hitmana 50       trainer.hitpoison 20
trainer.god              trainer.mana              (toggles)
trainer.infgold [n]      trainer.fall <n>          (fall adds fall damage, it is no switch)
trainer.rescue
```

World and objects:
```
trainer.create <name>    trainer.created <name>
trainer.item <name>      trainer.anim <name>
trainer.rate 5           trainer.time 12
trainer.teleports        trainer.overlay
trainer.fog              trainer.unlock            (nearby gates and chests)
trainer.lockpick <n>     trainer.tpon              (teleporters in range)
```

Position:
```
trainer.tp               print the current position
trainer.tp 21234 7226    teleport there (height comes from the ground)
```

Quests at runtime:
```
trainer.quest.state <id> <state>    trainer.quest.add <params>
trainer.quest.remove <id>           trainer.quest.pos <params>
trainer.ec <ec.dbg command>
```

Generic:
```
trainer.line Engine.DLandUseOCC 1   any console line, variables included
trainer.exec AddGold 5000           any vanilla function command
trainer.get Engine.FarPlane         show an engine variable
trainer.script [file]               run a file of console lines
trainer.cheats                      enable cheat mode again
trainer.horse 1                     horse comes to the whistle by teleport
```

## Autostart scripts

After a savegame is loaded the trainer runs two optional files from the game
folder as console lines (lines starting with `#` or `//` are skipped):

- `kira_grafik.txt` - graphics settings, runs in every build.
- `test.txt` - your own cheat lines, runs only in the full build.

`trainer.script <file>` runs any other file by hand.

## What does not work

- **Flight.** The game clamps the hero to the ground on every position
  change; only a patch of that routine could change it.
- **Turning fall damage off from the console.** `hitfall` adds fall damage.
  Use the settings tool from this repository instead, it patches the actual
  computation.

## Build

`build_trainer.bat` (Tiny C Compiler, 32-bit, `tcc.exe` in `..\..\tcc\` or in
`PATH`, or `set TCC=...`). It builds the full variant (`-DNUR_SPRINT=0`).
`-DNUR_SPRINT=1` gives the sprint-only variant that ships with the Kira
campaign: Shift sprint and the graphics script, no cheats. The TWSE headers
are in `..\twse\`.

Game version 1.7 only, Steam "Two Worlds - Epic Edition" exe (6,909,008
bytes); other 1.7 builds have the functions at other addresses.

License CC0. Built on TWSE by buglord.
