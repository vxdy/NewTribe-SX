import struct, capstone as c
md=c.Cs(c.CS_ARCH_SH,c.CS_MODE_SH3|c.CS_MODE_BIG_ENDIAN)
BASE=0x0c080000
P=open('C:/Users/Marco/Desktop/newtribe-sx/factory-firmware-sm/ESX0102N.BSS','rb').read()[0x20:]
def rd(a,n=1):
    return P[a-BASE:a-BASE+n]
def r16(a): return struct.unpack('>H',rd(a,2))[0]
def r32(a): return struct.unpack('>I',rd(a,4))[0]
def s(a):
    x=rd(a,12).split(b'\0')[0]
    return repr(x)
def dis(a,n=40,p=print):
    out=[]
    for k in range(n):
        ad=a+2*k; w=r16(ad)
        ins=list(md.disasm(struct.pack('>H',w),ad))
        t=f"{ins[0].mnemonic} {ins[0].op_str}" if ins else ".word"
        note=''
        if w>>12==0xD:
            ea=((ad+4)&~3)+(w&0xff)*4; v=r32(ea); note=f"; =[{ea:08x}]={v:08x}"
            if BASE<=v<BASE+len(P): note+=' '+s(v)
        elif w>>12==0x9:
            ea=ad+4+(w&0xff)*2; note=f"; =[{ea:08x}]={r16(ea):04x}"
        elif w>>8==0xC7:
            ea=((ad+4)&~3)+(w&0xff)*4; note=f"; mova {ea:08x}"
        out.append(f"{ad:08x}: {w:04x}  {t:28s}{note}")
    p("\n".join(out))
if __name__=='__main__':
    import sys
    dis(int(sys.argv[1],16),int(sys.argv[2]))
