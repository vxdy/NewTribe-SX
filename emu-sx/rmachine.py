# SPDX-License-Identifier: GPL-2.0-only
"""Machine on top of the Rust core (core/target/release/sh3core.dll). Same surface as machine.Machine where the tools use it."""
import ctypes as C
from pathlib import Path

from lcd import HD44780
from keys import KeyMatrix

HERE = Path(__file__).resolve().parent
_LIBS = [HERE / "core/target/release/sh3core.dll", HERE / "core/target/release/libsh3core.so",
         HERE / "core/target/release/libsh3core.dylib"]
RD = C.CFUNCTYPE(C.c_int64, C.c_uint32, C.c_uint32)
WR = C.CFUNCTYPE(None, C.c_uint32, C.c_uint32, C.c_uint32)
PORT0 = 0x04000000


def load_lib():
    for p in _LIBS:
        if p.exists():
            lib = C.CDLL(str(p))
            break
    else:
        raise FileNotFoundError("sh3core nicht gebaut: cd core && cargo build --release")
    P = C.c_void_p
    lib.emu_new.restype, lib.emu_new.argtypes = P, [C.c_char_p, C.c_size_t, C.c_size_t]
    lib.emu_free.argtypes = [P]
    lib.emu_run.restype, lib.emu_run.argtypes = C.c_uint64, [P, C.c_uint64]
    lib.emu_set_stop_pc.argtypes = [P, C.c_uint32]
    lib.emu_set_callbacks.argtypes = [P, RD, WR]
    lib.emu_hook.argtypes = [P, C.c_uint32, C.c_uint32, C.c_uint32, C.c_uint32]
    lib.emu_force_read.argtypes = [P, C.c_uint32, C.c_uint32, C.c_uint32]
    lib.emu_set_timescale.argtypes = [P, C.c_double]
    lib.emu_nand_set.argtypes = [P, C.c_uint32, C.c_char_p, C.c_size_t, C.c_uint32, C.c_uint32]
    lib.emu_nand_ptr.restype, lib.emu_nand_ptr.argtypes = C.c_void_p, [P, C.c_uint32]
    lib.emu_nand_len.restype, lib.emu_nand_len.argtypes = C.c_size_t, [P, C.c_uint32]
    lib.emu_nand_cmds.restype, lib.emu_nand_cmds.argtypes = C.c_uint64, [P, C.c_uint32]
    for n in ("emu_sdram_ptr", "emu_flash_ptr", "emu_ports_ptr"):
        getattr(lib, n).restype, getattr(lib, n).argtypes = C.c_void_p, [P]
    lib.emu_sdram_len.restype, lib.emu_sdram_len.argtypes = C.c_size_t, [P]
    lib.emu_get.restype, lib.emu_get.argtypes = C.c_uint64, [P, C.c_uint32]
    lib.emu_set.argtypes = [P, C.c_uint32, C.c_uint64]
    lib.emu_read32.restype, lib.emu_read32.argtypes = C.c_uint32, [P, C.c_uint32]
    lib.emu_unmapped.restype, lib.emu_unmapped.argtypes = C.c_uint32, [P, C.c_uint32, C.POINTER(C.c_uint32), C.POINTER(C.c_uint32), C.POINTER(C.c_uint64)]
    lib.emu_reg_count.restype, lib.emu_reg_count.argtypes = C.c_uint64, [P, C.c_uint32, C.c_uint32]
    lib.emu_clear_counts.argtypes = [P]
    lib.emu_raise_irq.argtypes = [P, C.c_uint32]
    lib.emu_set_adc_in.argtypes = [P, C.c_uint32, C.c_uint32, C.c_uint32]
    lib.emu_reg_write_pc.restype, lib.emu_reg_write_pc.argtypes = C.c_uint32, [P, C.c_uint32]
    lib.emu_port_log.argtypes = [P, C.c_uint32]
    lib.emu_port_log_get.restype, lib.emu_port_log_get.argtypes = C.c_uint32, [P, C.c_uint32] + [C.POINTER(C.c_uint32)] * 3
    lib.emu_reg_read_pc.restype, lib.emu_reg_read_pc.argtypes = C.c_uint32, [P, C.c_uint32]
    lib.emu_set_threaded.argtypes = [P, C.c_uint32]
    lib.emu_snapshot.restype, lib.emu_snapshot.argtypes = P, [P]
    lib.emu_restore.argtypes = [P, P]
    lib.emu_nand_rows.restype, lib.emu_nand_rows.argtypes = C.c_size_t, [P, C.c_uint32, C.c_uint32, C.POINTER(C.c_uint32), C.c_size_t]
    lib.emu_irq_period.argtypes = [P, C.c_uint32, C.c_double]
    lib.emu_set_adc.argtypes = [P, C.c_uint32, C.c_uint32]
    lib.emu_scif_tx.restype, lib.emu_scif_tx.argtypes = C.c_size_t, [P, C.c_char_p, C.c_size_t]
    lib.emu_watch.argtypes = [P, C.c_uint32, C.c_uint32]
    lib.emu_watch_get.restype, lib.emu_watch_get.argtypes = C.c_uint32, [P, C.c_uint32] + [C.POINTER(C.c_uint32)] * 4
    lib.emu_unmapped_pc.restype, lib.emu_unmapped_pc.argtypes = C.c_uint32, [P, C.c_uint32]
    lib.emu_dsp_word.restype, lib.emu_dsp_word.argtypes = C.c_uint64, [P, C.c_uint32]
    lib.emu_dsp_config.argtypes = [P, C.c_double, C.c_uint64, C.c_uint32]
    lib.emu_dsp_unimpl.restype, lib.emu_dsp_unimpl.argtypes = C.c_uint32, [P, C.c_uint32, C.POINTER(C.c_uint32), C.POINTER(C.c_uint32), C.POINTER(C.c_uint64), C.POINTER(C.c_uint32)]
    lib.emu_dsp_trace_get.restype, lib.emu_dsp_trace_get.argtypes = C.c_uint32, [P, C.c_uint32, C.POINTER(C.c_uint32), C.POINTER(C.c_uint32)]
    lib.emu_dsp_audio.restype, lib.emu_dsp_audio.argtypes = C.c_size_t, [P, C.c_uint32, C.c_void_p, C.c_size_t]
    lib.emu_dsp_wrpc.restype, lib.emu_dsp_wrpc.argtypes = C.c_uint32, [P, C.c_uint32, C.POINTER(C.c_uint32), C.POINTER(C.c_uint32), C.POINTER(C.c_uint64)]
    lib.emu_dsp_watch.argtypes = [P, C.c_uint32, C.c_uint32]
    lib.emu_dsp_watch_get.restype, lib.emu_dsp_watch_get.argtypes = C.c_uint32, [P, C.c_uint32] + [C.POINTER(C.c_uint32)] * 4
    lib.emu_dsp_rwatch_get.restype, lib.emu_dsp_rwatch_get.argtypes = C.c_uint32, [P, C.c_uint32] + [C.POINTER(C.c_uint32)] * 4
    lib.emu_dsp_tone.argtypes = [P, C.c_float]
    lib.emu_dsp_int2div.argtypes = [P, C.c_uint32]
    lib.emu_dsp_int0.argtypes = [P, C.c_uint64]
    lib.emu_dsp_mem.restype, lib.emu_dsp_mem.argtypes = C.c_uint32, [P, C.c_uint32, C.c_uint32]
    lib.emu_write8.argtypes = [P, C.c_uint32, C.c_uint32]
    lib.emu_write16.argtypes = [P, C.c_uint32, C.c_uint32]
    return lib


_lib = None


class _PortV:
    """dict-like view of the native port registers (what lcd.py and keys.py read as `ports.v`)."""
    def __init__(self, m):
        self.m = m

    def get(self, addr, default=0):
        return self.m._ports[addr - PORT0]

    def __getitem__(self, addr):
        return self.m._ports[addr - PORT0]


class _Ports:
    def __init__(self, m):
        self.v = _PortV(m)
        self.inputs = {}
        self.writes = []


class _Bus:
    def __init__(self, m):
        self.m = m

    def read8(self, a):
        s = a & 0x1FFFFFFF
        o = s - 0x0C000000
        if 0 <= o < self.m._sdram_len:
            return self.m._sdram[o]
        if s < 0x400000:
            return self.m._flash[s]
        return 0

    def read16(self, a):
        return self.read8(a) << 8 | self.read8(a + 1)

    def read32(self, a):
        return _lib.emu_read32(self.m.h, a)

    def write8(self, a, v):
        _lib.emu_write8(self.m.h, a, v)

    def write16(self, a, v):
        _lib.emu_write16(self.m.h, a, v)

    def peek(self, a, n):
        return bytes(self.read8(a + i) for i in range(n))


class _Cpu:
    def __init__(self, m):
        self.m = m

    pc = property(lambda s: _lib.emu_get(s.m.h, 16))
    pr = property(lambda s: _lib.emu_get(s.m.h, 17))
    sr = property(lambda s: _lib.emu_get(s.m.h, 18))
    sleeping = property(lambda s: bool(_lib.emu_get(s.m.h, 25)))

    @property
    def r(self):
        return [_lib.emu_get(self.m.h, i) for i in range(16)]

    @property
    def illegal_log(self):
        n = _lib.emu_get(self.m.h, 27)
        return [(_lib.emu_get(self.m.h, 28), _lib.emu_get(self.m.h, 29))] * min(n, 1)

    def run(self, n, stop_pc=None):
        _lib.emu_set_stop_pc(self.m.h, 0xFFFFFFFF if stop_pc is None else stop_pc)
        r = _lib.emu_run(self.m.h, n)
        _lib.emu_set_stop_pc(self.m.h, 0xFFFFFFFF)
        return r


class _Tmu:
    def __init__(self, m):
        self.m = m
        self._scale = 1.0

    @property
    def underflows(self):
        return [_lib.emu_get(self.m.h, 34 + i) for i in range(3)]

    @property
    def scale(self):
        return self._scale

    @scale.setter
    def scale(self, v):
        self._scale = float(v)
        _lib.emu_set_timescale(self.m.h, self._scale)


class _Nor:
    def __init__(self, m):
        self.m = m

    erases = property(lambda s: _lib.emu_get(s.m.h, 31))
    programmed = property(lambda s: _lib.emu_get(s.m.h, 32))
    bad_programs = property(lambda s: _lib.emu_get(s.m.h, 33))


class DspPort:
    """Host interface of the DSP (uPD77213) at 0x08000000: records everything the CPU writes (the microcode download and
    later parameter words) as a running CRC32 plus counters, so that a changed BDS shows up as a changed DSP stream.
    There is no instruction level DSP core behind it yet (no audio)."""
    def __init__(self):
        self.words = 0
        self.nonzero = 0
        self.crc = 0
        self.head = []

    def on_write(self, addr, size, val):
        if not (0x08000000 <= addr < 0x08000004):
            return
        import zlib
        self.words += 1
        if val:
            self.nonzero += 1
            self.crc = zlib.crc32(((addr & 3) | (size << 4) | (val << 8)).to_bytes(6, "little"), self.crc)
            if len(self.head) < 16:
                self.head.append(val)

    def summary(self):
        return {"writes": self.words, "nonzero": self.nonzero, "crc": f"{self.crc:08x}"}



class _Dsp:
    """View on the native DSP core."""
    def __init__(self, m):
        self.m = m

    def word(self, i):
        return _lib.emu_dsp_word(self.m.h, i)

    pc = property(lambda s: s.word(0))
    cycles = property(lambda s: s.word(1))
    boot = property(lambda s: s.word(2))
    icount = property(lambda s: s.word(3))

    def config(self, ratio=1.0, aso_period=2177, trace=False):
        _lib.emu_dsp_config(self.m.h, ratio, aso_period, 1 if trace else 0)

    def wrpcs(self):
        out, i = [], 0
        a, b, c = C.c_uint32(), C.c_uint32(), C.c_uint64()
        while _lib.emu_dsp_wrpc(self.m.h, i, C.byref(a), C.byref(b), C.byref(c)):
            out.append((a.value, b.value, c.value)); i += 1
        return out

    def watch(self, lo, hi):
        _lib.emu_dsp_watch(self.m.h, lo, hi)

    def watch_log(self):
        out, i = [], 0
        a = [C.c_uint32() for _ in range(4)]
        while _lib.emu_dsp_watch_get(self.m.h, i, *[C.byref(x) for x in a]):
            out.append(tuple(x.value for x in a)); i += 1
        return out

    def rwatch_log(self):
        out, i = [], 0
        a = [C.c_uint32() for _ in range(4)]
        while _lib.emu_dsp_rwatch_get(self.m.h, i, *[C.byref(x) for x in a]):
            out.append(tuple(x.value for x in a)); i += 1
        return out

    def tone(self, amp):
        _lib.emu_dsp_tone(self.m.h, amp)

    def int2div(self, n):
        _lib.emu_dsp_int2div(self.m.h, n)

    def int0(self, every):
        _lib.emu_dsp_int0(self.m.h, every)

    def unimpl(self):
        out, i = [], 0
        a, k, c, pc = C.c_uint32(), C.c_uint32(), C.c_uint64(), C.c_uint32()
        while _lib.emu_dsp_unimpl(self.m.h, i, C.byref(a), C.byref(k), C.byref(c), C.byref(pc)):
            out.append((a.value, chr(k.value), c.value, pc.value)); i += 1
        return out

    def trace(self):
        out, i = [], 0
        pc, w = C.c_uint32(), C.c_uint32()
        while _lib.emu_dsp_trace_get(self.m.h, i, C.byref(pc), C.byref(w)):
            out.append((pc.value, w.value)); i += 1
        return out

    def audio(self, n=1 << 16, which=0):
        buf = (C.c_int16 * n)()
        got = _lib.emu_dsp_audio(self.m.h, which, buf, n)
        return list(buf[:got])

    def mem(self, kind, addr):
        return _lib.emu_dsp_mem(self.m.h, {"x": 0, "y": 1, "i": 2, "e": 3, "p": 4, "icr": 5, "dpr": 6, "hlog": 7, "ev": 8}[kind], addr)

    def summary(self):
        return {"pc": self.pc, "boot": self.boot, "instr": self.icount, "cycles": self.cycles, "frames": self.word(32), "stalls": self.word(8), "acks": [self.word(20 + j) for j in range(4)]}



class RMachine:
    DELAY_FN = 0x0C009B50

    def __init__(self, flash_image, sdram_mb=32, card_present=False):
        global _lib
        _lib = _lib or load_lib()
        self.h = _lib.emu_new(bytes(flash_image), len(flash_image), sdram_mb)
        self._sdram_len = _lib.emu_sdram_len(self.h)
        self._sdram = (C.c_ubyte * self._sdram_len).from_address(_lib.emu_sdram_ptr(self.h))
        self._flash = (C.c_ubyte * 0x400000).from_address(_lib.emu_flash_ptr(self.h))
        self._ports = (C.c_ubyte * 0x200).from_address(_lib.emu_ports_ptr(self.h))
        self.ports = _Ports(self)
        self.bus = _Bus(self)
        self.cpu = _Cpu(self)
        self.tmu = _Tmu(self)
        self.nor = _Nor(self)
        self.lcd = HD44780(self.ports)
        self.keys = KeyMatrix(self.ports, self.bus, 0x0C00A170)
        self.card_present = card_present
        self.devs = []                      # (lo, hi, fn(addr, size) -> value) for external devices on the read hook
        self.fast_delays = False
        self._patched = False
        self._rd = RD(self._on_read)
        self._wr = WR(self._on_write)
        _lib.emu_set_callbacks(self.h, self._rd, self._wr)
        pe, sc, pg = 0x04000128, 0x04000136, 0x0400012C
        _lib.emu_hook(self.h, pe, pe + 1, 0, 1)
        _lib.emu_hook(self.h, sc, sc + 1, 1, 1)
        _lib.emu_hook(self.h, pg, pg + 1, 1, 0)
        _lib.emu_force_read(self.h, 0x0400012A, 0xFF, 0x0C)        # NAND ready lines
        _lib.emu_force_read(self.h, 0x0400012E, 0x70, 0x00)        # PH4 = 0, encoder idle
        self.set_card_present(card_present)
        self._dsp_t0 = None
        # the DSP (uPD77213) is emulated natively in the core: host port at 0x08000000, see core/src/dsp.rs
        self.dsp = _Dsp(self)
        self.irq_period(3, 108_850)  # IRQ3 = one per 50-frame DSP block

    def _dsp_read(self, addr, size):
        """Status word of the DSP: ready (bit 6) a few milliseconds after the first poll, never an error (bit 2)."""
        if addr not in (0x08000002, 0x08000003):
            return 0
        ticks = self.tmu.underflows[0]
        if self._dsp_t0 is None:
            self._dsp_t0 = ticks
        val = 0x0040 if ticks - self._dsp_t0 >= 5 else 0x0000
        if addr == 0x08000002 and size == 2:
            return val
        return val >> 8 if addr == 0x08000002 else val & 0xFF

    def add_read_device(self, lo, hi, fn):
        self.devs.append((lo, hi, fn))
        _lib.emu_hook(self.h, lo, hi, 1, 0)

    def set_card_present(self, present):
        self.card_present = present
        _lib.emu_force_read(self.h, 0x04000134, 0x8C, 0x80 if present else 0x00)

    # ----- hooks
    def _on_read(self, addr, size):
        for lo, hi, fn in self.devs:
            if lo <= addr < hi:
                return fn(addr, size)
        f = self.ports.inputs.get(addr)
        if f is not None:
            r = f()
            if r is not None:
                return r
        return -1

    def _on_write(self, addr, size, val):
        for h in self.ports.writes:
            h(addr, size, val)

    # ----- chips
    def set_nand(self, idx, data, maker=0, dev=0):
        if data is None:
            _lib.emu_nand_set(self.h, idx, None, 0, 0, 0)
        else:
            _lib.emu_nand_set(self.h, idx, bytes(data), len(data), maker, dev)

    def nand_data(self, idx):
        return C.string_at(_lib.emu_nand_ptr(self.h, idx), _lib.emu_nand_len(self.h, idx))

    def nand_cmds(self, idx):
        return _lib.emu_nand_cmds(self.h, idx)

    def flash_bytes(self, n=0x80000):
        return bytes(self._flash[:n])

    def sdram_bytes(self, lo=0, n=None):
        n = self._sdram_len - lo if n is None else n
        return bytes(self._sdram[lo:lo + n])

    # ----- running
    def run(self, n):
        if self.fast_delays and not self._patched and self.bus.read16(self.DELAY_FN) == 0x7FFC:
            self.bus.write16(self.DELAY_FN, 0x000B)
            self.bus.write16(self.DELAY_FN + 2, 0x0009)
            self._patched = True
        return _lib.emu_run(self.h, n)

    def watch(self, lo, hi):
        _lib.emu_watch(self.h, lo & 0x1FFFFFFF, hi & 0x1FFFFFFF)

    def watch_log(self):
        out, i = [], 0
        a = [C.c_uint32() for _ in range(4)]
        while _lib.emu_watch_get(self.h, i, *[C.byref(x) for x in a]):
            out.append(tuple(x.value for x in a)); i += 1
        return out

    def midi_out(self):
        buf = C.create_string_buffer(4096)
        n = _lib.emu_scif_tx(self.h, buf, 4096)
        return buf.raw[:n]

    def set_adc(self, ch, value10):
        _lib.emu_set_adc(self.h, ch, value10)

    def irq_period(self, line, instrs):
        _lib.emu_irq_period(self.h, line, float(instrs))

    def nand_rows(self, idx, kind=0):
        out = []
        buf = (C.c_uint32 * 65536)()
        while True:
            n = _lib.emu_nand_rows(self.h, idx, kind, buf, 65536)
            out.extend(buf[:n])
            if n < 65536:
                return out

    def snapshot(self):
        lcd = {k: (bytearray(v) if isinstance(v, bytearray) else v) for k, v in self.lcd.__dict__.items() if k != "ports"}
        return (_lib.emu_snapshot(self.h), lcd, set(self.keys.pressed), self._dsp_t0)

    def restore(self, snap):
        h, lcd, pressed, t0 = snap
        _lib.emu_restore(self.h, h)
        for k, v in lcd.items():
            setattr(self.lcd, k, bytearray(v) if isinstance(v, bytearray) else v)
        self.keys.pressed = set(pressed)
        self._dsp_t0 = t0

    # VALUE encoder: Port H bits 6:5, Gray code. 0,2,3,1 is one click clockwise (value up), 0,1,3,2 one click counter-clockwise.
    ENC_UP = (0, 2, 3, 1)
    ENC_DOWN = (0, 1, 3, 2)

    def _ph56(self, v):
        _lib.emu_force_read(self.h, 0x0400012E, 0x70, (v << 5) & 0x60)

    def turn(self, clicks, step_instr=1_500_000):
        """Turn the VALUE encoder: clicks > 0 up, < 0 down."""
        seq = self.ENC_UP if clicks > 0 else self.ENC_DOWN
        for _ in range(abs(clicks)):
            for v in seq:
                self._ph56(v)
                self.run(step_instr)
        self._ph56(0)

    def set_adc_in(self, col, ch, value10):
        _lib.emu_set_adc_in(self.h, col, ch, value10)

    def raise_irq(self, line):
        _lib.emu_raise_irq(self.h, line)

    # ----- diagnostics
    def clear_counts(self):
        _lib.emu_clear_counts(self.h)

    def unmapped(self):
        out, i = [], 0
        a, k, c = C.c_uint32(), C.c_uint32(), C.c_uint64()
        while _lib.emu_unmapped(self.h, i, C.byref(a), C.byref(k), C.byref(c)):
            out.append((a.value, "rw"[k.value], c.value, _lib.emu_unmapped_pc(self.h, i)))
            i += 1
        return out

    def reg_read_pc(self, addr):
        i = addr - 0x04000000 if addr < 0x04000200 + 0x04000000 else 0x200 + addr - 0xFFFFFE00
        return _lib.emu_reg_read_pc(self.h, i)

    def reg_write_pc(self, addr):
        i = addr - 0x04000000 if addr < 0x04000200 + 0x04000000 else 0x200 + addr - 0xFFFFFE00
        return _lib.emu_reg_write_pc(self.h, i)

    def port_log(self, on=True):
        _lib.emu_port_log(self.h, 1 if on else 0)

    def port_log_get(self):
        out, i = [], 0
        a = [C.c_uint32() for _ in range(3)]
        while _lib.emu_port_log_get(self.h, i, *[C.byref(x) for x in a]):
            out.append(tuple(x.value for x in a)); i += 1
        return out

    def reg_counts(self):
        out = {}
        for w in (0, 1):
            for i in range(0x400):
                c = _lib.emu_reg_count(self.h, w, i)
                if c:
                    a = 0x04000000 + i if i < 0x200 else 0xFFFFFE00 + i - 0x200
                    out[(a, "rw"[w])] = c
        return out

    def threaded(self, on):
        _lib.emu_set_threaded(self.h, 1 if on else 0)

    def close(self):
        if self.h:
            _lib.emu_free(self.h)
            self.h = None
