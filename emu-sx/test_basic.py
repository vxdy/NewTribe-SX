import struct, unittest
from bus import Bus, Region
from sh3 import SH3
import container

def cpu_with(words, **regs):
    bus = Bus()
    code = b"".join(struct.pack(">H", w) for w in words)
    bus.add_region(Region(0, 0x1000, code, writable=True))
    bus.add_region(Region(0x0C000000, 0x10000))
    c = SH3(bus)
    c.pc = 0
    c.set_sr(0)
    for k, v in regs.items():
        c.r[int(k[1:])] = v
    return c

class Cpu(unittest.TestCase):
    def test_mov_add(self):
        c = cpu_with([0xE105, 0x7103, 0x0009]); c.run(3)       # mov #5,r1; add #3,r1
        self.assertEqual(c.r[1], 8)
    def test_delay_slot_runs_before_branch(self):
        c = cpu_with([0xA001, 0x7101, 0x7102, 0x7104, 0x0009])  # bra +; add #1,r1 (slot); add #2 skipped; add #4 target
        c.run(3); self.assertEqual(c.r[1], 1 + 4)
    def test_literal_load_aligned(self):
        c = cpu_with([0x0009, 0xD101, 0x0009, 0x0009, 0x1234, 0x5678]); c.run(2)   # mov.l @(1,pc),r1 at 2 -> (2+4&~3)+4=8
        self.assertEqual(c.r[1], 0x12345678)
    def test_subc(self):
        c = cpu_with([0x3108, 0x310A, 0x0009]); c.r[0] = 1; c.r[1] = 5   # sub r0,r1 ; subc r0,r1 (T=0)
        c.run(2); self.assertEqual(c.r[1], 3)
    def test_div1_32_by_16(self):
        # Hitachi manual: shll16 r0; div0u; 16 x div1 r0,r1; rotcl r1; extu.w r1,r1  -> r1 = r1 / (r0 >> 16)
        prog = [0x4028, 0x0019] + [0x3104] * 16 + [0x4124, 0x611D]
        c = cpu_with(prog); c.r[0] = 7; c.r[1] = 50000
        c.run(len(prog)); self.assertEqual(c.r[1], 50000 // 7)
    def test_dmuls(self):
        c = cpu_with([0x311D]); c.r[1] = 0xFFFFFFFD          # dmuls.l r1,r1 = (-3)*(-3)
        c.run(1); self.assertEqual((c.mach, c.macl), (0, 9))
    def test_exception_illegal(self):
        c = cpu_with([0xFFFF]); c.run(1)
        self.assertEqual(c.illegal_log[0][1], 0xFFFF)
        self.assertEqual(c.pc, 0x180)

class Container(unittest.TestCase):
    def test_sum_and_fix(self):
        body = bytes(range(256)) * 4
        data = bytearray(b"KORG\0\0\0q" + b"BSS 01020000" + b"\0" * 16 + body)
        data += b"\0" * (0x200000 - len(data))
        fixed = container.fix_sum(bytes(data), len(data) - 4)
        self.assertEqual(container.word_sum(fixed), 0)
        self.assertTrue(container.check(fixed).ok)
        broken = bytearray(fixed); broken[0x100] ^= 1
        self.assertFalse(container.check(bytes(broken)).ok)

if __name__ == "__main__":
    unittest.main()
