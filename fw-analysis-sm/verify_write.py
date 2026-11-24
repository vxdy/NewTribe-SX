import sys
exec(open('verify_global.py').read().split('print("main:"')[0])
tap({GLOBAL})
for i in range(7): tap({RIGHT})
print("page7:", lcd())
tap({(9,1)}); print("WRITE:", lcd())
m.turn(1); print("turn:", lcd())
tap({(9,1)}, 40_000_000); print("after write:", lcd())
m.run(60_000_000); print("later:", lcd(), "illegal", m.cpu.illegal_log)
