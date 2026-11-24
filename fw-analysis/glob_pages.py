import sys
sys.path.insert(0,'.'); sys.path.insert(0,'scratch')
from cardenv import m, txt, tap
def raw(): return [repr(x) for x in m.lcd.text()]
G=(11,16); RIGHT=(8,16); LEFT=(8,128)
tap({G}); print("enter", raw())
for i in range(8):
    base=raw()
    m.turn(1); up=raw(); m.turn(-1); dn=raw()
    print(i, base, "| +1:", up[1], "| back:", dn[1], flush=True)
    tap({RIGHT})
print("now", raw())
for i in range(8):
    tap({LEFT}); print("left", i, raw())
