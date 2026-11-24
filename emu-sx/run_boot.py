"""Boots the emulated unit from the flash and NAND images that run_update.py produced (no card, no keys)."""
import sys,time
from machine import Machine
from nand import Chip
from pathlib import Path
flash=Path("out_flash.bin").read_bytes()
nand=Path("out_nand.bin").read_bytes()
m=Machine(flash); m.fast_delays=True; cpu=m.cpu
m.nand_chips[0]=None
m.nand_chips[1]=Chip(0x98,0x75,32,nand)
m.ports.inputs[0x0400012A]=lambda: 0x0C
m.ports.inputs[0x04000134]=lambda: (m.ports.v.get(0x04000134,0)&~0x8C)
N=int(sys.argv[1]) if len(sys.argv)>1 else 100_000_000
d=0;last=None;t0=time.time()
import collections
hist=collections.Counter()
while d<N and time.time()-t0<1500:
    d+=m.run(250_000); hist[cpu.pc>>8]+=1
    tx=tuple(x.strip() for x in m.lcd.text())
    if tx!=last: print(d,round(time.time()-t0),tx,hex(cpu.pc),flush=True); last=tx
print("pc hist",[(hex(k<<8),v) for k,v in hist.most_common(6)])
print("lcd",[x for x in m.lcd.text()])
print("end",d,hex(cpu.pc),cpu.sleeping,cpu.illegal_log[:3],{(k,hex(a)):v for (k,a),v in list(m.bus.unmapped.items())[:20]})
