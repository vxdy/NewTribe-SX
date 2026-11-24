"""Boot emulated ESX-1 (flash+NAND images from emu_update.py, factory card), open GLOBAL, walk all pages with the
cursor keys (and turn the VALUE encoder on each page), print the LCD.  usage: python verify_global.py [prefix]
(prefix of <prefix>_flash.bin/<prefix>_nand.bin; default = factory images of emu-sx)"""
import sys
from pathlib import Path
EMU = Path(r"C:\Users\Marco\Desktop\newtribe-sx\emu-sx")
sys.path.insert(0, str(EMU))
from rmachine import RMachine
pre = sys.argv[1] if len(sys.argv) > 1 else None
flash = Path(pre + "_flash.bin" if pre else EMU/"out_flash.bin").read_bytes()
nand = Path(pre + "_nand.bin" if pre else EMU/"out_nand.bin").read_bytes()
card = (EMU/"card_factory.cache").read_bytes()
m = RMachine(flash, card_present=True); m.fast_delays = True
m.set_nand(1, nand, 0x98, 0x75); m.set_nand(0, card, 0xEC, 0x75); m.tmu.scale = 1
d = 0
while d < 330_000_000: d += m.run(1_000_000)
def lcd(): return [x[:8].rstrip().replace("\x08", "").replace("\x09", "") for x in m.lcd.text()]
def raw(): return [x[:12] for x in m.lcd.text()]
def tap(keys, n=12_000_000):
    m.keys.pressed = set(keys); m.run(n); m.keys.pressed = set(); m.run(n)
GLOBAL, RIGHT, LEFT = (11, 16), (8, 16), (8, 128)
print("main:", lcd()); tap({GLOBAL}); print("GLOBAL:", lcd())
seq = []
for i in range(9):
    seq.append(tuple(lcd())); print("page", i, raw(), end="")
    m.turn(1); up = lcd()[1]; m.turn(-1); print("  +1:", up, " -1:", lcd()[1], flush=True)
    tap({RIGHT})
print("left walk:")
for i in range(9):
    tap({LEFT}); print("  ", lcd())
tap({(11, 16)}); print("GLOBAL again:", lcd())
for k in range(8): tap({RIGHT})
print("at end:", lcd(), "illegal", m.cpu.illegal_log)
for i in range(3): tap({(10,16)}); 
print("after song key:", lcd())
cave = bytes(m.bus.read8(a) for a in range(0x0C080650, 0x0C080650 + 8))
print("pc", hex(m.cpu.pc))
