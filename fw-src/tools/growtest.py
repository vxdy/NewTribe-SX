"""growtest.py PART.s NTH [NOPS] - growth experiment: insert NOPS nops in front of the NTH function label of src/PART.s, rebuild
(RAM filler shrinks accordingly), run the update + boot in the emulator (bootcheck.py).  Shows that the sources relocate.
Example: python tools/growtest.py part_0C0A8988.s 4 1"""
import sys, re, os, shutil, subprocess
from pathlib import Path
R=Path(__file__).resolve().parent.parent
part=sys.argv[1]; nth=int(sys.argv[2]) if len(sys.argv)>2 else 0
d=R/'build'/('growth_'+part+'_%d'%nth)
if d.exists(): shutil.rmtree(d)
d.mkdir(parents=True)
shutil.copytree(R/'src',d/'src'); shutil.copytree(R/'data',d/'data'); shutil.copy(R/'header.json',d/'header.json')
p=d/'src'/part
t=p.read_text()
ms=list(re.finditer(r'^(func_[0-9A-F]+:\n)',t,re.M))
m=ms[nth]
NN=int(sys.argv[3]) if len(sys.argv)>3 else 2
t=t[:m.start()]+"\tnop\n"*NN+t[m.start():]; print("INS",m.group(1).strip(),NN)
p.write_text(t)
z=(d/'src/zz_pad.s').read_text().replace('\t.org\t0x0C0ED9F0, 0\n','').replace('"../data/ram_pad.bin"','"../data/ram_pad.bin", . - 0x0C0ED9F0, 0x0C27FFE0 - .')
(d/'src/zz_pad.s').write_text(z)
r=subprocess.run([sys.executable,str(R/'tools/build.py'),'--src',str(d/'src'),'--out',str(d/'out.BSS'),'--header',str(d/'header.json'),'--map',''],capture_output=True,text=True)
print(r.stdout.strip()[-200:],r.stderr.strip()[-300:])
if r.returncode: sys.exit(1)
r=subprocess.run([sys.executable,str(R/'tools/bootcheck.py'),str(d/'out.BSS')],capture_output=True,text=True)
print(part,nth,'->',r.stdout.strip()[-300:])
