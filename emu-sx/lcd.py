# SPDX-License-Identifier: GPL-2.0-only
"""HD44780-compatible character LCD on the ESX-1 as the firmware drives it.

Wiring found in the boot code: E = port E (0x04000128) bit 2, data D7..D4 = SC port (0x04000136) bits 3..0 (4-bit
interface), RS = SC bit 5, RW = SC bit 6. Writes latch on the falling edge of E; reads present the nibble while E is high.
"""

PE, SC = 0x04000128, 0x04000136


class HD44780:
    def __init__(self, ports, cols=40, rows=2):
        self.ports = ports
        self.cols, self.rows = cols, rows
        self.ddram = bytearray(b" " * 80)
        self.cgram = bytearray(64)
        self.addr = 0
        self.in_cgram = False
        self.bits4 = False
        self.phase = 0            # which nibble of a 4-bit transfer comes next
        self.hi = 0
        self.e = 0
        self.inc = 1
        self.shift = 0
        self.display_on = False
        self.read_byte = 0
        self.log = []             # every command / data byte, for tests
        self.busy_polls = 0
        ports.writes.append(self.on_write)
        ports.inputs[SC] = self.read_sc

    # ----- bus
    def _ctl(self):
        sc = self.ports.v.get(SC, 0)
        return sc & 0x20 != 0, sc & 0x40 != 0, sc & 0x0F      # rs, rw, nibble

    def on_write(self, a, size, val):
        if a != PE:
            return
        e = (val >> 2) & 1
        old, self.e = self.e, e
        rs, rw, nib = self._ctl()
        if e and not old and rw:
            self._read_rising(rs)
        elif old and not e and not rw:
            self._write_falling(rs, nib)
        elif old and not e and rw:
            self._read_falling(rs)

    def read_sc(self):
        rs, rw, _ = self._ctl()
        if self.e and rw:
            base = self.ports.v.get(SC, 0) & 0xF0
            return base | self.out_nibble
        return None

    # ----- writes
    def _write_falling(self, rs, nib):
        if not self.bits4:
            byte = nib << 4
            if not rs and byte == 0x20:
                self.bits4 = True
                self.phase = 0
                self.log.append(("cmd", 0x20, "4bit"))
            elif not rs:
                self._exec(byte, "8bit")
            return
        if self.phase == 0:
            self.hi = nib
            self.phase = 1
        else:
            self.phase = 0
            self._xfer(rs, self.hi << 4 | nib)

    def _xfer(self, rs, byte):
        (self._data if rs else self._exec)(byte)

    def _exec(self, c, note=""):
        self.log.append(("cmd", c, note))
        if c == 0x01:
            self.ddram[:] = b" " * 80
            self.addr, self.in_cgram = 0, False
        elif c & 0xFE == 0x02:
            self.addr, self.in_cgram = 0, False
        elif c & 0xFC == 0x04:
            self.inc = 1 if c & 2 else -1
            self.shift = c & 1
        elif c & 0xF8 == 0x08:
            self.display_on = bool(c & 4)
        elif c & 0xE0 == 0x20:
            pass
        elif c & 0xC0 == 0x40:
            self.in_cgram, self.addr = True, c & 0x3F
        elif c & 0x80:
            self.in_cgram, self.addr = False, c & 0x7F

    def _data(self, d):
        self.log.append(("data", d, ""))
        if self.in_cgram:
            self.cgram[self.addr & 0x3F] = d
            self.addr = (self.addr + self.inc) & 0x3F
        else:
            i = self._index(self.addr)
            if i is not None:
                self.ddram[i] = d
            self.addr = (self.addr + self.inc) & 0x7F

    @staticmethod
    def _index(addr):
        if addr < 0x28:
            return addr
        if 0x40 <= addr < 0x68:
            return 40 + addr - 0x40
        return None

    # ----- reads: the busy flag is never set, the emulator does not model the LCD's own timing
    def _read_rising(self, rs):
        if self.phase == 0:
            if rs:
                i = None if self.in_cgram else self._index(self.addr)
                self.read_byte = self.cgram[self.addr & 0x3F] if self.in_cgram else (self.ddram[i] if i is not None else 0)
            else:
                self.read_byte = self.addr & 0x7F
            self.out_nibble = self.read_byte >> 4
        else:
            self.out_nibble = self.read_byte & 15

    def _read_falling(self, rs):
        if self.phase == 0:
            self.phase = 1
        else:
            self.phase = 0
            if rs:
                self.addr = (self.addr + self.inc) & 0x7F

    out_nibble = 0

    def text(self):
        return [self.ddram[:40].decode("latin-1"), self.ddram[40:80].decode("latin-1")]
