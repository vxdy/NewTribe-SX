import sys
sys.argv=[sys.argv[0]]+sys.argv[1:]
exec(open('verify_global.py').read().split('print("main:"')[0])
tap({GLOBAL})
for i in range(7): tap({RIGHT})
print(m.lcd.text())
import struct
print([hex(m.bus.read32(a)) for a in (0xc0e0b50,0xc0e0b6c,0xc0e0b68)])
