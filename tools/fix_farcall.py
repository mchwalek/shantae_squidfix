#!/usr/bin/env python3
"""ROM fix for the Shantae (GBC) warp-squid crash: make the far-call helper at $0540 reentrant.

The original helper stored the jump target in $C200/$C201 and read it back ~17 instructions later.
A VBlank interrupt in between (its task queue also far-calls) overwrote the target, so the main
thread jumped into the wrong code and ended in an endless `rst $38` loop that wipes SRAM (the save).
The new helper re-reads the target from the inline bytes next to the return address on the stack.

Usage: fix_farcall.py shantae.gbc out.gbc|out.ips
"""
import sys

ORIG = bytes.fromhex(
    'e15f2aea00c22aea01c22a57e5f091f5216405e5fa00c26ffa01c2677ae091ea00207be9')
NEW = bytes.fromhex(
    'e1'      # pop hl          ; hl -> inline lo,hi,bank
    '5f'      # ld e,a
    '232323'  # inc hl x3       ; hl = return address
    'e5'      # push hl
    'f091'    # ldh a,($ff91)
    'f5'      # push af         ; caller bank
    '216405'  # ld hl,$0564
    'e5'      # push hl         ; return stub
    'f804'    # ld hl,sp+4
    '2a'      # ld a,(hl+)
    '66'      # ld h,(hl)
    '6f'      # ld l,a          ; hl = return address
    '2b'      # dec hl
    '56'      # ld d,(hl)       ; d = bank
    '2b'      # dec hl
    '3a'      # ld a,(hl-)      ; a = hi
    '6e'      # ld l,(hl)
    '67'      # ld h,a          ; hl = target
    '7a'      # ld a,d
    'e091'    # ldh ($ff91),a
    'ea0020'  # ld ($2000),a
    '7b'      # ld a,e
    'e9'      # jp hl
).ljust(len(ORIG), b'\0')
OFF = 0x540


def patch(rom):
    assert rom[OFF:OFF + len(ORIG)] == ORIG, 'unexpected ROM (not Shantae US, or already patched)'
    return rom[:OFF] + NEW + rom[OFF + len(NEW):]


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    rom = open(sys.argv[1], 'rb').read()
    out = patch(rom)
    if sys.argv[2].endswith('.ips'):
        diff = [i for i in range(len(rom)) if rom[i] != out[i]]
        lo, hi = diff[0], diff[-1] + 1
        data = b'PATCH' + lo.to_bytes(3, 'big') + (hi - lo).to_bytes(2, 'big') + out[lo:hi] + b'EOF'
    else:
        data = out
    open(sys.argv[2], 'wb').write(data)
