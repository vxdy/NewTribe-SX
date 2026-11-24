from fwd import *
import struct
def pools(val):
    pat=struct.pack('>I',val);i=0;ps=set()
    while True:
        i=P.find(pat,i)
        if i<0:break
        if (BASE+i)%4==0: ps.add(BASE+i)
        i+=1
    return ps
def users(val):
    ps=pools(val); out=[]
    for a in range(BASE,BASE+0x70000,2):
        w=r16(a)
        if w>>12==0xD and ((a+4)&~3)+(w&0xff)*4 in ps: out.append(a)
    return out
def callers(target):
    out=[]
    for a in range(BASE,BASE+0x70000,2):
        w=r16(a)
        if w>>12==0xB:
            d=w&0xfff
            if d&0x800:d-=0x1000
            if a+4+2*d==target: out.append(a)
    return out
def func_start(a):
    # scan back for sts.l pr,@-r15 (4f22) possibly preceded by pushes
    while a>BASE:
        if r16(a)==0x4f22:
            b=a
            while r16(b-2)>>8 == 0x2f and (r16(b-2)&0xf)==6: b-=2
            return b
        a-=2
    return None
