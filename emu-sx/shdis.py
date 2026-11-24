import capstone as c
md=c.Cs(c.CS_ARCH_SH,c.CS_MODE_SH3|c.CS_MODE_BIG_ENDIAN)
def dis(bus,start,n=40):
    out=[]
    for k in range(n):
        a=start+2*k
        w=bus.read16(a)
        raw=bytes([w>>8,w&255])
        ins=list(md.disasm(raw,a))
        txt=f"{ins[0].mnemonic} {ins[0].op_str}" if ins else ".word"
        out.append(f"{a:08x}: {w:04x}  {txt}")
    return "\n".join(out)
