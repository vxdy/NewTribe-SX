"""bootcheck.py BSS - update through the card path + normal boot of a BSS file; prints BOOT OK/FAIL (used by growtest.py)."""
import sys
import os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from emutest import *
bss=Path(sys.argv[1])
files=[("ESX0101F.BFS",(FW/"ESX0101F.BFS").read_bytes()),("ESX0102N.BSS",bss.read_bytes()),("ESX0102D.BDS",(FW/"ESX0102D.BDS").read_bytes())]
card=smartmedia.build_card(files)
m=RMachine((FW/"ESX0101F.BFS").read_bytes()[0x20:],card_present=True)
m.set_nand(0,card,0xEC,0x73); m.set_nand(1,smartmedia.formatted_blank(32),0x98,0x75)
m.keys.pressed={(8,0x10),(8,0x80)}; m.fast_delays=True
d=0;stage=0
while d<8_000_000_000:
    d+=m.run(500_000)
    tx=tuple(x.strip().replace("\x08","") for x in m.lcd.text())
    if tx==("SysVerUp","Sure?") and stage==0: m.keys.pressed={(9,4)}; stage=1
    if tx[0].startswith("Turn OFF"): break
nf=bytes(m.flash_bytes(0x80000)); n1=m.nand_data(1)
m2=RMachine(nf); m2.set_nand(1,n1,0x98,0x75); m2.fast_delays=True; m2.tmu.scale=1
d=0;ok=False
while d<400_000_000:
    d+=m2.run(1_000_000)
    tx=tuple(x.rstrip().replace("\x08","").replace("\x09","") for x in m2.lcd.text())
    if tx[0] and "A.01" in tx[1]: ok=True; break
print('BOOT', 'OK' if ok else 'FAIL', tx, hex(m2.cpu.pc))
import os; sys.stdout.flush(); os._exit(0)
