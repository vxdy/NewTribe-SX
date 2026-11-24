# SPDX-License-Identifier: GPL-2.0-only
"""AMD-style 8-bit NOR flash (AM29F040 class: 512 KiB, eight 64 KiB sectors) behind a read-only Region.

Reads go straight to the region memory. Writes arrive through `write(offset, value)` (Region.write_hook):
unlock cycles 0x555 <- 0xAA, 0x2AA <- 0x55, then a command byte at 0x555:
0xA0 program (new data ANDed into old), 0x80 erase setup (followed by a second unlock and 0x10 chip erase at 0x555
or 0x30 sector erase), 0x20 unlock bypass (then `A0 data` pairs without unlock, `90 00` leaves it),
0x90 autoselect (offset 0/1 read manufacturer 01 / device A4), 0xF0 reset.
Operations finish instantly, so DQ7/DQ6 status polling reads the final data.
"""
SECTOR = 0x10000


class NorFlash:
    def __init__(self, region, size=0x80000):
        self.r, self.size = region, size
        self.unlock = 0              # 0..2 first sequence, 3..5 second sequence (after erase setup)
        self.erase_setup = False
        self.pending = None          # "program" | "bypass-reset"
        self.bypass = False
        self.autoselect = False
        self._saved = None
        self.log = []                # ("erase", sector or None)
        self.programmed = 0
        self.bad_programs = 0        # attempts to set a 0 bit back to 1
        region.write_hook = self.write

    # top-boot map of the 4 Mbit part: 7 x 64 KiB, 32 KiB, 8 KiB, 8 KiB, 16 KiB
    SECTORS = [(i * 0x10000, (i + 1) * 0x10000) for i in range(7)] + [(0x70000, 0x78000), (0x78000, 0x7A000),
                                                                      (0x7A000, 0x7C000), (0x7C000, 0x80000)]

    def _sector(self, off):
        for lo, hi in self.SECTORS:
            if lo <= off < hi:
                return lo, hi
        return off // SECTOR * SECTOR, off // SECTOR * SECTOR + SECTOR

    def _reset(self):
        if self.autoselect:
            self.r.mem[0], self.r.mem[1] = self._saved
            self.autoselect = False
        self.unlock, self.erase_setup, self.pending, self.bypass = 0, False, None, False

    def write(self, off, v):
        off %= self.size
        a = off & 0x7FF
        m = self.r.mem
        if v == 0xF0 and self.pending is None:
            self._reset()
            return
        if self.pending == "program":
            if v & ~m[off] & 0xFF:
                self.bad_programs += 1
            m[off] &= v
            self.programmed += 1
            self.pending = None
            return
        if self.pending == "bypass-reset":
            self.bypass = False
            self.pending = None
            return
        if self.bypass and self.unlock == 0:
            if v == 0xA0:
                self.pending = "program"
            elif v == 0x90:
                self.pending = "bypass-reset"
            return
        u = self.unlock
        if u in (0, 3):
            if a == 0x555 and v == 0xAA:
                self.unlock = u + 1
            else:
                self.unlock = 3 if self.erase_setup and u == 3 else 0
            return
        if u in (1, 4):
            if a == 0x2AA and v == 0x55:
                self.unlock = u + 1
            else:
                self.unlock, self.erase_setup = 0, False
            return
        # u in (2, 5): the command byte
        self.unlock = 0
        if u == 2:
            if a == 0x555 and v == 0xA0:
                self.pending = "program"
            elif a == 0x555 and v == 0x80:
                self.erase_setup = True
                self.unlock = 3
            elif a == 0x555 and v == 0x20:
                self.bypass = True
            elif a == 0x555 and v == 0x90:
                self._saved = (m[0], m[1])
                m[0], m[1] = 0x04, 0xB5
                self.autoselect = True
            return
        self.erase_setup = False
        if a == 0x555 and v == 0x10:
            m[:self.size] = b"\xff" * self.size
            self.log.append(("erase", None))
        elif v == 0x30:
            s = off // SECTOR * SECTOR
            m[s:s + SECTOR] = b"\xff" * SECTOR
            self.log.append(("erase", s // SECTOR))
