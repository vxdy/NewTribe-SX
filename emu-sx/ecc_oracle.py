import random
from machine import Machine
from nand import Chip
import container, smartmedia
from pathlib import Path
img=container.payload(Path("../factory-firmware/ESX0101F.BFS").read_bytes())
m=Machine(img); m.fast_delays=True; cpu=m.cpu
d=0
while d<2_000_000: d+=m.run(500_000)
SENT=0x0c200000; m.bus.write16(SENT,0xAFFE)
chip=Chip(0xEC,0x73,16); m.nand_chips[0]=chip
m.ports.v[0x04000128]=0x42     # window on, chip index 0 selected (bit 3 low), data cycle
def oracle(data):
    chip.cmd=0; chip.buf=bytes(data); chip.pos=0
    for i in range(16): m.bus.write8(0x0c100200+i,0xAA)
    save=(list(cpu.r),cpu.pc,cpu.pr)
    cpu.r[15]=0x0c3ffff0; cpu.r[4]=0x0c100000; cpu.r[5]=0x0c100200; cpu.pr=SENT; cpu.pc=0x0c000ed8
    n=0
    while cpu.pc!=SENT and n<200000: cpu.run(100); n+=100
    cpu.r[:],cpu.pc,cpu.pr=save
    return bytes(m.bus.read8(0x0c100200+i) for i in range(6)), bytes(m.bus.read8(0x0c100000+i) for i in range(4))
if __name__=="__main__":
    random.seed(1)
    tests=[bytes(256),bytes([0xff])*256]+[bytes(random.getrandbits(8) for _ in range(256)) for _ in range(3)]
    for k in (0,1,2,3,7,8,9,255):
        t=bytearray(256); t[k]=1; tests.append(bytes(t))
    for t in tests:
        o,c=oracle(t)
        print(o.hex(), c.hex(), smartmedia.ecc256(t).hex())
