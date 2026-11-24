# SPDX-License-Identifier: GPL-2.0-only
"""Hitachi SH-3 (SH7709) CPU core, big-endian, no FPU, no MMU/cache model.

Interpreter with one pre-built handler per 16-bit opcode (built lazily). Memory is reached through the
`bus` object (read8/16/32, write8/16/32 with already-translated physical addresses; see machine.py).
Delay slots, register banks, exceptions and interrupts follow the SH7708/7709 manual.
"""

M32 = 0xFFFFFFFF
T, S, IMASK, Q, M = 1, 2, 0xF0, 0x100, 0x200
BL, RB, MD = 1 << 28, 1 << 29, 1 << 30
SR_MASK = 0x700003F3

EV_RESET_POWER = 0x000
EV_ILLEGAL = 0x180
EV_SLOT_ILLEGAL = 0x1A0
EV_TRAPA = 0x160
EV_ADDR_ERR_R = 0x0E0
EV_ADDR_ERR_W = 0x100


class Halt(Exception):
    pass


def s8(x):
    return x - 256 if x & 0x80 else x


def s16(x):
    return x - 65536 if x & 0x8000 else x


def s32(x):
    return x - (1 << 32) if x & 0x80000000 else x


class SH3:
    def __init__(self, bus):
        self.bus = bus
        self.r = [0] * 16
        self.bank = [0] * 8          # the register bank that R0-R7 do not currently name
        self.pc = 0xA0000000
        self.pr = self.gbr = self.vbr = self.ssr = self.spc = 0
        self.mach = self.macl = 0
        self.sr = MD | RB | BL | IMASK
        self.sleeping = False
        self.cycles = 0              # executed instructions
        self.in_slot = False
        self.irq = None              # callable() -> (level, intevt) or None, polled between instructions
        self.exp = {"tra": 0, "expevt": 0, "intevt": 0}
        self.table = [None] * 65536
        self.trace_hook = None
        self.illegal_log = []

    # ------------------------------------------------------------------ SR / banks
    def set_sr(self, v):
        v &= SR_MASK
        if (v ^ self.sr) & RB:
            self.r[:8], self.bank[:] = self.bank[:], self.r[:8]
        self.sr = v

    def reset(self):
        self.r = [0] * 16
        self.bank = [0] * 8
        self.sr = MD | RB | BL | IMASK
        # RB=1 at reset: R0-R7 name bank 1, which is what `bank` holds when RB is clear; both zero here.
        self.vbr = 0
        self.pc = 0xA0000000
        self.sleeping = False
        self.exp["expevt"] = 0

    # ------------------------------------------------------------------ exceptions
    def exception(self, offset, expevt=None, intevt=None, pc=None, vector_base=None):
        self.spc = self.pc if pc is None else pc
        self.ssr = self.sr
        if expevt is not None:
            self.exp["expevt"] = expevt
        if intevt is not None:
            self.exp["intevt"] = intevt
        self.set_sr(self.sr | MD | RB | BL)
        self.pc = (self.vbr + offset) & M32
        self.sleeping = False

    def check_irq(self):
        if self.sr & BL or self.irq is None:
            return
        got = self.irq(self.sr & IMASK)
        if got:
            level, evt = got
            self.exception(0x600, intevt=evt)

    # ------------------------------------------------------------------ run
    def step(self):
        """Execute one instruction (with its delay slot when it branches)."""
        bus = self.bus
        pc = self.pc
        op = bus.read16(pc)
        h = self.table[op]
        if h is None:
            h = self.table[op] = self.decode(op)
        self.cycles += 1
        self.pc = (pc + 2) & M32
        h(self, pc)

    def run(self, n, stop_pc=None):
        """Run up to n instructions (stops early at `stop_pc`); returns the number executed."""
        done = 0
        table = self.table
        read16 = self.bus.read16
        while done < n:
            if self.sleeping:
                return done
            pc = self.pc
            if pc == stop_pc and done:
                break
            op = read16(pc)
            h = table[op]
            if h is None:
                h = table[op] = self.decode(op)
            self.pc = (pc + 2) & M32
            h(self, pc)
            done += 1
            if self.irq is not None and not (self.sr & BL):
                got = self.irq(self.sr & IMASK)
                if got:
                    self.exception(0x600, intevt=got[1])
        self.cycles += done
        return done

    def slot(self, at):
        """Run the delay slot instruction at `at`."""
        op = self.bus.read16(at)
        h = self.table[op]
        if h is None:
            h = self.table[op] = self.decode(op)
        self.pc = (at + 2) & M32
        self.in_slot = True
        h(self, at)
        self.in_slot = False

    # ------------------------------------------------------------------ decode
    def illegal(self, op):
        def f(c, pc):
            c.illegal_log.append((pc, op))
            c.exception(EV_SLOT_ILLEGAL if c.in_slot else EV_ILLEGAL, expevt=EV_SLOT_ILLEGAL if c.in_slot else EV_ILLEGAL, pc=pc)
        return f

    def decode(self, op):
        n = (op >> 8) & 15
        m = (op >> 4) & 15
        d = op & 15
        hi = op >> 12
        fn = getattr(self, f"_op{hi:X}", None)
        h = fn(op, n, m, d) if fn else None
        return h or self.illegal(op)

    # --- 0xxx
    def _op0(self, op, n, m, d):
        bus = self.bus
        if d == 2:
            if m == 0:
                return lambda c, pc: c.r.__setitem__(n, c.sr)
            if m == 1:
                return lambda c, pc: c.r.__setitem__(n, c.gbr)
            if m == 2:
                return lambda c, pc: c.r.__setitem__(n, c.vbr)
            if m == 3:
                return lambda c, pc: c.r.__setitem__(n, c.ssr)
            if m == 4:
                return lambda c, pc: c.r.__setitem__(n, c.spc)
            if m & 8:
                b = m & 7
                def f(c, pc):
                    c.r[n] = c.bank[b]
                return f
        if d == 3:
            if m == 0:
                def bsrf(c, pc):
                    c.pr = c.pc + 2
                    t = (c.pc + 2 + c.r[n]) & M32
                    c.slot(c.pc)
                    c.pc = t
                return bsrf
            if m == 2:
                def braf(c, pc):
                    t = (c.pc + 2 + c.r[n]) & M32
                    c.slot(c.pc)
                    c.pc = t
                return braf
            if m == 8:
                return lambda c, pc: None  # pref
        if d == 4:
            return lambda c, pc: bus.write8((c.r[0] + c.r[n]) & M32, c.r[m] & 0xFF)
        if d == 5:
            return lambda c, pc: bus.write16((c.r[0] + c.r[n]) & M32, c.r[m] & 0xFFFF)
        if d == 6:
            return lambda c, pc: bus.write32((c.r[0] + c.r[n]) & M32, c.r[m])
        if d == 7:
            def mull(c, pc):
                c.macl = (c.r[n] * c.r[m]) & M32
            return mull
        if d == 8:
            return {0x08: self._f_clrt, 0x18: self._f_sett, 0x28: self._f_clrmac, 0x38: self._f_ldtlb,
                    0x48: self._f_clrs, 0x58: self._f_sets}.get(op & 0xFF)
        if d == 9:
            if m == 0:
                return lambda c, pc: None
            if m == 1:
                def div0u(c, pc):
                    c.sr &= ~(M | Q | T)
                return div0u
            if m == 2:
                def movt(c, pc):
                    c.r[n] = c.sr & 1
                return movt
        if d == 10:
            if m == 0:
                return lambda c, pc: c.r.__setitem__(n, c.mach)
            if m == 1:
                return lambda c, pc: c.r.__setitem__(n, c.macl)
            if m == 2:
                return lambda c, pc: c.r.__setitem__(n, c.pr)
        if d == 11:
            if op == 0x000B:
                def rts(c, pc):
                    t = c.pr
                    c.slot(c.pc)
                    c.pc = t
                return rts
            if op == 0x001B:
                def sleep(c, pc):
                    c.sleeping = True
                return sleep
            if op == 0x002B:
                def rte(c, pc):
                    t = c.spc
                    ssr = c.ssr
                    c.slot(c.pc)
                    c.set_sr(ssr)
                    c.pc = t
                return rte
        if d == 12:
            return lambda c, pc: c.r.__setitem__(n, s8(bus.read8((c.r[0] + c.r[m]) & M32)) & M32)
        if d == 13:
            return lambda c, pc: c.r.__setitem__(n, s16(bus.read16((c.r[0] + c.r[m]) & M32)) & M32)
        if d == 14:
            return lambda c, pc: c.r.__setitem__(n, bus.read32((c.r[0] + c.r[m]) & M32))
        if d == 15:
            def macl(c, pc):
                a = s32(bus.read32(c.r[n]))
                c.r[n] = (c.r[n] + 4) & M32
                b = s32(bus.read32(c.r[m]))
                c.r[m] = (c.r[m] + 4) & M32
                acc = (c.mach << 32 | c.macl)
                acc = acc - (1 << 64) if acc >> 63 else acc
                acc += a * b
                if c.sr & S:
                    acc = max(-(1 << 47), min((1 << 47) - 1, acc))
                acc &= (1 << 64) - 1
                c.mach, c.macl = acc >> 32, acc & M32
            return macl
        return None

    @staticmethod
    def _f_clrt(c, pc):
        c.sr &= ~T

    @staticmethod
    def _f_sett(c, pc):
        c.sr |= T

    @staticmethod
    def _f_clrmac(c, pc):
        c.mach = c.macl = 0

    @staticmethod
    def _f_ldtlb(c, pc):
        pass

    @staticmethod
    def _f_clrs(c, pc):
        c.sr &= ~S

    @staticmethod
    def _f_sets(c, pc):
        c.sr |= S

    # --- 1xxx
    def _op1(self, op, n, m, d):
        bus = self.bus
        return lambda c, pc: bus.write32((c.r[n] + d * 4) & M32, c.r[m])

    # --- 2xxx
    def _op2(self, op, n, m, d):
        bus = self.bus
        if d == 0:
            return lambda c, pc: bus.write8(c.r[n], c.r[m] & 0xFF)
        if d == 1:
            return lambda c, pc: bus.write16(c.r[n], c.r[m] & 0xFFFF)
        if d == 2:
            return lambda c, pc: bus.write32(c.r[n], c.r[m])
        if d == 4:
            def f(c, pc):
                a = (c.r[n] - 1) & M32
                bus.write8(a, c.r[m] & 0xFF)
                c.r[n] = a
            return f
        if d == 5:
            def f(c, pc):
                a = (c.r[n] - 2) & M32
                bus.write16(a, c.r[m] & 0xFFFF)
                c.r[n] = a
            return f
        if d == 6:
            def f(c, pc):
                a = (c.r[n] - 4) & M32
                bus.write32(a, c.r[m])
                c.r[n] = a
            return f
        if d == 7:
            def div0s(c, pc):
                q = c.r[n] >> 31
                mm = c.r[m] >> 31
                c.sr = (c.sr & ~(Q | M | T)) | (Q if q else 0) | (M if mm else 0) | (T if q != mm else 0)
            return div0s
        if d == 8:
            def tst(c, pc):
                c.sr = (c.sr & ~T) | (T if c.r[n] & c.r[m] == 0 else 0)
            return tst
        if d == 9:
            def f(c, pc):
                c.r[n] &= c.r[m]
            return f
        if d == 10:
            def f(c, pc):
                c.r[n] ^= c.r[m]
            return f
        if d == 11:
            def f(c, pc):
                c.r[n] |= c.r[m]
            return f
        if d == 12:
            def cmpstr(c, pc):
                x = c.r[n] ^ c.r[m]
                hit = (x & 0xFF000000 == 0) or (x & 0xFF0000 == 0) or (x & 0xFF00 == 0) or (x & 0xFF == 0)
                c.sr = (c.sr & ~T) | (T if hit else 0)
            return cmpstr
        if d == 13:
            def xtrct(c, pc):
                c.r[n] = ((c.r[m] << 16) | (c.r[n] >> 16)) & M32
            return xtrct
        if d == 14:
            def mulu(c, pc):
                c.macl = ((c.r[n] & 0xFFFF) * (c.r[m] & 0xFFFF)) & M32
            return mulu
        if d == 15:
            def muls(c, pc):
                c.macl = (s16(c.r[n] & 0xFFFF) * s16(c.r[m] & 0xFFFF)) & M32
            return muls
        return None

    # --- 3xxx
    def _op3(self, op, n, m, d):
        def cmp(test):
            def f(c, pc):
                c.sr = (c.sr & ~T) | (T if test(c.r[n], c.r[m]) else 0)
            return f
        if d == 0:
            return cmp(lambda a, b: a == b)
        if d == 2:
            return cmp(lambda a, b: a >= b)
        if d == 3:
            return cmp(lambda a, b: s32(a) >= s32(b))
        if d == 4:
            return self._div1(n, m)
        if d == 5:
            def dmulu(c, pc):
                p = c.r[n] * c.r[m]
                c.mach, c.macl = p >> 32, p & M32
            return dmulu
        if d == 6:
            return cmp(lambda a, b: a > b)
        if d == 7:
            return cmp(lambda a, b: s32(a) > s32(b))
        if d == 8:
            def f(c, pc):
                c.r[n] = (c.r[n] - c.r[m]) & M32
            return f
        if d == 10:
            def subc(c, pc):
                t = c.sr & 1
                x = c.r[n] - c.r[m] - t
                c.r[n] = x & M32
                c.sr = (c.sr & ~T) | (T if x < 0 else 0)
            return subc
        if d == 11:
            def subv(c, pc):
                a, b = s32(c.r[n]), s32(c.r[m])
                x = a - b
                c.r[n] = x & M32
                c.sr = (c.sr & ~T) | (T if not -(1 << 31) <= x < (1 << 31) else 0)
            return subv
        if d == 12:
            def f(c, pc):
                c.r[n] = (c.r[n] + c.r[m]) & M32
            return f
        if d == 13:
            def dmuls(c, pc):
                p = (s32(c.r[n]) * s32(c.r[m])) & ((1 << 64) - 1)
                c.mach, c.macl = p >> 32, p & M32
            return dmuls
        if d == 14:
            def addc(c, pc):
                x = c.r[n] + c.r[m] + (c.sr & 1)
                c.r[n] = x & M32
                c.sr = (c.sr & ~T) | (T if x >> 32 else 0)
            return addc
        if d == 15:
            def addv(c, pc):
                a, b = s32(c.r[n]), s32(c.r[m])
                x = a + b
                c.r[n] = x & M32
                c.sr = (c.sr & ~T) | (T if not -(1 << 31) <= x < (1 << 31) else 0)
            return addv
        return None

    def _div1(self, n, m):
        def div1(c, pc):
            sr = c.sr
            old_q = 1 if sr & Q else 0
            mm = 1 if sr & M else 0
            q = (c.r[n] >> 31) & 1
            rn = ((c.r[n] << 1) | (sr & 1)) & M32
            tmp0 = rn
            rm = c.r[m]
            if old_q == mm:
                rn = (rn - rm) & M32
                tmp1 = 1 if rn > tmp0 else 0
                q = (tmp1 if q == 0 else 1 - tmp1) if old_q == 0 else (1 - tmp1 if q == 0 else tmp1)
            else:
                rn = (rn + rm) & M32
                tmp1 = 1 if rn < tmp0 else 0
                q = (1 - tmp1 if q == 0 else tmp1) if old_q == 0 else (tmp1 if q == 0 else 1 - tmp1)
            c.r[n] = rn
            c.sr = (sr & ~(Q | T)) | (Q if q else 0) | (T if q == mm else 0)
        return div1

    # --- 4xxx
    def _op4(self, op, n, m, d):
        bus = self.bus
        lo = op & 0xFF
        if d == 12:
            def shad(c, pc):
                s = c.r[m]
                x = s32(c.r[n])
                if not s & 0x80000000:
                    c.r[n] = (x << (s & 31)) & M32
                elif s & 31:
                    c.r[n] = (x >> (32 - (s & 31))) & M32
                else:
                    c.r[n] = M32 if x < 0 else 0
            return shad
        if d == 13:
            def shld(c, pc):
                s = c.r[m]
                x = c.r[n]
                if not s & 0x80000000:
                    c.r[n] = (x << (s & 31)) & M32
                elif s & 31:
                    c.r[n] = x >> (32 - (s & 31))
                else:
                    c.r[n] = 0
            return shld
        if d == 15:
            def macw(c, pc):
                a = s16(bus.read16(c.r[n]))
                c.r[n] = (c.r[n] + 2) & M32
                b = s16(bus.read16(c.r[m]))
                c.r[m] = (c.r[m] + 2) & M32
                p = a * b
                if c.sr & S:
                    x = s32(c.macl) + p
                    if x > 0x7FFFFFFF:
                        c.macl, c.mach = 0x7FFFFFFF, c.mach | 1
                    elif x < -0x80000000:
                        c.macl, c.mach = 0x80000000, c.mach | 1
                    else:
                        c.macl = x & M32
                else:
                    acc = c.mach << 32 | c.macl
                    acc = (acc + p) & ((1 << 64) - 1)
                    c.mach, c.macl = acc >> 32, acc & M32
            return macw
        if d == 3 and m & 8:
            b = m & 7
            def f(c, pc):
                a = (c.r[n] - 4) & M32
                bus.write32(a, c.bank[b])
                c.r[n] = a
            return f
        if d == 7 and m & 8:
            b = m & 7
            def f(c, pc):
                c.bank[b] = bus.read32(c.r[n])
                c.r[n] = (c.r[n] + 4) & M32
            return f
        if d == 14 and m & 8:
            b = m & 7
            def f(c, pc):
                c.bank[b] = c.r[n]
            return f
        # control register tables
        regs_s = {0: "mach", 1: "macl", 2: "pr"}
        regs_c = {0: "sr", 1: "gbr", 2: "vbr", 3: "ssr", 4: "spc"}
        if d == 2 and m in regs_s:
            name = regs_s[m]
            def f(c, pc):
                a = (c.r[n] - 4) & M32
                bus.write32(a, getattr(c, name))
                c.r[n] = a
            return f
        if d == 3 and m in regs_c:
            name = regs_c[m]
            def f(c, pc):
                a = (c.r[n] - 4) & M32
                bus.write32(a, getattr(c, name))
                c.r[n] = a
            return f
        if d == 6 and m in regs_s:
            name = regs_s[m]
            def f(c, pc):
                setattr(c, name, bus.read32(c.r[n]))
                c.r[n] = (c.r[n] + 4) & M32
            return f
        if d == 7 and m in regs_c:
            name = regs_c[m]
            if name == "sr":
                def f(c, pc):
                    v = bus.read32(c.r[n])
                    c.r[n] = (c.r[n] + 4) & M32
                    c.set_sr(v)
            else:
                def f(c, pc):
                    setattr(c, name, bus.read32(c.r[n]))
                    c.r[n] = (c.r[n] + 4) & M32
            return f
        if d == 10 and m in regs_s:
            name = regs_s[m]
            return lambda c, pc: setattr(c, name, c.r[n])
        if d == 14 and m in regs_c:
            name = regs_c[m]
            if name == "sr":
                return lambda c, pc: c.set_sr(c.r[n])
            return lambda c, pc: setattr(c, name, c.r[n])
        shifts = {
            0x00: lambda c, v: (v << 1 & M32, v >> 31), 0x01: lambda c, v: (v >> 1, v & 1),
            0x04: lambda c, v: ((v << 1 | v >> 31) & M32, v >> 31), 0x05: lambda c, v: ((v >> 1 | (v & 1) << 31), v & 1),
            0x08: lambda c, v: ((v << 2) & M32, None), 0x09: lambda c, v: (v >> 2, None),
            0x18: lambda c, v: ((v << 8) & M32, None), 0x19: lambda c, v: (v >> 8, None),
            0x20: lambda c, v: (v << 1 & M32, v >> 31), 0x21: lambda c, v: ((v >> 1) | (v & 0x80000000), v & 1),
            0x24: lambda c, v: ((v << 1 | (c.sr & 1)) & M32, v >> 31), 0x25: lambda c, v: ((v >> 1) | (c.sr & 1) << 31, v & 1),
            0x28: lambda c, v: ((v << 16) & M32, None), 0x29: lambda c, v: (v >> 16, None),
        }
        if lo in shifts:
            fn = shifts[lo]
            def f(c, pc):
                v, t = fn(c, c.r[n])
                c.r[n] = v
                if t is not None:
                    c.sr = (c.sr & ~T) | t
            return f
        if lo == 0x0B:
            def jsr(c, pc):
                c.pr = c.pc + 2
                t = c.r[n]
                c.slot(c.pc)
                c.pc = t
            return jsr
        if lo == 0x2B:
            def jmp(c, pc):
                t = c.r[n]
                c.slot(c.pc)
                c.pc = t
            return jmp
        if lo == 0x10:
            def dt(c, pc):
                c.r[n] = (c.r[n] - 1) & M32
                c.sr = (c.sr & ~T) | (T if c.r[n] == 0 else 0)
            return dt
        if lo == 0x11:
            def f(c, pc):
                c.sr = (c.sr & ~T) | (T if not c.r[n] & 0x80000000 else 0)
            return f
        if lo == 0x15:
            def f(c, pc):
                c.sr = (c.sr & ~T) | (T if 0 < c.r[n] < 0x80000000 else 0)
            return f
        if lo == 0x1B:
            def tas(c, pc):
                v = bus.read8(c.r[n])
                c.sr = (c.sr & ~T) | (T if v == 0 else 0)
                bus.write8(c.r[n], v | 0x80)
            return tas
        return None

    # --- 5xxx
    def _op5(self, op, n, m, d):
        bus = self.bus
        return lambda c, pc: c.r.__setitem__(n, bus.read32((c.r[m] + d * 4) & M32))

    # --- 6xxx
    def _op6(self, op, n, m, d):
        bus = self.bus
        if d == 0:
            return lambda c, pc: c.r.__setitem__(n, s8(bus.read8(c.r[m])) & M32)
        if d == 1:
            return lambda c, pc: c.r.__setitem__(n, s16(bus.read16(c.r[m])) & M32)
        if d == 2:
            return lambda c, pc: c.r.__setitem__(n, bus.read32(c.r[m]))
        if d == 3:
            return lambda c, pc: c.r.__setitem__(n, c.r[m])
        if d == 4:
            def f(c, pc):
                a = c.r[m]
                v = s8(bus.read8(a)) & M32
                if n != m:
                    c.r[m] = (a + 1) & M32
                c.r[n] = v
            return f
        if d == 5:
            def f(c, pc):
                a = c.r[m]
                v = s16(bus.read16(a)) & M32
                if n != m:
                    c.r[m] = (a + 2) & M32
                c.r[n] = v
            return f
        if d == 6:
            def f(c, pc):
                a = c.r[m]
                v = bus.read32(a)
                if n != m:
                    c.r[m] = (a + 4) & M32
                c.r[n] = v
            return f
        if d == 7:
            return lambda c, pc: c.r.__setitem__(n, ~c.r[m] & M32)
        if d == 8:
            return lambda c, pc: c.r.__setitem__(n, (c.r[m] & 0xFFFF0000) | (c.r[m] << 8 & 0xFF00) | (c.r[m] >> 8 & 0xFF))
        if d == 9:
            return lambda c, pc: c.r.__setitem__(n, ((c.r[m] << 16) | (c.r[m] >> 16)) & M32)
        if d == 10:
            def negc(c, pc):
                x = 0 - c.r[m] - (c.sr & 1)
                c.r[n] = x & M32
                c.sr = (c.sr & ~T) | (T if x < 0 else 0)
            return negc
        if d == 11:
            return lambda c, pc: c.r.__setitem__(n, -c.r[m] & M32)
        if d == 12:
            return lambda c, pc: c.r.__setitem__(n, c.r[m] & 0xFF)
        if d == 13:
            return lambda c, pc: c.r.__setitem__(n, c.r[m] & 0xFFFF)
        if d == 14:
            return lambda c, pc: c.r.__setitem__(n, s8(c.r[m] & 0xFF) & M32)
        if d == 15:
            return lambda c, pc: c.r.__setitem__(n, s16(c.r[m] & 0xFFFF) & M32)
        return None

    # --- 7xxx
    def _op7(self, op, n, m, d):
        i = s8(op & 0xFF)
        def f(c, pc):
            c.r[n] = (c.r[n] + i) & M32
        return f

    # --- 8xxx
    def _op8(self, op, n, m, d):
        bus = self.bus
        sub = n
        if sub == 0:
            return lambda c, pc: bus.write8((c.r[m] + d) & M32, c.r[0] & 0xFF)
        if sub == 1:
            return lambda c, pc: bus.write16((c.r[m] + d * 2) & M32, c.r[0] & 0xFFFF)
        if sub == 4:
            return lambda c, pc: c.r.__setitem__(0, s8(bus.read8((c.r[m] + d) & M32)) & M32)
        if sub == 5:
            return lambda c, pc: c.r.__setitem__(0, s16(bus.read16((c.r[m] + d * 2) & M32)) & M32)
        if sub == 8:
            i = s8(op & 0xFF) & M32
            def f(c, pc):
                c.sr = (c.sr & ~T) | (T if c.r[0] == i else 0)
            return f
        disp = s8(op & 0xFF) * 2 + 4
        if sub == 9:
            def bt(c, pc):
                if c.sr & 1:
                    c.pc = (pc + disp) & M32
            return bt
        if sub == 11:
            def bf(c, pc):
                if not c.sr & 1:
                    c.pc = (pc + disp) & M32
            return bf
        if sub == 13:
            return self._cond_slot(True, disp)
        if sub == 15:
            return self._cond_slot(False, disp)
        return None

    def _cond_slot(self, on_true, disp):
        def f(c, pc):
            if bool(c.sr & 1) == on_true:
                t = (pc + disp) & M32
                c.slot(c.pc)
                c.pc = t
        return f

    # --- 9xxx
    def _op9(self, op, n, m, d):
        bus = self.bus
        disp = (op & 0xFF) * 2 + 4
        return lambda c, pc: c.r.__setitem__(n, s16(bus.read16((pc + disp) & M32)) & M32)

    # --- Axxx / Bxxx
    def _opA(self, op, n, m, d):
        disp = op & 0xFFF
        disp = (disp - 0x1000 if disp & 0x800 else disp) * 2 + 4
        def bra(c, pc):
            t = (pc + disp) & M32
            c.slot(c.pc)
            c.pc = t
        return bra

    def _opB(self, op, n, m, d):
        disp = op & 0xFFF
        disp = (disp - 0x1000 if disp & 0x800 else disp) * 2 + 4
        def bsr(c, pc):
            c.pr = (pc + 4) & M32
            t = (pc + disp) & M32
            c.slot(c.pc)
            c.pc = t
        return bsr

    # --- Cxxx
    def _opC(self, op, n, m, d):
        bus = self.bus
        i = op & 0xFF
        if n == 0:
            return lambda c, pc: bus.write8((c.gbr + i) & M32, c.r[0] & 0xFF)
        if n == 1:
            return lambda c, pc: bus.write16((c.gbr + i * 2) & M32, c.r[0] & 0xFFFF)
        if n == 2:
            return lambda c, pc: bus.write32((c.gbr + i * 4) & M32, c.r[0])
        if n == 3:
            def trapa(c, pc):
                c.exp["tra"] = i << 2
                c.exception(0x100, expevt=0x160, pc=c.pc)
            return trapa
        if n == 4:
            return lambda c, pc: c.r.__setitem__(0, s8(bus.read8((c.gbr + i) & M32)) & M32)
        if n == 5:
            return lambda c, pc: c.r.__setitem__(0, s16(bus.read16((c.gbr + i * 2) & M32)) & M32)
        if n == 6:
            return lambda c, pc: c.r.__setitem__(0, bus.read32((c.gbr + i * 4) & M32))
        if n == 7:
            return lambda c, pc: c.r.__setitem__(0, ((pc & ~3) + 4 + i * 4) & M32)
        if n == 8:
            def tst(c, pc):
                c.sr = (c.sr & ~T) | (T if c.r[0] & i == 0 else 0)
            return tst
        if n == 9:
            def f(c, pc):
                c.r[0] &= i
            return f
        if n == 10:
            def f(c, pc):
                c.r[0] ^= i
            return f
        if n == 11:
            def f(c, pc):
                c.r[0] |= i
            return f
        if n == 12:
            def f(c, pc):
                v = bus.read8((c.gbr + c.r[0]) & M32)
                c.sr = (c.sr & ~T) | (T if v & i == 0 else 0)
            return f
        if n in (13, 14, 15):
            fn = {13: lambda v: v & i, 14: lambda v: v ^ i, 15: lambda v: v | i}[n]
            def f(c, pc):
                a = (c.gbr + c.r[0]) & M32
                bus.write8(a, fn(bus.read8(a)))
            return f
        return None

    # --- Dxxx / Exxx
    def _opD(self, op, n, m, d):
        bus = self.bus
        disp = (op & 0xFF) * 4
        return lambda c, pc: c.r.__setitem__(n, bus.read32((((pc + 4) & ~3) + disp) & M32))

    def _opE(self, op, n, m, d):
        v = s8(op & 0xFF) & M32
        return lambda c, pc: c.r.__setitem__(n, v)
