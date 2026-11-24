# SPDX-License-Identifier: GPL-2.0-only
"""On-chip peripherals of the Hitachi SH7709 as far as the ESX-1 firmware uses them.

Everything that is not modelled stores what was written and reads it back, so initialisation code sees what it
set. Anything with behaviour (SCIF status, timers, interrupt controller) is a class below.
"""


class RegFile:
    """Plain read/write registers over an address range."""
    def __init__(self, lo, hi, name=""):
        self.lo, self.hi, self.name = lo, hi, name
        self.v = {}

    def read(self, a, size):
        out = 0
        for i in range(size):
            out = out << 8 | self.v.get(a + i, 0)
        return out

    def write(self, a, size, val):
        for i in range(size):
            self.v[a + size - 1 - i] = (val >> (8 * i)) & 0xFF


class SCIF(RegFile):
    """SCIF2 at 0x04000150: SCSMR, SCBRR, SCSCR, SCFTDR, SCSSR, SCFRDR, SCFCR, SCFDR. Always ready to send."""
    def __init__(self, base=0x04000150, name="scif"):
        super().__init__(base, base + 0x20, name)
        self.base = base
        self.tx = bytearray()
        self.rx = bytearray()

    def read(self, a, size):
        off = a - self.base
        if off == 0x08:                     # SCSSR: TEND|TDFE always, RDF/DR when bytes wait
            return 0x60 | (0x03 if self.rx else 0)
        if off == 0x0C:                     # SCFRDR
            return self.rx.pop(0) if self.rx else 0
        if off == 0x0E:                     # SCFDR: receive count in the low byte
            return min(len(self.rx), 16)
        return super().read(a, size)

    def write(self, a, size, val):
        off = a - self.base
        if off == 0x06:
            self.tx.append(val & 0xFF)
            return
        if off == 0x08:                     # status clears by writing 0
            return
        super().write(a, size, val)


class Ports(RegFile):
    """Port control (0x04000100) and data registers (0x04000120). Inputs come from `inputs[addr] -> int or None`."""
    def __init__(self):
        super().__init__(0x04000100, 0x04000140, "ports")
        self.inputs = {}
        self.writes = []     # hook list: callables (addr, size, value)

    def read(self, a, size):
        f = self.inputs.get(a)
        if f is not None:
            r = f()
            if r is not None:
                return r
        return super().read(a, size)

    def write(self, a, size, val):
        super().write(a, size, val)
        for h in self.writes:
            h(a, size, val)


class TMU:
    """Timer unit (0xFFFFFE90..): three 32-bit down counters. Time is counted in executed CPU instructions;
    one instruction is taken as one 96 MHz core cycle, the peripheral clock is 24 MHz (Pck/4 = 6 MHz by default).
    Interrupts: TUNI0/1/2 = INTEVT 0x400/0x420/0x440, levels from IPRA (bits 15..12, 11..8, 7..4)."""
    BASE = 0xFFFFFE90
    PRESCALE = {0: 4, 1: 16, 2: 64, 3: 256, 4: 1024}
    EVT = (0x400, 0x420, 0x440)
    IPRA = 0xFFFFFEE2

    def __init__(self, onchip):
        self.lo, self.hi = self.BASE, self.BASE + 0x2C
        self.onchip = onchip          # RegFile that holds IPRA
        self.tocr = 0
        self.tstr = 0
        self.tcor = [0xFFFFFFFF] * 3
        self.tcnt = [0xFFFFFFFF] * 3
        self.tcr = [0] * 3
        self.frac = [0.0] * 3
        self.underflows = [0, 0, 0]
        self.scale = 1.0              # time lapse: timers run this many times faster than the instruction count says

    def _ch(self, a):
        off = a - self.BASE
        if 4 <= off < 0x2C:
            ch, reg = divmod(off - 4, 0x0C)
            if ch < 3 and reg < 0x0C:
                return ch, reg
        return None, off

    def read(self, a, size):
        ch, reg = self._ch(a)
        if ch is None:
            return {0: self.tocr, 2: self.tstr}.get(reg, 0)
        if reg == 0:
            return self.tcor[ch]
        if reg == 4:
            return self.tcnt[ch]
        if reg == 8:
            return self.tcr[ch]
        return 0

    def write(self, a, size, v):
        ch, reg = self._ch(a)
        if ch is None:
            if reg == 0:
                self.tocr = v & 0xFF
            elif reg == 2:
                self.tstr = v & 0x07
            return
        if reg == 0:
            self.tcor[ch] = v & 0xFFFFFFFF
        elif reg == 4:
            self.tcnt[ch] = v & 0xFFFFFFFF
        elif reg == 8:
            unf = self.tcr[ch] & 0x100
            self.tcr[ch] = (v & 0xFFFF & ~0x100) | (unf & v)   # UNF can only be cleared by software

    def advance(self, instrs):
        for ch in range(3):
            if not self.tstr >> ch & 1:
                continue
            div = self.PRESCALE.get(self.tcr[ch] & 7)
            if div is None:
                continue
            self.frac[ch] += instrs * self.scale / 16.0 * 4 / div       # instructions -> Pck/4 ticks -> prescaled ticks
            n = int(self.frac[ch])
            if not n:
                continue
            self.frac[ch] -= n
            c = self.tcnt[ch]
            while n > c:
                n -= c + 1
                c = self.tcor[ch]
                self.tcr[ch] |= 0x100
                self.underflows[ch] += 1
                if c == 0 and n:
                    n = 0
            self.tcnt[ch] = c - n

    def next_event_instrs(self):
        """Instructions until the earliest enabled underflow, or None."""
        best = None
        for ch in range(3):
            if not self.tstr >> ch & 1:
                continue
            div = self.PRESCALE.get(self.tcr[ch] & 7)
            if div is None:
                continue
            ticks = self.tcnt[ch] + 1 - self.frac[ch]
            instrs = ticks * div * 16.0 / 4 / self.scale
            best = instrs if best is None else min(best, instrs)
        return best

    def pending(self, imask):
        """(level, intevt) of the highest-priority pending interrupt above imask, or None."""
        ipra = (self.onchip.read(self.IPRA, 2))
        best = None
        for ch in range(3):
            if self.tcr[ch] & 0x100 and self.tcr[ch] & 0x20:
                level = (ipra >> (12 - 4 * ch)) & 0xF
                if level > imask and (best is None or level > best[0]):
                    best = (level, self.EVT[ch])
        return best


class ExcRegs:
    """TRA 0xFFFFFFD0, EXPEVT 0xFFFFFFD4, INTEVT 0xFFFFFFD8 and INTEVT2 at 0xA4000000 (the SH7709 puts the event code of
    peripheral interrupts there; the firmware's interrupt handler at VBR+0x600 reads it)."""
    def __init__(self, cpu):
        self.cpu = cpu

    def read(self, a, size):
        e = self.cpu.exp
        if a == 0x04000000:
            return e["intevt"]
        return {0xFFFFFFD0: e["tra"], 0xFFFFFFD4: e["expevt"], 0xFFFFFFD8: e["intevt"]}.get(a & ~3, 0)

    def write(self, a, size, v):
        pass
