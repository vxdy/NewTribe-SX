"""Install the custom (Newtribe) firmware via the real card-update path in the emulator and
write custom_flash.bin / custom_nand.bin, which the native app's "Neustart (custom)" uses.
usage: python make_custom.py [BSS]   (default: fw-src/build/ESX0102N.BSS, else fw-analysis/proto/ESX0102N_proto.BSS)"""
import sys, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
cands = [ROOT/"fw-src"/"build"/"ESX0102N.BSS", ROOT/"fw-analysis"/"proto"/"ESX0102N_proto.BSS"]
bss = Path(sys.argv[1]) if len(sys.argv) > 1 else next((c for c in cands if c.exists()), None)
if not bss or not bss.exists(): sys.exit("no custom BSS found")
print("using", bss)
tool = ROOT/"fw-analysis"/"proto"/"emu_update.py"
subprocess.check_call([sys.executable, str(tool), str(bss), str(Path(__file__).parent/"custom_tmp")])
import os
here = Path(__file__).parent
os.replace(here/"custom_tmp_flash.bin", here/"custom_flash.bin")
os.replace(here/"custom_tmp_nand.bin", here/"custom_nand.bin")
print("written custom_flash.bin / custom_nand.bin from", bss)
