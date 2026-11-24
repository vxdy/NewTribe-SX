# SPDX-License-Identifier: GPL-2.0-only
"""Physical bus of the emulated ESX-1: RAM/ROM regions plus memory-mapped device handlers.

Addresses arrive as the CPU saw them. P0-P3 (below 0xE0000000) lose their top three bits (no MMU model);
P4 (0xE0000000 and up, where the SH7709 keeps its control registers) is looked up unchanged.
"""
import struct

PAGE = 12


class Region:
    def __init__(self, base, size, data=None, writable=True, name=""):
        self.base, self.size, self.writable, self.name = base, size, writable, name
        self.mem = bytearray(size) if data is None else bytearray(data).ljust(size, b"\xff")[:size]


class Bus:
    def __init__(self):
        self.pages = {}              # page number -> Region
        self.devices = []            # (lo, hi, device)
        self.dev_pages = {}          # page number -> [(lo, hi, device)]
        self.unmapped = {}           # (kind, phys) -> count, for the report
        self.trace = None            # optional callable(kind, addr, size, value)
        self.strict = False

    def add_region(self, region):
        for p in range(region.base >> PAGE, (region.base + region.size + (1 << PAGE) - 1) >> PAGE):
            self.pages[p] = region
        return region

    def add_device(self, lo, hi, dev, first=False):
        self.devices.append((lo, hi, dev))
        for p in range(lo >> PAGE, (hi - 1 >> PAGE) + 1):
            lst = self.dev_pages.setdefault(p, [])
            lst.insert(0, (lo, hi, dev)) if first else lst.append((lo, hi, dev))

    @staticmethod
    def phys(a):
        return a if a >= 0xE0000000 else a & 0x1FFFFFFF

    def _dev(self, p):
        for lo, hi, dev in self.dev_pages.get(p >> PAGE, ()):
            if lo <= p < hi:
                return dev
        return None

    # ------------------------------------------------------------------ reads
    def read8(self, a):
        p = a if a >= 0xE0000000 else a & 0x1FFFFFFF
        r = self.pages.get(p >> PAGE)
        if r is not None:
            o = p - r.base
            if 0 <= o < r.size:
                return r.mem[o]
        return self._mmio("r", p, 1, 0)

    def read16(self, a):
        p = a if a >= 0xE0000000 else a & 0x1FFFFFFF
        r = self.pages.get(p >> PAGE)
        if r is not None:
            o = p - r.base
            if 0 <= o <= r.size - 2:
                m = r.mem
                return m[o] << 8 | m[o + 1]
        return self._mmio("r", p, 2, 0)

    def read32(self, a):
        p = a if a >= 0xE0000000 else a & 0x1FFFFFFF
        r = self.pages.get(p >> PAGE)
        if r is not None:
            o = p - r.base
            if 0 <= o <= r.size - 4:
                m = r.mem
                return m[o] << 24 | m[o + 1] << 16 | m[o + 2] << 8 | m[o + 3]
        return self._mmio("r", p, 4, 0)

    # ------------------------------------------------------------------ writes
    def write8(self, a, v):
        p = a if a >= 0xE0000000 else a & 0x1FFFFFFF
        r = self.pages.get(p >> PAGE)
        if r is not None and r.writable:
            o = p - r.base
            if 0 <= o < r.size:
                r.mem[o] = v & 0xFF
                return
        if r is not None and r.write_hook is not None and 0 <= p - r.base < r.size:
            r.write_hook(p - r.base, v & 0xFF)
            return
        self._mmio("w", p, 1, v & 0xFF)

    def write16(self, a, v):
        p = a if a >= 0xE0000000 else a & 0x1FFFFFFF
        r = self.pages.get(p >> PAGE)
        if r is not None and r.writable:
            o = p - r.base
            if 0 <= o <= r.size - 2:
                r.mem[o] = v >> 8 & 0xFF
                r.mem[o + 1] = v & 0xFF
                return
        if r is not None and r.write_hook is not None and 0 <= p - r.base < r.size - 1:
            r.write_hook(p - r.base, v >> 8 & 0xFF)
            r.write_hook(p - r.base + 1, v & 0xFF)
            return
        self._mmio("w", p, 2, v & 0xFFFF)

    def write32(self, a, v):
        p = a if a >= 0xE0000000 else a & 0x1FFFFFFF
        r = self.pages.get(p >> PAGE)
        if r is not None and r.writable:
            o = p - r.base
            if 0 <= o <= r.size - 4:
                m = r.mem
                m[o] = v >> 24 & 0xFF
                m[o + 1] = v >> 16 & 0xFF
                m[o + 2] = v >> 8 & 0xFF
                m[o + 3] = v & 0xFF
                return
        if r is not None and r.write_hook is not None and 0 <= p - r.base < r.size - 3:
            for i in range(4):
                r.write_hook(p - r.base + i, v >> (24 - 8 * i) & 0xFF)
            return
        self._mmio("w", p, 4, v & 0xFFFFFFFF)

    def _mmio(self, kind, p, size, value):
        dev = self._dev(p)
        if self.trace:
            self.trace(kind, p, size, value)
        if dev is not None:
            if kind == "r":
                return dev.read(p, size)
            dev.write(p, size, value)
            return None
        r = self.pages.get(p >> PAGE)
        if r is not None and kind == "w" and not r.writable:
            key = ("rom-write", p)
        else:
            key = (kind, p)
        self.unmapped[key] = self.unmapped.get(key, 0) + 1
        if self.strict:
            raise MemoryError(f"unmapped {kind}{size * 8} at 0x{p:08x}")
        return 0

    # convenience for tools
    def load(self, addr, data):
        for i, b in enumerate(data):
            self.write8(addr + i, b)

    def peek(self, addr, n):
        return bytes(self.read8(addr + i) for i in range(n))
