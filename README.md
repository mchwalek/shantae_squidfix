# Shantae (GBC) warp-squid crash fix

Fixes the long-known crash in the 3DS eShop Virtual Console release of *Shantae* (Game Boy Color, 2002):
collecting a baby warp squid sometimes freezes the game on a solid blue screen, and after a reset the save
file can be gone. The same crash is reported for the Switch port.

The crash is a real bug in the game: a non-reentrant far-call helper that the VBlank interrupt can
interrupt and corrupt. On a real Game Boy Color the timing never lines up. The 3DS VC emulator makes it reachable
because it treats the CPU stall during the game's DMA copies as free. Full analysis: [WRITEUP.md](WRITEUP.md).

There are two independent fixes. Each one alone prevents the crash.

| Fix | File | Fixes | For |
|---|---|---|---|
| Emulator fix | [`patches/3ds/luma/titles/00040000000BE500/code.ips`](patches/3ds/luma/titles/00040000000BE500/code.ips) | the VC emulator's DMA timing | 3DS eShop VC (US, title ID `00040000000BE500`), Luma3DS or Azahar |
| ROM fix | [`patches/gbc/Shantae_warpsquid_fix.ips`](patches/gbc/Shantae_warpsquid_fix.ips) | the bug in the game itself | the GBC ROM, any emulator or flash cart |

> **Back up your save first.** The crash wipes the save, and these patches are only tested in emulators so far.

## 3DS (eShop Virtual Console) with Luma3DS

1. Copy the `luma` folder from `patches/3ds/` to the root of your SD card, so the file ends up at
   `/luma/titles/00040000000BE500/code.ips`.
2. Enable game patching: hold SELECT while powering on to open the Luma3DS configuration, tick
   **"Enable game patching"**, and save with START.
3. Start Shantae as usual.

To remove the fix, delete the `00040000000BE500` folder.

The patch is made for the VC emulator build `0.124` that ships with this title
(`code.bin` SHA-1 `cc99b2ad4fd43000d0d383192157c9112c216e1c`). Luma3DS applies IPS files without checking,
so do not copy this file to another title ID. To check your own copy, dump the title's `code.bin` (e.g. with
GodMode9) and run `python tools/dmastall.py code.bin out.bin`: it refuses unknown builds.

## Azahar (3DS emulator)

Put the same file at `load/mods/00040000000BE500/exefs/code.ips` inside the Azahar user directory
(right-click the game, **Open > Mods Location**, and create the `exefs` folder there). Start the game from the
menu: savestates made before the patch keep running the old emulator code. The Azahar log shows
`ApplyCodePatch: ... patching code.bin` when it works.

## GBC ROM

Apply `patches/gbc/Shantae_warpsquid_fix.ips` with any IPS patcher (Floating IPS, Rom Patcher JS, ...) to the
US ROM:

| | SHA-1 |
|---|---|
| Shantae (USA), unpatched | `520e48c50f6e997fcd841ca368fc9abc1dbddec1` |
| after the patch | `6fc1ecf666cf24043998e8bd16bea0981cee0799` |

The patch changes 34 bytes at `0x542`-`0x563` and nothing else (the header checksum is left alone; the GBC
does not check it). None of its bytes overlap with these ROM hacks, so it can be combined with them
(checked on a ROM with all three applied):

- [Shantae dance floor hang bugfix](https://www.romhacking.net/hacks/3785/) by Griever
- [Shantae - Force GBA Enhanced Mode](https://www.romhacking.net/hacks/3462/) by Polar-Star
- [Shantae GBC palettes](https://www.romhacking.net/hacks/3567/) by Stewmat

On the original GBC cartridge the crash has never been reported, and in SameBoy (cycle-accurate) it never happened
in testing. Other GBC emulators were not tested. It cannot be applied to the official Switch, PS4 or PS5 releases.

## Test status

| | Result |
|---|---|
| eShop VC in Azahar, squid pickup with every input timing from 81 consecutive frames | unpatched 5/81 crash, with `code.ips` 0/81 |
| ROM fix in SameBoy and PyBoy with the interrupt forced into the race window | unpatched ROM crashes every time, patched ROM never |
| Real 3DS (New Nintendo 3DS LL, Luma3DS v13.3.3) with `code.ips` | boots, patch applied, squid collected without a crash (a single run, so not proof) |
| Switch port | not analysed (different emulator) |
| PS4 release (Limited Run Carbon engine) | not tested on a PS4. Its GBC ROM has the same helper bug and its emulator also treats the DMA stall as free (found in the executable); SameBoy with free DMA and that ROM: 5/121 crash, with the IPS 0/121. No crash reports known |

If you try it on a real 3DS, please open an issue with the "Test report" template (console, Luma3DS version,
whether the crash still happens, and whether the game otherwise behaves normally).

## Building the patches yourself

The scripts need only Python 3. They check the original bytes and refuse anything else.

```
python tools/fix_farcall.py shantae.gbc Shantae_warpsquid_fix.ips   # or out.gbc for a patched ROM
python tools/dmastall.py code.bin code.ips                          # or out.bin for a patched code.bin
```

This repository contains no ROMs, CIAs or Nintendo code: only the patches and the scripts that make them.
Use your own dumps.

## How this was made

The investigation, both fixes, the scripts and this documentation were done with an AI coding agent
(Claude by Anthropic) under human direction. The claims rest on the reproductions in [WRITEUP.md](WRITEUP.md),
not on the AI's word; if something does not hold up, please open an issue.

## Disclaimer

Fan-made fix, not affiliated with or endorsed by WayForward, Nintendo or Limited Run Games.
Use at your own risk.
