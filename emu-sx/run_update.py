"""Runs the whole card update in the emulator and stores the resulting flash and NAND images."""
import sys,time,pickle
from machine import Machine
from nand import Chip
import container, smartmedia
from pathlib import Path
FW=Path("../factory-firmware-sm")
img=container.payload((FW/"ESX0101F.BFS").read_bytes())
card=open("card.cache","rb").read()
m=Machine(img); m.fast_delays=True; cpu=m.cpu
m.nand_chips[0]=Chip(0xEC,0x73,16,card)
m.nand_chips[1]=Chip(0x98,0x75,32,smartmedia.formatted_blank(32))
m.ports.inputs[0x0400012A]=lambda: 0x0C
m.ports.inputs[0x04000134]=lambda: (m.ports.v.get(0x04000134,0)&~0x8C)|0x80
m.keys.pressed={(8,0x10),(8,0x80)}
d=0;last=None;stage=0;t0=time.time();idle=0
while time.time()-t0<3000:
    d+=m.run(250_000)
    tx=tuple(x.strip() for x in m.lcd.text())
    if tx!=last:
        print(d,round(time.time()-t0),tx,hex(cpu.pc),flush=True); last=tx; idle=0
    else: idle+=1
    if tx==('SysVerUp','Sure?') and stage==0:
        m.keys.pressed={(9,4)}; stage=1
    if tx==('Turn OFF','Please'): break
open("out_flash.bin","wb").write(bytes(m.flash.mem[:0x80000]))
open("out_nand.bin","wb").write(bytes(m.nand_chips[1].data))
print("done",d,tx,flush=True)
