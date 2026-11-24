# SPDX-License-Identifier: GPL-2.0-only
"""NAND flash chips (SmartMedia style, 512+16 byte pages) behind the 0x14000000 window, steered by port E.

Port E (0x04000128) as the firmware drives it: bit6 = NAND window active, bit4 = CLE, bit5 = ALE,
bit1 = /CE of chip index 1, bit3 = /CE of chip index 0 (active low). Ready/busy is read from port L, never busy here.
"""

PAGE, SPARE, PAGES_PER_BLOCK = 512, 16, 32
PE = 0x04000128


class Chip:
    def __init__(self, maker, device, size_mb, image=None):
        self.maker, self.device = maker, device
        self.pages = size_mb * 1024 * 1024 // PAGE
        self.data = bytearray(b"\xff" * (self.pages * (PAGE + SPARE)))
        if image:
            self.data[:len(image)] = image
        self.cmd = 0xFF
        self.addr = []
        self.col = 0
        self.row = 0
        self.buf = b""
        self.pos = 0
        self.prog = None
        self.status = 0xC0          # ready, not write protected
        self.addr_cycles = 3 if size_mb <= 32 else 4
        self.log = []

    # ----- bus cycles
    def command(self, c):
        self.log.append(("cmd", c))
        if c in (0x00, 0x01, 0x50):
            self.cmd = c
            self.addr = []
            self.base = {0x00: 0, 0x01: 256, 0x50: PAGE}[c]
        elif c == 0x90:
            self.cmd = c
            self.addr = []
            self.buf, self.pos = bytes([self.maker, self.device]), 0
        elif c == 0xFF:
            self.cmd = 0xFF
            self.status = 0xC0
        elif c == 0x70:
            self.cmd = 0x70
            self.buf, self.pos = bytes([self.status]), 0
        elif c == 0x80:
            self.cmd = 0x80
            self.addr = []
            self.prog = bytearray()
        elif c == 0x10:
            self._program()
        elif c == 0x60:
            self.cmd = 0x60
            self.addr = []
        elif c == 0xD0:
            self._erase()
        else:
            self.cmd = c

    def address(self, a):
        self.addr.append(a)
        if self.cmd in (0x00, 0x01, 0x50, 0x80):
            if len(self.addr) == 1:
                self.col = self.base + a if self.cmd != 0x80 else a
            elif len(self.addr) == 1 + self.addr_cycles - 1:
                self.row = sum(v << (8 * i) for i, v in enumerate(self.addr[1:]))
                if self.cmd != 0x80:
                    self._load()
        elif self.cmd == 0x60:
            if len(self.addr) == self.addr_cycles - 1:
                self.row = sum(v << (8 * i) for i, v in enumerate(self.addr))
        elif self.cmd == 0x90:
            pass

    def read_data(self):
        if self.cmd in (0x90, 0x70):
            if self.pos < len(self.buf):
                v = self.buf[self.pos]
                self.pos += 1
                return v
            return self.buf[-1] if self.buf else 0xFF
        if self.cmd in (0x00, 0x01, 0x50):
            if self.pos < len(self.buf):
                v = self.buf[self.pos]
                self.pos += 1
                return v
            return 0xFF
        return 0xFF

    def write_data(self, v):
        if self.cmd == 0x80 and self.prog is not None:
            self.prog.append(v)

    # ----- operations
    def _load(self):
        start = (self.row % self.pages) * (PAGE + SPARE)
        page = self.data[start:start + PAGE + SPARE]
        self.buf, self.pos = bytes(page[self.col:]), 0

    def _program(self):
        if self.prog is None:
            return
        start = (self.row % self.pages) * (PAGE + SPARE) + self.col
        for i, b in enumerate(self.prog):
            if start + i < len(self.data):
                self.data[start + i] &= b          # NAND programming can only clear bits
        self.prog = None
        self.status = 0xC0

    def _erase(self):
        block = (self.row % self.pages) // PAGES_PER_BLOCK
        s = block * PAGES_PER_BLOCK * (PAGE + SPARE)
        self.data[s:s + PAGES_PER_BLOCK * (PAGE + SPARE)] = b"\xff" * (PAGES_PER_BLOCK * (PAGE + SPARE))
        self.status = 0xC0


class NandBus:
    """Device at 0x14000000: routes byte cycles to the chip whose /CE is low."""
    def __init__(self, ports, chips):
        self.ports = ports
        self.chips = chips            # index -> Chip or None
        ports.inputs[0x0400013A - 0x4 if False else 0x04000134] = self._pl

    def _pl(self):
        return self.ports.v.get(0x04000134, 0) & ~0x0C     # ready on both

    def _selected(self):
        pe = self.ports.v.get(PE, 0)
        if not pe & 0x40:
            return None, pe
        if not pe & 0x08:
            return self.chips.get(0), pe
        if not pe & 0x02:
            return self.chips.get(1), pe
        return None, pe

    def read(self, a, size):
        chip, pe = self._selected()
        if chip is None:
            return 0xFF
        return chip.read_data()

    def write(self, a, size, v):
        chip, pe = self._selected()
        if chip is None:
            return
        if pe & 0x10:
            chip.command(v & 0xFF)
        elif pe & 0x20:
            chip.address(v & 0xFF)
        else:
            chip.write_data(v & 0xFF)
