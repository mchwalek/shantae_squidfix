# Why Shantae crashes on warp squids in the 3DS Virtual Console

## The symptom

Since the 2013 eShop release, players have reported that collecting a baby warp squid in *Shantae* (GBC) on the 3DS
Virtual Console sometimes freezes the game on a solid blue screen (sometimes with garbage on screen), and that after a
reset the save file is sometimes gone. The Switch port (2021) shows the same crash. Nobody reported it on the original GBC cartridge.
The Shantae Wiki lists the cause as unknown.

## Short version

1. The game calls code in other ROM banks through a small helper at ROM address `0x0540`. The helper parks the jump
   target in two fixed RAM bytes (`$C200/$C201`) and reads them back 17 instructions later.
2. The VBlank interrupt handler re-enables interrupts and, from its task queue, also far-calls through the same helper.
   If VBlank fires inside that window, the interrupt overwrites `$C200/$C201`.
3. The main code then jumps to the interrupt's target with its own ROM bank mapped, lands in the middle of an unrelated
   routine, unbalances the stack and eventually reaches address `0x0038`.
4. `0x0038` holds `0xFF` = `rst $38`, a call to `0x0038` itself. The CPU recurses forever, and every iteration pushes
   two bytes. The stack walks down through work RAM, **cartridge save RAM (the save file)**, video RAM and palette RAM:
   the screen turns one colour and the save is overwritten.
5. On real hardware the main code is always done with its far calls long before VBlank, so the window is never hit.
   The 3DS VC emulator does not charge any LCD time for the CPU stall during GDMA copies, which the VBlank handler uses
   for its graphics queue. The handler ends about 14 scanlines early, the main code runs ahead, and in the squid pickup
   frame its far call lands next to the following VBlank.

Two fixes, each sufficient on its own: make the helper reentrant (ROM patch) or make the emulator charge the DMA stall
(3DS `code.ips`).

## Background: far calls on the Game Boy Color

The SM83 CPU addresses 64 KB. `0x0000-0x3FFF` is always ROM bank 0; `0x4000-0x7FFF` shows one of the cartridge's 16 KB
banks (this game: 4 MB, MBC5, bank select by writing `$2000`). Code in another bank cannot simply be `call`ed: the bank
has to be switched in first and restored afterwards. The bank register is write-only, so the game mirrors the current
bank in HRAM `$FF91`.

Shantae's convention is `call $0540` followed by three data bytes, `target_lo, target_hi, bank`:

```
00:0ef9  cd 40 05   call $0540
00:0efc  00 40 13   .db $00,$40,$13   ; call bank $13, address $4000
00:0eff  ...                          ; execution resumes here
```

The helper reads the three bytes through the return address, pushes a return stub at `$0564` that restores the caller's
bank, switches the bank and jumps. Register `A` is passed through to the callee (stashed in `E` meanwhile), `HL` is
used for the jump.

## The original helper

```
00:0540  e1        pop hl              ; hl = address of the 3 inline bytes
00:0541  5f        ld e,a              ; save A (caller's argument)
00:0542  2a        ld a,(hl+)          ; target lo
00:0543  ea 00 c2  ld ($c200),a        ; store in a shared global   <-- window opens
00:0546  2a        ld a,(hl+)          ; target hi
00:0547  ea 01 c2  ld ($c201),a
00:054a  2a        ld a,(hl+)          ; bank
00:054b  57        ld d,a
00:054c  e5        push hl             ; real return address (after the inline bytes)
00:054d  f0 91     ldh a,($ff91)       ; caller's ROM bank
00:054f  f5        push af
00:0550  21 64 05  ld hl,$0564
00:0553  e5        push hl             ; callee's ret lands on the stub at $0564
00:0554  fa 00 c2  ld a,($c200)        ; read the target back       <-- window closes
00:0557  6f        ld l,a
00:0558  fa 01 c2  ld a,($c201)
00:055b  67        ld h,a              ; hl = target
00:055c  7a        ld a,d
00:055d  e0 91     ldh ($ff91),a
00:055f  ea 00 20  ld ($2000),a        ; switch bank
00:0562  7b        ld a,e              ; restore A
00:0563  e9        jp hl

00:0564  f1        pop af              ; return stub
00:0565  e0 91     ldh ($ff91),a
00:0567  ea 00 20  ld ($2000),a        ; restore caller's bank
00:056a  c9        ret
```

The temporary state lives in a fixed global instead of on the stack, a classic non-reentrancy bug. The VBlank handler
(vector `0x40` -> `jp $0884`) saves registers, executes `ei` at `0x0a96` to allow nested interrupts, and at `0x0aab`
runs its deferred-task queue (`0x06d8`). Task kinds 2 and 3 are far calls to `01:4139` and `01:4163` through the same
helper. Kind 2 suspends the music; it is queued when an item-get jingle starts, which is exactly what picking up a warp
squid does.

## How it was found

- The crashed state has `PC=0x0038` and `SP=0x0001`, and save RAM and the palette buffer are filled with `39 00`, the
  return address `0x0039` pushed by the endless `rst $38`. Palette entries of `0x3900` are dark blue: the blue screen.
- The bottom of the stack showed the first push at `SP=0xCFFD` without a preceding call, so the CPU arrived at `0x0038`
  by a jump into the wrong code.
- In Azahar, a scripted sweep of the button-press timing reproduced the crash reliably at one specific delay.
- With a trap placed at `0x0038` in the emulated ROM, the crash froze with `A=12 F=20 BC=FAB7 DE=13B2 HL=214E`,
  bank `01`, and `$C200/$C201 = 39 41`: the interrupt's target `0x4139`. The main code had been executing the object
  update far call `call $0540 / 00 40 13` (bank `$13`, `0x4000`).
- In PyBoy, writing `39 41` into `$C200/$C201` at `0x0554` in the frame before the pickup produced exactly the same
  registers at `0x0038`.

## Why only in the emulator

In normal frames the main loop finishes its work early and waits for VBlank (`0x0851`). The squid pickup switches the
sound bank inside the VBlank handler, which makes that handler run into the next frame; the main code's far calls then
happen late, close to the next VBlank, whose handler runs the suspend-music task.

The GBC's GDMA (`FF55` with bit 7 clear) copies 16-byte blocks while the CPU is halted (16 M-cycles per block in double
speed mode); the LCD keeps running. The 3DS VC emulator copies instantly, and the stall only shortens the next CPU time
slice without advancing the LCD and timers. A timing log written by the ROM into save RAM showed:

| | VBlank handler length (scanlines) | main loop reaches its wait (scanline) |
|---|---|---|
| 3DS VC 0.124, unpatched | 6-8 | 91-98 |
| 3DS VC 0.124 + `code.ips` | 17-21 | 100-109 |
| SameBoy (cycle-accurate) | 19-24 | 102-116 |

In the pickup frame the object-update far call starts about 9 scanlines after VBlank in the VC instead of about 20, and
depending on the exact input frame (about 1 in 16) VBlank lands inside the 17-instruction window. Every other timing
difference of the VC emulator (free interrupt dispatch, immediate `ei`, minimum mode 3 length) also makes the emulated CPU
faster relative to the LCD; instruction timings themselves are exact.

The Switch port uses a different emulator and was not analysed; the crash there suggests a similar DMA shortcut.

The PS4 release (Limited Run Games' Carbon engine, 2023) has the same shortcut: its GBC core performs general DMA and
HBlank DMA without charging any CPU cycles. Its two ROMs (original and "enhanced" GBA mode) only change text, button
prompts and graphics; the far-call helper at `0x0540` is unchanged, so the crash should be possible there too (no reports
known, not tested on a PS4). The ROM IPS applies to both unchanged.

Not only squids: the suspend-music task is also queued by the item-get scripts for keys, transformation items,
fireflies and heart holders, so those pickups can hit the same window (static analysis only).

## Fix 1: reentrant helper (ROM)

Never copy the target to a global. Re-read it from the inline bytes in ROM, found through the return address that is
already on the stack. Every interrupt has its own stack frame, so a nested far call cannot disturb the outer one.

```
00:0540  e1        pop hl              ; hl -> inline bytes
00:0541  5f        ld e,a              ; save A
00:0542  23 23 23  inc hl x3           ; hl = return address
00:0545  e5        push hl
00:0546  f0 91     ldh a,($ff91)
00:0548  f5        push af             ; caller's bank
00:0549  21 64 05  ld hl,$0564
00:054c  e5        push hl             ; return stub
00:054d  f8 04     ld hl,sp+4          ; hl -> return-address slot on the stack
00:054f  2a        ld a,(hl+)
00:0550  66        ld h,(hl)
00:0551  6f        ld l,a              ; hl = return address
00:0552  2b        dec hl
00:0553  56        ld d,(hl)           ; bank     = [ret-1]
00:0554  2b        dec hl
00:0555  3a        ld a,(hl-)          ; target hi = [ret-2]
00:0556  6e        ld l,(hl)           ; target lo = [ret-3]
00:0557  67        ld h,a
00:0558  7a        ld a,d
00:0559  e0 91     ldh ($ff91),a
00:055b  ea 00 20  ld ($2000),a
00:055e  7b        ld a,e
00:055f  e9        jp hl
00:0560  00 00 00 00                   ; padding up to the unchanged stub at $0564
```

Same calling convention, same registers (A preserved, HL clobbered), same return stub. Nothing else reads or writes
`$C200/$C201`. Result: 34 changed bytes at `0x542`-`0x563`.

## Fix 2: charge the DMA stall (3DS VC emulator)

The VC emulator (`code.bin`, a hand-written ARM interpreter) handles the stall at the top of its frame loop
(`0x17e5dc` in build 0.124):

```
ldr   r0, =stall
ldr   r2, [r0]
cmp   r2, #0
beq   run
ldr   r1, =limit         ; CPU slice length
mov   ip, #0
ldr   r3, [r1]
cmp   r2, r3
suble r2, r3, r2         ; stall <= limit: limit -= stall, stall = 0
strle r2, [r1]
subgt r2, r2, r3         ; stall > limit:  stall -= limit, limit = 0
strle ip, [r0]
strgt r2, [r0]
strgt ip, [r1]
nop
run:
bl    cpu_run            ; resets the cycle counter; LCD/timers advance by executed cycles only
```

The stall only shortens the CPU slice. Because the CPU run function resets the cycle counter and the LCD and timers are
advanced by that counter, the stalled cycles never reach them. The patched block (same 60 bytes) spends the stall as
elapsed time without running the CPU:

```
ldr   r0, =stall
ldr   r2, [r0]
cmp   r2, #0
beq   run
ldr   r1, =limit
ldr   r3, [r1]
cmp   r2, r3
movgt r2, r3             ; consume = min(stall, limit)
cmp   r2, #0
ble   run
ldr   r3, [r0]
sub   r3, r3, r2
str   r3, [r0]           ; stall -= consume
str   r2, [r5]           ; cycle counter = consume (elapsed time for LCD/timers)
b     after_run          ; skip the CPU this iteration
run:
bl    cpu_run
```

## Evidence

| Test | Result |
|---|---|
| Azahar, eShop VC, Right held from each of 81 consecutive input frames | 5/81 crash (deterministic, 10/10 on rerun) |
| same with `code.ips` | 0/81 |
| SameBoy (cycle-accurate), stock ROM, 121 input timings | 0/121 crash |
| SameBoy with GDMA stall made free (VC behaviour), stock ROM | 2/121 crash |
| SameBoy with GDMA stall made free, PS4 ROM (original / enhanced) | 5/121 / 2/121 crash; with the IPS 0/121 each |
| SameBoy, race forced by hand, stock ROM / patched ROM | 3/3 crash / 0/3 |
| PyBoy, patched ROM, interrupt forced inside the helper (108 trials) | 0 crashes |

| Real 3DS (New Nintendo 3DS LL, Luma3DS v13.3.3), `code.ips` | boots, patch applied, squid collected without a crash (single run) |

Not tested yet: the crash rate on a real 3DS over many pickups, the Switch port, and the PS4 release on a console.

The investigation, the fixes and this write-up were done with an AI coding agent (Claude by Anthropic) under human
direction.
