import sys
sys.path.insert(0,'.')
import shisa
import os; p=open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','factory-firmware','ESX0102N.BSS'),'rb').read()[0x20:]
BASE=0x0C080000
def view(a,b):
    o=a
    while o<b:
        op=(p[o]<<8)|p[o+1]
        d=shisa.decode(op)
        extra=''
        if d:
            t=shisa.targets(d[0],d[1],BASE+o)
            if t:
                to=t[1]-BASE
                if t[0]=='llit' and 0<=to<len(p)-4: extra='  ; [%08X]=%08X'%(t[1],int.from_bytes(p[to:to+4],'big'))
                elif t[0]=='wlit' and 0<=to<len(p)-2: extra='  ; [%08X]=%04X'%(t[1],int.from_bytes(p[to:to+2],'big'))
                else: extra='  ; ->%08X'%t[1]
            txt=shisa.format_insn(op,BASE+o)
        else: txt='.word 0x%04X'%op
        print('%08X: %04X  %s%s'%(BASE+o,op,txt,extra))
        o+=2
if __name__=='__main__':
    view(int(sys.argv[1],0)-BASE if int(sys.argv[1],0)>=BASE else int(sys.argv[1],0), (int(sys.argv[2],0)-BASE if int(sys.argv[2],0)>=BASE else int(sys.argv[2],0)))
