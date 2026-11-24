import sys
sys.path.insert(0,'.'); sys.path.insert(0,'scratch')
from cardenv import m, txt, tap
open('../fw-analysis-sm/sdram_boot.bin','wb').write(bytes(m.sdram_bytes(0,0x2000000)))
