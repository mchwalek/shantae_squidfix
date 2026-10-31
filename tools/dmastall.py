#!/usr/bin/env python3
"""3DS GBC Virtual Console emulator fix: make GDMA/HDMA CPU stalls take LCD/timer time.

In the VC frame loop the DMA stall only shortened the next CPU slice; the time handed to the
LCD and timers was the executed CPU cycles only, so DMA was free. The new code consumes
min(stall, limit) cycles as elapsed time without running the CPU (the CPU is halted during
GDMA on hardware too). 60 bytes, same size, position-independent.

Usage: dmastall.py code.bin out.bin|out.ips
The code.ips offsets are code.bin file offsets (Luma3DS / Azahar format).
"""
import struct
import sys

ORIG = bytes.fromhex(
    "88029fe5002090e5000052e3090000" "0a7c129fe500c0a0e3003091e5030052e1"
    "022043d0002081d5032042c000c080d5002080c500c081c5" "00f020e3")
RUN, AFTER_RUN = 0x3c, 0x40  # offsets of the `bl cpu_run` right after the block and of the instruction after it


def b(cond, at, to): return struct.pack('<I', (cond << 28) | (0xa << 24) | (((to - at - 8) >> 2) & 0xffffff))
def w(x): return struct.pack('<I', x)


NEW = (ORIG[0:4] + w(0xe5902000) + w(0xe3520000) + b(0x0, 12, RUN)   # ldr r0,=stall; ldr r2,[r0]; cmp r2,#0; beq run
       + ORIG[16:20] + w(0xe5913000) + w(0xe1520003) + w(0xc1a02003)  # ldr r1,=limit; ldr r3,[r1]; cmp r2,r3; movgt r2,r3
       + w(0xe3520000) + b(0xd, 36, RUN)                              # cmp r2,#0; ble run
       + w(0xe5903000) + w(0xe0433002) + w(0xe5803000)                # stall -= consume
       + w(0xe5852000) + b(0xe, 56, AFTER_RUN))                       # cycles = consume; skip CPU
assert len(ORIG) == len(NEW) == 60

if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    c = open(sys.argv[1], 'rb').read()
    assert c.count(ORIG) == 1, "code not found exactly once (unknown build, or already patched)"
    off = c.find(ORIG)
    print(f"patched at code.bin offset {off:#x}")
    if sys.argv[2].endswith('.ips'):
        data = b'PATCH' + off.to_bytes(3, 'big') + len(NEW).to_bytes(2, 'big') + NEW + b'EOF'
    else:
        data = c[:off] + NEW + c[off + 60:]
    open(sys.argv[2], 'wb').write(data)
