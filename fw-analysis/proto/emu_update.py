"""Run the genuine card update in the emulator with a given BSS and save flash/NAND images.
usage: python emu_update.py <BSS file> <out prefix> [existing internal NAND image to update over]"""
import sys, time
from pathlib import Path
EMU = Path(r"C:\Users\Marco\Desktop\newtribe-sx\emu-sx"); FW = EMU.parent / "factory-firmware"
sys.path.insert(0, str(EMU))
import container, smartmedia
from rmachine import RMachine
bss = Path(sys.argv[1]); pre = sys.argv[2]
files = [("ESX0101F.BFS", (FW/"ESX0101F.BFS").read_bytes()), ("ESX0102N.BSS", bss.read_bytes()), ("ESX0102D.BDS", (FW/"ESX0102D.BDS").read_bytes())]
for n, d in files: print(n, container.check(d, n).ok, container.check(d, n).problems)
card = smartmedia.build_card(files)
m = RMachine(container.payload(files[0][1]), card_present=True)
m.set_nand(0, card, 0xEC, 0x73); m.set_nand(1, (Path(sys.argv[3]).read_bytes() if len(sys.argv)>3 else smartmedia.formatted_blank(32)), 0x98, 0x75)
m.keys.pressed = {(8, 0x10), (8, 0x80)}; m.fast_delays = True
d = 0; last = None; stage = 0; t0 = time.time()
while time.time() - t0 < 600:
    d += m.run(1_000_000)
    tx = tuple(x.strip() for x in m.lcd.text())
    if tx != last: print(d, tx, flush=True); last = tx
    if tx == ('SysVerUp', 'Sure?') and stage == 0: m.keys.pressed = {(9, 4)}; stage = 1
    if tx == ('Turn OFF', 'Please') or (tx[0].startswith('CkSum')): break
Path(pre + "_flash.bin").write_bytes(m.flash_bytes()); Path(pre + "_nand.bin").write_bytes(m.nand_data(1))
print("done", d, tx)
