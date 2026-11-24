import sys
import time
from pathlib import Path

from rmachine import RMachine

flash = Path("out_flash.bin").read_bytes()
nand = Path("out_nand.bin").read_bytes()
m = RMachine(flash)
m.fast_delays = True
m.set_nand(1, nand, 0x98, 0x75)
m.tmu.scale = float(sys.argv[2]) if len(sys.argv) > 2 else 50
limit = int(sys.argv[1]) if len(sys.argv) > 1 else 120_000_000
d = 0
last = None
t0 = time.time()
while d < limit and time.time() - t0 < 100:
    d += m.run(500_000)
    tx = tuple(x.rstrip() for x in m.lcd.text())
    key = (tx[0], tx[1] if not tx[1].startswith("Wait") else "Wait")
    if key != last:
        print(d, round(time.time() - t0, 1), [repr(x) for x in tx], hex(m.cpu.pc), flush=True)
        last = key
dt = time.time() - t0
print("end", d, round(dt, 1), "s;", round(d / dt / 1e6, 1), "Mi/s; pc", hex(m.cpu.pc), "illegal", m.cpu.illegal_log, "ticks", m.tmu.underflows)
