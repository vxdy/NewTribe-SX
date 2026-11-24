"""lockstep.py GROWN.BSS INS_ADDR SHIFT - runs the factory BSS and a grown build side by side (pc mapped by +SHIFT behind INS_ADDR) and
prints the first divergence (stale absolute pointer = missing relocation).  Slow (minutes)."""
import sys, ctypes as C
import os; sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from emutest import *
import rmachine as R

def update(bss):
    files=[("ESX0101F.BFS",(FW/"ESX0101F.BFS").read_bytes()),("ESX0102N.BSS",Path(bss).read_bytes()),("ESX0102D.BDS",(FW/"ESX0102D.BDS").read_bytes())]
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
    return bytes(m.flash_bytes(0x80000)), m.nand_data(1)
fo,no=update(FW/'ESX0102N.BSS')
fg,ng=update(sys.argv[1])
INS=int(sys.argv[2],0); SH=int(sys.argv[3],0)
def f(a):
    p=a&0x1FFFFFFF
    return a+SH if INS<=p<0x0C0ED9F0 else a
def mk(fl,nd):
    m=RMachine(fl); m.set_nand(1,nd,0x98,0x75); m.fast_delays=True; m.tmu.scale=1; return m
mo=mk(fo,no); mg=mk(fg,ng); L=R._lib
STEP=200000
d=0
while d<500_000_000:
    so=L.emu_snapshot(mo.h); sg=L.emu_snapshot(mg.h)
    mo.run(STEP); mg.run(STEP)
    d+=STEP
    po,pg=mo.cpu.pc,mg.cpu.pc
    if f(po)!=pg:
        L.emu_restore(mo.h,so); L.emu_restore(mg.h,sg)
        hist=[]
        for k in range(STEP):
            po,pg=mo.cpu.pc,mg.cpu.pc
            hist.append((po,pg))
            if f(po)!=pg:
                print('hist',[(hex(a),hex(b)) for a,b in hist[-8:]])
                print('DIVERGE at instr',d-STEP+k,'orig pc',hex(po),'grown pc',hex(pg))
                print('orig regs',[hex(x) for x in mo.cpu.r]); print('grown regs',[hex(x) for x in mg.cpu.r])
                break
            mo.cpu.run(1); mg.cpu.run(1)
        # print previous instruction info
        break
    L.emu_free(so); L.emu_free(sg)
else:
    print('no divergence in',d)
import os; sys.stdout.flush(); os._exit(0)
