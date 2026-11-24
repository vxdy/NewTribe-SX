// SPDX-License-Identifier: GPL-2.0-only
//! Hitachi SH7709 (SH-3, big-endian) core of the ESX-1 emulator: CPU, SDRAM, boot flash (AMD NOR), two NAND chips,
//! timer unit and the event registers. Display, keys and everything else stay in Python and are reached through
//! hooks on a few port addresses (see `emu_hook`).

mod dsp;
use std::slice;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::collections::VecDeque as VDq;

/// Handshake between the SH thread and the DSP thread (lock step in quanta).
struct Link { go: AtomicU64, done: AtomicU64, cycles: AtomicU64, quit: AtomicBool }
struct ThrHandle(Option<std::thread::JoinHandle<()>>);
impl Clone for ThrHandle { fn clone(&self) -> Self { ThrHandle(None) } }
struct DspPtr(*mut dsp::Dsp);
unsafe impl Send for DspPtr {}

#[derive(Clone)]
enum HostMsg { Write { off: u32, size: u32, v: u32, pc: u32, pr: u32 }, Underflow }

const T: u32 = 1;
const S: u32 = 2;
const IMASK: u32 = 0xF0;
const Q: u32 = 0x100;
const M: u32 = 0x200;
const BL: u32 = 1 << 28;
const RB: u32 = 1 << 29;
const MD: u32 = 1 << 30;
const SR_MASK: u32 = 0x700003F3;

const SDRAM_BASE: u32 = 0x0C00_0000;
const FLASH_SIZE: usize = 0x40_0000;
const NOR_SIZE: usize = 0x8_0000;
const NAND_WIN: u32 = 0x1400_0000;
const PE: usize = 0x128;
const CHUNK: u64 = 256;
const XCHG_EVERY: u64 = 1; // chunks per SH<->DSP exchange

type RdCb = extern "C" fn(u32, u32) -> i64;
type WrCb = extern "C" fn(u32, u32, u32);

// ------------------------------------------------------------------------------------------------ NAND
const PAGE: usize = 512;
const SPARE: usize = 16;
const PPB: usize = 32;

#[derive(Default, Clone)]
struct Chip {
    present: bool,
    maker: u8,
    dev: u8,
    addr_cycles: usize,
    data: Vec<u8>,
    pages: usize,
    cmd: u8,
    addr: Vec<u8>,
    col: usize,
    row: usize,
    base: usize,
    rd: usize,
    rd_end: usize,
    small: Vec<u8>,
    small_pos: usize,
    prog: Vec<u8>,
    prog_on: bool,
    status: u8,
    cmds: u64,
    read_rows: Vec<u32>,
    write_rows: Vec<u32>,
}

impl Chip {
    fn command(&mut self, c: u8) {
        self.cmds += 1;
        match c {
            0x00 | 0x01 | 0x50 => {
                self.cmd = c;
                self.addr.clear();
                self.base = match c { 0x00 => 0, 0x01 => 256, _ => PAGE };
            }
            0x90 => {
                self.cmd = c;
                self.addr.clear();
                self.small = vec![self.maker, self.dev];
                self.small_pos = 0;
            }
            0xFF => { self.cmd = 0xFF; self.status = 0xC0; }
            0x70 => { self.cmd = 0x70; self.small = vec![self.status]; self.small_pos = 0; }
            0x80 => { self.cmd = 0x80; self.addr.clear(); self.prog.clear(); self.prog_on = true; }
            0x10 => self.program(),
            0x60 => { self.cmd = 0x60; self.addr.clear(); }
            0xD0 => self.erase(),
            _ => self.cmd = c,
        }
    }

    fn address(&mut self, a: u8) {
        self.addr.push(a);
        let n = self.addr.len();
        match self.cmd {
            0x00 | 0x01 | 0x50 | 0x80 => {
                if n == 1 {
                    self.col = if self.cmd == 0x80 { a as usize } else { self.base + a as usize };
                } else if n == self.addr_cycles {
                    self.row = self.addr[1..].iter().enumerate().map(|(i, v)| (*v as usize) << (8 * i)).sum();
                    if self.cmd != 0x80 { self.load(); }
                }
            }
            0x60 => {
                if n == self.addr_cycles - 1 {
                    self.row = self.addr.iter().enumerate().map(|(i, v)| (*v as usize) << (8 * i)).sum();
                }
            }
            _ => {}
        }
    }

    fn load(&mut self) {
        let start = (self.row % self.pages) * (PAGE + SPARE);
        self.rd = start + self.col;
        self.rd_end = start + PAGE + SPARE;
        if self.read_rows.len() < 400_000 { self.read_rows.push((self.row % self.pages) as u32); }
    }

    fn read(&mut self) -> u8 {
        match self.cmd {
            0x90 | 0x70 => {
                if self.small_pos < self.small.len() {
                    let v = self.small[self.small_pos];
                    self.small_pos += 1;
                    v
                } else { *self.small.last().unwrap_or(&0xFF) }
            }
            0x00 | 0x01 | 0x50 => {
                if self.rd < self.rd_end { let v = self.data[self.rd]; self.rd += 1; v } else { 0xFF }
            }
            _ => 0xFF,
        }
    }

    fn write(&mut self, v: u8) {
        if self.cmd == 0x80 && self.prog_on { self.prog.push(v); }
    }

    fn program(&mut self) {
        if !self.prog_on { return; }
        if self.write_rows.len() < 400_000 { self.write_rows.push((self.row % self.pages) as u32); }
        let start = (self.row % self.pages) * (PAGE + SPARE) + self.col;
        for (i, b) in self.prog.iter().enumerate() {
            if start + i < self.data.len() { self.data[start + i] &= *b; }
        }
        self.prog_on = false;
        self.status = 0xC0;
    }

    fn erase(&mut self) {
        let block = (self.row % self.pages) / PPB;
        let s = block * PPB * (PAGE + SPARE);
        let e = s + PPB * (PAGE + SPARE);
        for b in &mut self.data[s..e] { *b = 0xFF; }
        self.status = 0xC0;
    }
}

// ------------------------------------------------------------------------------------------------ NOR flash
#[derive(Default, Clone)]
struct Nor {
    unlock: u8,
    erase_setup: bool,
    pending: u8, // 0 none, 1 program, 2 bypass reset
    bypass: bool,
    autoselect: bool,
    saved: [u8; 2],
    erases: u32,
    programmed: u64,
    bad: u64,
}

const NOR_SECTORS: [(usize, usize); 11] = [
    (0x00000, 0x10000), (0x10000, 0x20000), (0x20000, 0x30000), (0x30000, 0x40000), (0x40000, 0x50000),
    (0x50000, 0x60000), (0x60000, 0x70000), (0x70000, 0x78000), (0x78000, 0x7A000), (0x7A000, 0x7C000),
    (0x7C000, 0x80000),
];

impl Nor {
    fn reset(&mut self, mem: &mut [u8]) {
        if self.autoselect {
            mem[0] = self.saved[0];
            mem[1] = self.saved[1];
            self.autoselect = false;
        }
        self.unlock = 0;
        self.erase_setup = false;
        self.pending = 0;
        self.bypass = false;
    }

    fn write(&mut self, mem: &mut [u8], off: usize, v: u8) {
        let off = off % NOR_SIZE;
        let a = off & 0x7FF;
        if v == 0xF0 && self.pending == 0 { self.reset(mem); return; }
        if self.pending == 1 {
            if (v & !mem[off]) != 0 { self.bad += 1; }
            mem[off] &= v;
            self.programmed += 1;
            self.pending = 0;
            return;
        }
        if self.pending == 2 { self.bypass = false; self.pending = 0; return; }
        if self.bypass && self.unlock == 0 {
            if v == 0xA0 { self.pending = 1; } else if v == 0x90 { self.pending = 2; }
            return;
        }
        let u = self.unlock;
        match u {
            0 | 3 => {
                if a == 0x555 && v == 0xAA { self.unlock = u + 1; } else { self.unlock = if self.erase_setup && u == 3 { 3 } else { 0 }; }
            }
            1 | 4 => {
                if a == 0x2AA && v == 0x55 { self.unlock = u + 1; } else { self.unlock = 0; self.erase_setup = false; }
            }
            _ => {
                self.unlock = 0;
                if u == 2 {
                    if a == 0x555 && v == 0xA0 { self.pending = 1; }
                    else if a == 0x555 && v == 0x80 { self.erase_setup = true; self.unlock = 3; }
                    else if a == 0x555 && v == 0x20 { self.bypass = true; }
                    else if a == 0x555 && v == 0x90 {
                        self.saved = [mem[0], mem[1]];
                        mem[0] = 0x04; mem[1] = 0xB5;
                        self.autoselect = true;
                    }
                } else {
                    self.erase_setup = false;
                    if a == 0x555 && v == 0x10 {
                        for b in &mut mem[..NOR_SIZE] { *b = 0xFF; }
                        self.erases += 1;
                    } else if v == 0x30 {
                        for (lo, hi) in NOR_SECTORS.iter() {
                            if off >= *lo && off < *hi { for b in &mut mem[*lo..*hi] { *b = 0xFF; } break; }
                        }
                        self.erases += 1;
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------------------------------------ TMU
#[derive(Clone)]
struct Tmu {
    tocr: u8,
    tstr: u8,
    tcor: [u32; 3],
    tcnt: [u32; 3],
    tcr: [u16; 3],
    frac: [f64; 3],
    under: [u64; 3],
    scale: f64,
}

impl Tmu {
    fn new() -> Self {
        Tmu { tocr: 0, tstr: 0, tcor: [u32::MAX; 3], tcnt: [u32::MAX; 3], tcr: [0; 3], frac: [0.0; 3], under: [0; 3], scale: 1.0 }
    }
    fn div(&self, ch: usize) -> Option<f64> {
        match self.tcr[ch] & 7 { 0 => Some(4.0), 1 => Some(16.0), 2 => Some(64.0), 3 => Some(256.0), 4 => Some(1024.0), _ => None }
    }
    fn locate(a: u32) -> (Option<usize>, u32) {
        let off = a.wrapping_sub(0xFFFF_FE90);
        if (4..0x2C).contains(&off) {
            let ch = ((off - 4) / 12) as usize;
            let reg = (off - 4) % 12;
            if ch < 3 { return (Some(ch), reg); }
        }
        (None, off)
    }
    fn read(&self, a: u32) -> u32 {
        match Tmu::locate(a) {
            (None, 0) => self.tocr as u32,
            (None, 2) => self.tstr as u32,
            (Some(c), 0) => self.tcor[c],
            (Some(c), 4) => self.tcnt[c],
            (Some(c), 8) => self.tcr[c] as u32,
            _ => 0,
        }
    }
    fn write(&mut self, a: u32, v: u32) {
        match Tmu::locate(a) {
            (None, 0) => self.tocr = v as u8,
            (None, 2) => self.tstr = (v & 7) as u8,
            (Some(c), 0) => self.tcor[c] = v,
            (Some(c), 4) => self.tcnt[c] = v,
            (Some(c), 8) => {
                let unf = self.tcr[c] & 0x100;
                self.tcr[c] = ((v as u16) & !0x100) | (unf & (v as u16));
            }
            _ => {}
        }
    }
    fn advance(&mut self, instrs: f64) {
        for ch in 0..3 {
            if self.tstr >> ch & 1 == 0 { continue; }
            let div = match self.div(ch) { Some(d) => d, None => continue };
            self.frac[ch] += instrs * self.scale / (4.0 * div);
            let n = self.frac[ch].floor();
            if n < 1.0 { continue; }
            self.frac[ch] -= n;
            let mut n = n as u64;
            let mut c = self.tcnt[ch] as u64;
            if n > c {
                n -= c + 1;
                self.tcr[ch] |= 0x100;
                self.under[ch] += 1;
                let p = self.tcor[ch] as u64 + 1;
                self.under[ch] += n / p;
                n %= p;
                c = self.tcor[ch] as u64;
            }
            self.tcnt[ch] = (c - n) as u32;
        }
    }
    fn next_event(&self) -> Option<f64> {
        let mut best: Option<f64> = None;
        for ch in 0..3 {
            if self.tstr >> ch & 1 == 0 { continue; }
            let div = match self.div(ch) { Some(d) => d, None => continue };
            let ticks = self.tcnt[ch] as f64 + 1.0 - self.frac[ch];
            let instrs = ticks * 4.0 * div / self.scale;
            best = Some(match best { Some(b) => b.min(instrs), None => instrs });
        }
        best
    }
}

// ------------------------------------------------------------------------------------------------ the machine
#[derive(Clone)]
pub struct Emu {
    r: [u32; 16],
    bank: [u32; 8],
    pc: u32,
    pr: u32,
    gbr: u32,
    vbr: u32,
    ssr: u32,
    spc: u32,
    mach: u32,
    macl: u32,
    sr: u32,
    sleeping: bool,
    in_slot: bool,
    cycles: u64,
    tra: u32,
    expevt: u32,
    intevt: u32,
    illegal: u32,
    illegal_pc: u32,
    illegal_op: u32,
    flash: Vec<u8>,
    sdram: Vec<u8>,
    ports: Vec<u8>,
    onchip: Vec<u8>,
    nor: Nor,
    chips: [Chip; 2],
    tmu: Tmu,
    hooks: Vec<(u32, u32, bool, bool)>,
    force: Vec<(u32, u8, u8)>,
    rd_cb: Option<RdCb>,
    wr_cb: Option<WrCb>,
    stop_pc: u32,
    unmapped: Vec<(u32, u8, u64)>,
    unm_pc: Vec<u32>,
    irq_lines: u32,
    adc_in: [[u16; 8]; 64],
    irq_period: [f64; 6],
    irq_acc: [f64; 6],
    scif_tx: Vec<u8>,
    watch: (u32, u32),
    watch_log: Vec<(u32, u32, u32, u32)>,
    reg_rd: Vec<u64>,
    reg_rd_pc: Vec<u32>,
    reg_wr_pc: Vec<u32>,
    port_log: Vec<(u32, u32, u32)>,
    port_log_on: bool,
    reg_wr: Vec<u64>,
    dsp: dsp::Dsp,
    dma_irq: u32,
    dma_done: u64,
    dsp_ratio: f64,
    sleep_instr: u64,
    dsp_acc: f64,
    // SH <-> DSP threading
    threaded: bool,
    link: Option<Arc<Link>>,
    dsp_thread: ThrHandle,
    seq: u64,
    inflight: bool,
    pend_dc: u64,
    chunk_n: u64,
    sh_in: Vec<HostMsg>,
    sh_in_writes: u32,
    sh_out: VDq<u16>,
    hst_snap: u16,
    hq_empty_snap: bool,
    cov: Vec<u8>,
    cov_on: bool,
    cov_lo: u32,
}

#[inline]
fn s8(x: u32) -> i32 { x as u8 as i8 as i32 }
#[inline]
fn s16(x: u32) -> i32 { x as u16 as i16 as i32 }

impl Emu {
    fn new(flash: &[u8], sdram_mb: usize) -> Emu {
        let mut f = vec![0xFFu8; FLASH_SIZE];
        let n = flash.len().min(FLASH_SIZE);
        f[..n].copy_from_slice(&flash[..n]);
        let mut e = Emu {
            r: [0; 16], bank: [0; 8], pc: 0xA000_0000, pr: 0, gbr: 0, vbr: 0, ssr: 0, spc: 0, mach: 0, macl: 0,
            sr: MD | RB | BL | IMASK, sleeping: false, in_slot: false, cycles: 0, tra: 0, expevt: 0, intevt: 0,
            illegal: 0, illegal_pc: 0, illegal_op: 0,
            flash: f, sdram: vec![0; sdram_mb << 20], ports: vec![0; 0x200], onchip: vec![0; 0x200],
            nor: Nor::default(), chips: [Chip::default(), Chip::default()], tmu: Tmu::new(),
            hooks: Vec::new(), force: Vec::new(), rd_cb: None, wr_cb: None, stop_pc: 0xFFFF_FFFF,
            unmapped: Vec::new(), unm_pc: Vec::new(), irq_lines: 0, adc_in: [[0x200; 8]; 64], irq_period: [0.0; 6], irq_acc: [0.0; 6], scif_tx: Vec::new(), watch: (0, 0), watch_log: Vec::new(), reg_rd: vec![0; 0x400], reg_rd_pc: vec![0; 0x400], reg_wr_pc: vec![0; 0x400], port_log: Vec::new(), port_log_on: false, reg_wr: vec![0; 0x400], dsp: dsp::Dsp::new(), dma_irq: 0, dma_done: 0, dsp_ratio: 1.0, sleep_instr: 0, dsp_acc: 0.0, threaded: false, link: None, dsp_thread: ThrHandle(None), seq: 0, inflight: false, pend_dc: 0, chunk_n: 0, sh_in: Vec::new(), sh_in_writes: 0, sh_out: VDq::new(), hst_snap: 0, hq_empty_snap: true, cov: Vec::new(), cov_on: false, cov_lo: 0,
        };
        e.nor.saved = [0xFF, 0xFF];
        e.adc_in[2][2] = 0x3FF;   // ribbon controller (mux col 2, ch 2): >~0x340 = not touched (all other pots rest at mid-scale)
        for ch in 0..4 { e.ports[0x80 + 2 * ch] = 0x80; }   // A/D data registers: mid-scale (knobs centred)
        e
    }

    // ---------------------------------------------------------------- bus
    #[inline]
    fn phys(a: u32) -> u32 { if a >= 0xE000_0000 { a } else { a & 0x1FFF_FFFF } }

    #[inline(always)]
    fn cov_mark(&mut self, p: u32, n: u32, f: u8) {
        let o = p.wrapping_sub(self.cov_lo) as usize;
        if o + (n as usize) <= self.cov.len() { for i in 0..n as usize { self.cov[o + i] |= f; } }
    }

    #[inline(always)]
    fn fetch(&mut self, a: u32) -> u32 {
        let p = Self::phys(a);
        if self.cov_on {
            let o = p.wrapping_sub(self.cov_lo) as usize;
            if o + 2 <= self.cov.len() { self.cov[o] |= 1; self.cov[o + 1] |= 2; }
        }
        self.read16_raw(a)
    }

    #[inline(always)]
    fn read8(&mut self, a: u32) -> u32 {
        let p = Self::phys(a);
        if self.cov_on { self.cov_mark(p, 1, 4); }
        let o = p.wrapping_sub(SDRAM_BASE) as usize;
        if o < self.sdram.len() { return self.sdram[o] as u32; }
        if (p as usize) < FLASH_SIZE { return self.flash[p as usize] as u32; }
        self.mmio_read(p, 1)
    }

    #[inline(always)]
    fn read16(&mut self, a: u32) -> u32 {
        if self.cov_on { let p = Self::phys(a); self.cov_mark(p, 2, 8); }
        self.read16_raw(a)
    }

    #[inline(always)]
    fn read16_raw(&mut self, a: u32) -> u32 {
        let p = Self::phys(a);
        let o = p.wrapping_sub(SDRAM_BASE) as usize;
        if o + 1 < self.sdram.len() { return (self.sdram[o] as u32) << 8 | self.sdram[o + 1] as u32; }
        let pi = p as usize;
        if pi + 1 < FLASH_SIZE { return (self.flash[pi] as u32) << 8 | self.flash[pi + 1] as u32; }
        self.mmio_read(p, 2)
    }

    #[inline(always)]
    fn read32(&mut self, a: u32) -> u32 {
        let p = Self::phys(a);
        if self.cov_on { self.cov_mark(p, 4, 16); }
        let o = p.wrapping_sub(SDRAM_BASE) as usize;
        if o + 3 < self.sdram.len() {
            let m = &self.sdram[o..o + 4];
            return u32::from_be_bytes([m[0], m[1], m[2], m[3]]);
        }
        let pi = p as usize;
        if pi + 3 < FLASH_SIZE {
            let m = &self.flash[pi..pi + 4];
            return u32::from_be_bytes([m[0], m[1], m[2], m[3]]);
        }
        self.mmio_read(p, 4)
    }

    #[inline]
    fn note_write(&mut self, p: u32, size: u32, v: u32) {
        if p >= self.watch.0 && p < self.watch.1 && self.watch_log.len() < 256 { let pc = self.pc; self.watch_log.push((pc, p, size, v)); }
    }

    #[inline(always)]
    fn write8(&mut self, a: u32, v: u32) {
        let p = Self::phys(a);
        if self.cov_on { self.cov_mark(p, 1, 32); }
        if self.watch.1 != 0 { self.note_write(p, 1, v); }
        let o = p.wrapping_sub(SDRAM_BASE) as usize;
        if o < self.sdram.len() { self.sdram[o] = v as u8; return; }
        self.mmio_write(p, 1, v & 0xFF);
    }

    #[inline(always)]
    fn write16(&mut self, a: u32, v: u32) {
        let p = Self::phys(a);
        if self.cov_on { self.cov_mark(p, 2, 32); }
        if self.watch.1 != 0 { self.note_write(p, 2, v); }
        let o = p.wrapping_sub(SDRAM_BASE) as usize;
        if o + 1 < self.sdram.len() { self.sdram[o] = (v >> 8) as u8; self.sdram[o + 1] = v as u8; return; }
        self.mmio_write(p, 2, v & 0xFFFF);
    }

    #[inline(always)]
    fn write32(&mut self, a: u32, v: u32) {
        let p = Self::phys(a);
        if self.cov_on { self.cov_mark(p, 4, 32); }
        if self.watch.1 != 0 { self.note_write(p, 4, v); }
        let o = p.wrapping_sub(SDRAM_BASE) as usize;
        if o + 3 < self.sdram.len() { self.sdram[o..o + 4].copy_from_slice(&v.to_be_bytes()); return; }
        self.mmio_write(p, 4, v);
    }

    fn nand_selected(&self) -> Option<usize> {
        let pe = self.ports[PE];
        if pe & 0x40 == 0 { return None; }
        if pe & 0x08 == 0 { return Some(0); }
        if pe & 0x02 == 0 { return Some(1); }
        None
    }

    fn note_unmapped(&mut self, p: u32, kind: u8) {
        if (0xF000_0000..0xF200_0000).contains(&p) { return; } // cache address/data arrays
        let pc = self.pc;
        for (i, u) in self.unmapped.iter_mut().enumerate() { if u.0 == p && u.1 == kind { u.2 += 1; self.unm_pc[i] = pc; return; } }
        if self.unmapped.len() < 256 { self.unmapped.push((p, kind, 1)); self.unm_pc.push(pc); }
    }

    fn reg_index(p: u32) -> Option<usize> {
        if p >= 0x0400_0000 && p < 0x0400_0200 { return Some((p - 0x0400_0000) as usize); }
        if p >= 0xFFFF_FE00 { return Some(0x200 + (p - 0xFFFF_FE00) as usize); }
        None
    }

    fn reg_array(&mut self, p: u32) -> Option<(&mut Vec<u8>, usize)> {
        if p >= 0x0400_0000 && p < 0x0400_0200 { return Some((&mut self.ports, (p - 0x0400_0000) as usize)); }
        if p >= 0xFFFF_FE00 { return Some((&mut self.onchip, (p - 0xFFFF_FE00) as usize)); }
        None
    }

    #[cold]
    #[inline(never)]
    fn mmio_read(&mut self, p: u32, size: u32) -> u32 {
        if (0x0800_0000..0x0800_0010).contains(&p) { return self.sh_host_read(p & 7, size); }
        if !self.hooks.is_empty() {
            if let Some(cb) = self.rd_cb {
                for h in &self.hooks {
                    if h.2 && p >= h.0 && p < h.1 {
                        let v = cb(p, size);
                        if v >= 0 { return v as u32; }
                        break;
                    }
                }
            }
        }
        if p == NAND_WIN {
            return match self.nand_selected() {
                Some(i) if self.chips[i].present => self.chips[i].read() as u32,
                _ => 0xFF,
            };
        }
        if p == 0x0400_0000 { return self.intevt; }
        if (0xFFFF_FFD0..0xFFFF_FFDC).contains(&p) {
            return match p & !3 { 0xFFFF_FFD0 => self.tra, 0xFFFF_FFD4 => self.expevt, _ => self.intevt };
        }
        if (0xFFFF_FE90..0xFFFF_FEBC).contains(&p) { return self.tmu.read(p); }
        if p == 0x0400_0158 { return 0x60; } // SCIF status: transmitter always empty
        let force: Vec<(u32, u8, u8)> = if size == 1 { self.force.iter().filter(|f| f.0 == p).cloned().collect() } else { Vec::new() };
        if let Some(ix) = Self::reg_index(p) { self.reg_rd[ix] += 1; self.reg_rd_pc[ix] = self.pc; }
        if let Some((arr, i)) = self.reg_array(p) {
            let n = size as usize;
            let mut v = 0u32;
            for k in 0..n { v = v << 8 | *arr.get(i + k).unwrap_or(&0) as u32; }
            for f in force { v = (v & !(f.1 as u32)) | (f.2 as u32 & f.1 as u32); }
            return v;
        }
        self.note_unmapped(p, 0);
        0
    }

    #[cold]
    #[inline(never)]
    fn mmio_write(&mut self, p: u32, size: u32, v: u32) {
        if (0x0800_0000..0x0800_0010).contains(&p) { self.sh_host_write(p & 7, size, v); return; }
        if (p as usize) < FLASH_SIZE {
            for k in 0..size {
                let b = (v >> (8 * (size - 1 - k))) as u8;
                let mut fl = std::mem::take(&mut self.flash);
                self.nor.write(&mut fl, p as usize + k as usize, b);
                self.flash = fl;
            }
            return;
        }
        if p == NAND_WIN {
            if let Some(i) = self.nand_selected() {
                let pe = self.ports[PE];
                let c = &mut self.chips[i];
                if c.present {
                    if pe & 0x10 != 0 { c.command(v as u8); } else if pe & 0x20 != 0 { c.address(v as u8); } else { c.write(v as u8); }
                }
            }
            return;
        }
        if (0xFFFF_FE90..0xFFFF_FEBC).contains(&p) { self.tmu.write(p, v); return; }
        if p == 0x0400_0156 { self.scif_tx.push(v as u8); }
        if p == 0x0400_0090 && v & 0x20 != 0 {                 // ADCSR: start conversion -> done at once, ADF set
            let ch = (v & 7) as usize;
            let pd = self.ports[0x126];
            // mux select = PDDR (0x0400_0126) bits 7/5: col = PD7<<1 | PD5 (firmware group g = PD7 | PD5<<1; low nibble of PD is the key-matrix column address)
            let col = ((((pd >> 7) & 1) as usize) << 1) | (((pd >> 5) & 1) as usize);
            let val = (self.adc_in[col][ch] as u32 & 0x3FF) << 6;
            if ch < 4 {
            self.ports[0x80 + 4 * ch] = (val >> 8) as u8;                // ADDRnH
            self.ports[0x82 + 4 * ch] = val as u8; }                       // ADDRnL (bits 7:6 = low two bits)
            self.ports[0x90] = ((v as u8) & !0x20) | 0x80;
            if self.port_log_on && self.port_log.len() < 400_000 { let pc = self.pc; self.port_log.push((pc, p, v)); }
            return;
        }
        if let Some(ix) = Self::reg_index(p) { self.reg_wr[ix] += 1; self.reg_wr_pc[ix] = self.pc; } else { self.note_unmapped(p, 1); }
        if self.port_log_on && ((0x0400_0120..0x0400_0140).contains(&p) || (0x0400_0020..0x0400_0070).contains(&p) || p == 0x0400_0090) && self.port_log.len() < 400_000 { let pc = self.pc; self.port_log.push((pc, p, v)); }
        if let Some((arr, i)) = self.reg_array(p) {
            for k in 0..size as usize {
                if let Some(b) = arr.get_mut(i + k) { *b = (v >> (8 * (size as usize - 1 - k))) as u8; }
            }
        }
        if !self.hooks.is_empty() {
            if let Some(cb) = self.wr_cb {
                for h in &self.hooks {
                    if h.3 && p >= h.0 && p < h.1 { cb(p, size, v); break; }
                }
            }
        }
    }

    // ---------------------------------------------------------------- CPU helpers
    fn set_sr(&mut self, v: u32) {
        let v = v & SR_MASK;
        if (v ^ self.sr) & RB != 0 {
            for i in 0..8 { std::mem::swap(&mut self.r[i], &mut self.bank[i]); }
        }
        self.sr = v;
    }

    fn exception(&mut self, offset: u32, spc: u32) {
        self.spc = spc;
        self.ssr = self.sr;
        self.set_sr(self.sr | MD | RB | BL);
        self.pc = self.vbr.wrapping_add(offset);
        if self.cov_on { let p = Self::phys(self.pc); self.cov_mark(p, 1, 0x80); }
        self.sleeping = false;
    }

    fn pending_irq(&self, imask: u32) -> Option<(u32, u32)> {
        // fast exit: no TMU underflow flag, no external/DMA line, no SCIF TXI
        if (self.tmu.tcr[0] | self.tmu.tcr[1] | self.tmu.tcr[2]) & 0x100 == 0 && self.irq_lines == 0 && self.dma_irq & 1 == 0
            && self.ports[0x154] & 0xA0 != 0xA0 { return None; }
        let hi = self.onchip[(0xFFFF_FEE2u32 - 0xFFFF_FE00) as usize] as u32;
        let lo = self.onchip[(0xFFFF_FEE3u32 - 0xFFFF_FE00) as usize] as u32;
        let ipra = hi << 8 | lo;
        let mut best: Option<(u32, u32)> = None;
        for ch in 0..3usize {
            if self.tmu.tcr[ch] & 0x100 != 0 && self.tmu.tcr[ch] & 0x20 != 0 {
                let level = (ipra >> (12 - 4 * ch)) & 0xF;
                if level > imask && best.map_or(true, |b| level > b.0) { best = Some((level, 0x400 + 0x20 * ch as u32)); }
            }
        }
        let iprc = (self.ports[0x16] as u32) << 8 | self.ports[0x17] as u32;
        let iprd = (self.ports[0x18] as u32) << 8 | self.ports[0x19] as u32;
        for line in 0..6u32 {
            if self.irq_lines >> line & 1 == 0 { continue; }
            let level = match line { 0 => iprc & 0xF, 1 => (iprc >> 4) & 0xF, 2 => (iprc >> 8) & 0xF, 3 => (iprc >> 12) & 0xF,
                                     4 => iprd & 0xF, _ => (iprd >> 4) & 0xF };
            if level > imask && best.map_or(true, |b| level > b.0) { best = Some((level, 0x600 + 0x20 * line)); }
        }
        if self.dma_irq & 1 != 0 {
            let ipre = (self.ports[0x1A] as u32) << 8 | self.ports[0x1B] as u32;
            let level = (ipre >> 12) & 0xF;
            if level > imask && best.map_or(true, |b| level > b.0) { best = Some((level, 0x800)); }
        }
        // SCIF2 transmit-FIFO-empty interrupt (TXI 0x960): level while TIE and TE are set; the FIFO empties instantly here
        if self.ports[0x154] & 0xA0 == 0xA0 {
            let ipre = (self.ports[0x1A] as u32) << 8 | self.ports[0x1B] as u32;
            let level = (ipre >> 4) & 0xF;
            if level > imask && best.map_or(true, |b| level > b.0) { best = Some((level, 0x960)); }
        }
        best
    }

    fn port32(&self, off: usize) -> u32 { u32::from_be_bytes([self.ports[off], self.ports[off + 1], self.ports[off + 2], self.ports[off + 3]]) }
    fn set_port32(&mut self, off: usize, v: u32) { self.ports[off..off + 4].copy_from_slice(&v.to_be_bytes()); }

    /// SH DMAC channel 0 / 1. Transfers that involve the DSP host port are paced by the DSP (HRE / HWE requests).
    fn dma_service(&mut self) {
        if self.ports[0x61] & 1 == 0 { return; }
        for ch in 0..2usize {
            let b = 0x20 + 0x10 * ch;
            let chcr = self.port32(b + 12);
            if chcr & 1 == 0 || chcr & 2 != 0 { continue; }
            let mut sar = self.port32(b);
            let mut dar = self.port32(b + 4);
            let mut tcr = self.port32(b + 8) & 0xFFFFFF;
            let size: u32 = if chcr & 0x18 == 0x08 { 2 } else if chcr & 0x18 == 0x10 { 4 } else { 1 };
            let sm = (chcr >> 12) & 3;
            let dm = (chcr >> 14) & 3;
            let dsp_src = Self::phys(sar) & !0xF == 0x0800_0000;
            let dsp_dst = Self::phys(dar) & !0xF == 0x0800_0000;
            while tcr > 0 {
                let v: u32;
                if dsp_src {
                    match self.sh_out.pop_front() { Some(x) => v = x as u32, None => break }
                } else if size == 2 { v = self.read16(sar); } else if size == 4 { v = self.read32(sar); } else { v = self.read8(sar); }
                if dsp_dst { self.sh_host_write(0, 2, v); } else if size == 2 { self.write16(dar, v); } else if size == 4 { self.write32(dar, v); } else { self.write8(dar, v); }
                if !dsp_src { sar = if sm == 1 { sar.wrapping_add(size) } else if sm == 2 { sar.wrapping_sub(size) } else { sar }; }
                if !dsp_dst { dar = if dm == 1 { dar.wrapping_add(size) } else if dm == 2 { dar.wrapping_sub(size) } else { dar }; }
                tcr -= 1;
            }
            self.set_port32(b, sar);
            self.set_port32(b + 4, dar);
            self.set_port32(b + 8, tcr);
            if tcr == 0 {
                self.set_port32(b + 12, (chcr & !1) | 2);
                if chcr & 4 != 0 { self.dma_irq |= 1 << ch; }
                self.dma_done += 1;
            }
        }
    }

    fn tick_irqs(&mut self, instrs: f64) {
        for l in 0..6 {
            let p = self.irq_period[l];
            if p > 0.0 {
                self.irq_acc[l] += instrs * self.tmu.scale;
                if self.irq_acc[l] >= p { self.irq_acc[l] -= p * (self.irq_acc[l] / p).floor(); self.irq_lines |= 1 << l; }
            }
        }
    }

    fn check_irq(&mut self) {
        if self.sr & BL != 0 { return; }
        if let Some((_, evt)) = self.pending_irq(self.sr & IMASK) {
            self.intevt = evt;
            if (0x600..0x6C0).contains(&evt) { self.irq_lines &= !(1 << ((evt - 0x600) / 0x20)); } // edge: taken
            if evt == 0x800 { self.dma_irq &= !1; }
            let pc = self.pc;
            self.exception(0x600, pc);
        }
    }

    fn illegal_op(&mut self, op: u32, pc: u32) {
        self.illegal += 1;
        self.illegal_pc = pc;
        self.illegal_op = op;
        let (off, ev) = if self.in_slot { (0x100, 0x1A0) } else { (0x100, 0x180) };
        self.expevt = ev;
        self.exception(off, pc);
    }

    fn slot(&mut self) {
        let at = self.pc;
        let op = self.fetch(at);
        self.pc = at.wrapping_add(2);
        self.in_slot = true;
        self.exec(op, at);
        self.in_slot = false;
    }

    // ---------------------------------------------------------------- run
    fn run(&mut self, n: u64) -> u64 {
        let r = self.run_inner(n);
        self.dsp_wait();
        self.dsp_exchange();
        r
    }

    fn dsp_account(&mut self, instrs: u64) {
        self.dsp_acc += instrs as f64 * self.dsp_ratio;
        let dc = self.dsp_acc as u64;
        if dc > 0 { self.dsp_acc -= dc as f64; self.pend_dc += dc; }
    }

    fn ensure_dsp_thread(&mut self) {
        if self.link.is_some() { return; }
        let link = Arc::new(Link { go: AtomicU64::new(0), done: AtomicU64::new(0), cycles: AtomicU64::new(0), quit: AtomicBool::new(false) });
        let l2 = link.clone();
        let p = DspPtr(&mut self.dsp as *mut dsp::Dsp);
        self.seq = 0;
        self.dsp_thread = ThrHandle(Some(std::thread::spawn(move || {
            let p = p;
            let mut last = 0u64;
            let mut spins = 0u32;
            loop {
                let g = l2.go.load(Ordering::Acquire);
                if g != last {
                    let c = l2.cycles.load(Ordering::Relaxed);
                    unsafe { (*p.0).run(c); }
                    last = g;
                    l2.done.store(g, Ordering::Release);
                    spins = 0;
                    continue;
                }
                if l2.quit.load(Ordering::Relaxed) { break; }
                spins += 1;
                if spins < 40_000 { std::hint::spin_loop(); } else { std::thread::sleep(std::time::Duration::from_micros(100)); }
            }
        })));
        self.link = Some(link);
    }

    /// Wait for the DSP quantum in flight.
    fn dsp_wait(&mut self) {
        if !self.inflight { return; }
        if let Some(l) = &self.link { while l.done.load(Ordering::Acquire) != self.seq { std::hint::spin_loop(); } }
        self.inflight = false;
    }

    /// Hand SH writes to the DSP and pick up DSP output (DSP must be idle).
    fn dsp_exchange(&mut self) {
        for m in self.sh_in.drain(..) {
            match m {
                HostMsg::Write { off, size, v, pc, pr } => { self.dsp.wr_pc = pc; self.dsp.wr_pr = pr; self.dsp.host_write(off, size, v); }
                HostMsg::Underflow => self.dsp.mark_read_underflow(),
            }
        }
        self.sh_in_writes = 0;
        while let Some(w) = self.dsp.pop_hout() { self.sh_out.push_back(w); }
        self.hst_snap = self.dsp.hst_raw();
        self.hq_empty_snap = self.dsp.hq_is_empty();
    }

    fn dsp_kick(&mut self, c: u64) {
        if c == 0 { return; }
        if !self.threaded { self.dsp.run(c); return; }
        self.ensure_dsp_thread();
        let l = self.link.as_ref().unwrap();
        l.cycles.store(c, Ordering::Relaxed);
        self.seq += 1;
        l.go.store(self.seq, Ordering::Release);
        self.inflight = true;
    }

    /// Finish the running DSP quantum, exchange data and start the next one (overlapped with SH execution when `overlap`).
    fn dsp_sync(&mut self, overlap: bool) {
        self.dsp_wait();
        self.dsp_exchange();
        let c = std::mem::take(&mut self.pend_dc);
        self.dsp_kick(c);
        if !overlap { self.dsp_wait(); self.dsp_exchange(); }
    }

    fn sh_hst(&self) -> u16 {
        let mut v = self.hst_snap & 0xFFFC;
        if self.hq_empty_snap && self.sh_in_writes == 0 { v |= 1; }
        if !self.sh_out.is_empty() { v |= 2; }
        v
    }

    fn sh_host_read(&mut self, off: u32, size: u32) -> u32 {
        let v = if off & 2 != 0 { self.sh_hst() } else {
            match self.sh_out.pop_front() { Some(x) => x, None => { self.sh_in.push(HostMsg::Underflow); 0 } }
        };
        match size { 1 => if off & 1 == 0 { v as u32 & 0xFF } else { (v >> 8) as u32 }, _ => v as u32 }
    }

    fn sh_host_write(&mut self, off: u32, size: u32, v: u32) {
        let (pc, pr) = (self.pc, self.pr);
        self.sh_in.push(HostMsg::Write { off, size, v, pc, pr });
        if off & 2 == 0 { self.sh_in_writes += 1; }
    }

    fn run_inner(&mut self, n: u64) -> u64 {
        let mut done = 0u64;
        while done < n {
            if self.sleeping {
                let step = match self.tmu.next_event() { Some(s) => (s.ceil() as u64).max(1), None => return done };
                self.tmu.advance(step as f64);
                self.tick_irqs(step as f64);
                self.sleep_instr += step;
                self.dsp_account(step);
                self.dsp_sync(false);
                done += step;
                if self.pending_irq(self.sr & IMASK).is_none() && self.sr & BL == 0 { /* keep sleeping */ }
                self.check_irq();
                continue;
            }
            let chunk = CHUNK.min(n - done);
            let mut i = 0;
            let stop = self.stop_pc;
            while i < chunk {
                if self.pc == stop && (i > 0 || done > 0) { self.tmu.advance(i as f64); self.cycles += i; return done + i; }
                let pc = self.pc;
                let op = self.fetch(pc);
                self.pc = pc.wrapping_add(2);
                if self.cov_on { self.cov_branch(op, pc); }
                self.exec_i(op, pc);
                i += 1;
                if self.sleeping { break; }
            }
            done += i;
            self.cycles += i;
            self.dsp_account(i);
            self.chunk_n += 1;
            if self.chunk_n % XCHG_EVERY == 0 { self.dsp_sync(true); }
            self.dma_service();
            self.tmu.advance(i as f64);
            self.tick_irqs(i as f64);
            self.check_irq();
        }
        done
    }

    #[inline(never)]
    fn exec(&mut self, op: u32, pc: u32) { self.exec_i(op, pc) }

    #[inline(always)]
    fn exec_i(&mut self, op: u32, pc: u32) {
        let n = ((op >> 8) & 15) as usize;
        let m = ((op >> 4) & 15) as usize;
        let d = op & 15;
        match op >> 12 {
            0x0 => self.op0(op, n, m, d, pc),
            0x1 => { let a = self.r[n].wrapping_add(d * 4); let v = self.r[m]; self.write32(a, v); }
            0x2 => self.op2(op, n, m, d, pc),
            0x3 => self.op3(op, n, m, d, pc),
            0x4 => self.op4(op, n, m, d, pc),
            0x5 => { let a = self.r[m].wrapping_add(d * 4); self.r[n] = self.read32(a); }
            0x6 => self.op6(op, n, m, d, pc),
            0x7 => { self.r[n] = self.r[n].wrapping_add(s8(op) as u32); }
            0x8 => self.op8(op, n, m, d, pc),
            0x9 => {
                let a = pc.wrapping_add(4).wrapping_add((op & 0xFF) * 2);
                self.r[n] = s16(self.read16(a)) as u32;
            }
            0xA => {
                let mut disp = (op & 0xFFF) as i32;
                if disp & 0x800 != 0 { disp -= 0x1000; }
                let t = pc.wrapping_add(4).wrapping_add((disp * 2) as u32);
                self.slot();
                self.pc = t;
            }
            0xB => {
                let mut disp = (op & 0xFFF) as i32;
                if disp & 0x800 != 0 { disp -= 0x1000; }
                self.pr = pc.wrapping_add(4);
                let t = pc.wrapping_add(4).wrapping_add((disp * 2) as u32);
                self.slot();
                self.pc = t;
            }
            0xC => self.opc(op, n, m, d, pc),
            0xD => {
                let a = (pc.wrapping_add(4) & !3).wrapping_add((op & 0xFF) * 4);
                self.r[n] = self.read32(a);
            }
            0xE => { self.r[n] = s8(op) as u32; }
            _ => self.illegal_op(op, pc),
        }
    }

    fn cov_branch(&mut self, op: u32, pc: u32) {
        let m = op & 0xF0FF;
        let n = ((op >> 8) & 15) as usize;
        if m == 0x400B { let t = Self::phys(self.r[n]); self.cov_mark(t, 1, 0x40); }
        else if m == 0x402B { let t = Self::phys(self.r[n]); self.cov_mark(t, 1, 0x80); }
        else if op & 0xF000 == 0xB000 {
            let mut disp = (op & 0xFFF) as i32; if disp & 0x800 != 0 { disp -= 0x1000; }
            let t = Self::phys(pc.wrapping_add(4).wrapping_add((disp * 2) as u32)); self.cov_mark(t, 1, 0x40);
        } else if m == 0x0003 || op & 0xF0FF == 0x0003 {
            // bsrf Rn
            let t = Self::phys(pc.wrapping_add(4).wrapping_add(self.r[n])); self.cov_mark(t, 1, 0x40);
        }
    }

    fn setb(&mut self, cond: bool) { if cond { self.sr |= T } else { self.sr &= !T } }

    fn op0(&mut self, op: u32, n: usize, m: usize, d: u32, pc: u32) {
        match d {
            2 => match m {
                0 => self.r[n] = self.sr,
                1 => self.r[n] = self.gbr,
                2 => self.r[n] = self.vbr,
                3 => self.r[n] = self.ssr,
                4 => self.r[n] = self.spc,
                8..=15 => self.r[n] = self.bank[m & 7],
                _ => self.illegal_op(op, pc),
            },
            3 => match m {
                0 => { self.pr = pc.wrapping_add(4); let t = pc.wrapping_add(4).wrapping_add(self.r[n]); self.slot(); self.pc = t; }
                2 => { let t = pc.wrapping_add(4).wrapping_add(self.r[n]); self.slot(); self.pc = t; }
                8 => {}
                _ => self.illegal_op(op, pc),
            },
            4 => { let a = self.r[0].wrapping_add(self.r[n]); let v = self.r[m]; self.write8(a, v & 0xFF); }
            5 => { let a = self.r[0].wrapping_add(self.r[n]); let v = self.r[m]; self.write16(a, v & 0xFFFF); }
            6 => { let a = self.r[0].wrapping_add(self.r[n]); let v = self.r[m]; self.write32(a, v); }
            7 => self.macl = self.r[n].wrapping_mul(self.r[m]),
            8 => match op & 0xFF {
                0x08 => self.sr &= !T,
                0x18 => self.sr |= T,
                0x28 => { self.mach = 0; self.macl = 0; }
                0x38 => {}
                0x48 => self.sr &= !S,
                0x58 => self.sr |= S,
                _ => self.illegal_op(op, pc),
            },
            9 => match m {
                0 => {}
                1 => self.sr &= !(M | Q | T),
                2 => self.r[n] = self.sr & 1,
                _ => self.illegal_op(op, pc),
            },
            10 => match m {
                0 => self.r[n] = self.mach,
                1 => self.r[n] = self.macl,
                2 => self.r[n] = self.pr,
                _ => self.illegal_op(op, pc),
            },
            11 => match op {
                0x000B => { let t = self.pr; self.slot(); self.pc = t; }
                0x001B => { self.sleeping = true; }
                0x002B => { let t = self.spc; let ssr = self.ssr; self.slot(); self.set_sr(ssr); self.pc = t; }
                _ => self.illegal_op(op, pc),
            },
            12 => { let a = self.r[0].wrapping_add(self.r[m]); self.r[n] = s8(self.read8(a)) as u32; }
            13 => { let a = self.r[0].wrapping_add(self.r[m]); self.r[n] = s16(self.read16(a)) as u32; }
            14 => { let a = self.r[0].wrapping_add(self.r[m]); self.r[n] = self.read32(a); }
            15 => {
                let a = s32(self.read32(self.r[n])) as i64;
                self.r[n] = self.r[n].wrapping_add(4);
                let b = s32(self.read32(self.r[m])) as i64;
                self.r[m] = self.r[m].wrapping_add(4);
                let mut acc = ((self.mach as u64) << 32 | self.macl as u64) as i64;
                acc = acc.wrapping_add(a * b);
                if self.sr & S != 0 { acc = acc.clamp(-(1i64 << 47), (1i64 << 47) - 1); }
                self.mach = (acc >> 32) as u32;
                self.macl = acc as u32;
            }
            _ => self.illegal_op(op, pc),
        }
    }

    fn op2(&mut self, op: u32, n: usize, m: usize, d: u32, pc: u32) {
        match d {
            0 => { let a = self.r[n]; let v = self.r[m]; self.write8(a, v & 0xFF); }
            1 => { let a = self.r[n]; let v = self.r[m]; self.write16(a, v & 0xFFFF); }
            2 => { let a = self.r[n]; let v = self.r[m]; self.write32(a, v); }
            4 => { let a = self.r[n].wrapping_sub(1); let v = self.r[m]; self.write8(a, v & 0xFF); self.r[n] = a; }
            5 => { let a = self.r[n].wrapping_sub(2); let v = self.r[m]; self.write16(a, v & 0xFFFF); self.r[n] = a; }
            6 => { let a = self.r[n].wrapping_sub(4); let v = self.r[m]; self.write32(a, v); self.r[n] = a; }
            7 => {
                let q = self.r[n] >> 31;
                let mm = self.r[m] >> 31;
                self.sr = (self.sr & !(Q | M | T)) | if q != 0 { Q } else { 0 } | if mm != 0 { M } else { 0 } | if q != mm { T } else { 0 };
            }
            8 => { let c = self.r[n] & self.r[m] == 0; self.setb(c); }
            9 => self.r[n] &= self.r[m],
            10 => self.r[n] ^= self.r[m],
            11 => self.r[n] |= self.r[m],
            12 => {
                let x = self.r[n] ^ self.r[m];
                let hit = x & 0xFF00_0000 == 0 || x & 0xFF_0000 == 0 || x & 0xFF00 == 0 || x & 0xFF == 0;
                self.setb(hit);
            }
            13 => self.r[n] = (self.r[m] << 16) | (self.r[n] >> 16),
            14 => self.macl = (self.r[n] & 0xFFFF).wrapping_mul(self.r[m] & 0xFFFF),
            15 => self.macl = (s16(self.r[n]).wrapping_mul(s16(self.r[m]))) as u32,
            _ => self.illegal_op(op, pc),
        }
    }

    fn op3(&mut self, op: u32, n: usize, m: usize, d: u32, pc: u32) {
        let (a, b) = (self.r[n], self.r[m]);
        match d {
            0 => self.setb(a == b),
            2 => self.setb(a >= b),
            3 => self.setb(s32(a) >= s32(b)),
            4 => {
                let sr = self.sr;
                let old_q = (sr & Q != 0) as u32;
                let mm = (sr & M != 0) as u32;
                let mut q = a >> 31;
                let mut rn = (a << 1) | (sr & 1);
                let tmp0 = rn;
                if old_q == mm {
                    rn = rn.wrapping_sub(b);
                    let tmp1 = (rn > tmp0) as u32;
                    q = if old_q == 0 { if q == 0 { tmp1 } else { 1 - tmp1 } } else if q == 0 { 1 - tmp1 } else { tmp1 };
                } else {
                    rn = rn.wrapping_add(b);
                    let tmp1 = (rn < tmp0) as u32;
                    q = if old_q == 0 { if q == 0 { 1 - tmp1 } else { tmp1 } } else if q == 0 { tmp1 } else { 1 - tmp1 };
                }
                self.r[n] = rn;
                self.sr = (sr & !(Q | T)) | if q != 0 { Q } else { 0 } | if q == mm { T } else { 0 };
            }
            5 => { let p = (a as u64) * (b as u64); self.mach = (p >> 32) as u32; self.macl = p as u32; }
            6 => self.setb(a > b),
            7 => self.setb(s32(a) > s32(b)),
            8 => self.r[n] = a.wrapping_sub(b),
            10 => {
                let t = (self.sr & 1) as u64;
                let x = (a as u64).wrapping_sub(b as u64).wrapping_sub(t);
                self.r[n] = x as u32;
                self.setb(x >> 63 != 0);
            }
            11 => {
                let x = s32(a) as i64 - s32(b) as i64;
                self.r[n] = x as u32;
                self.setb(x < i32::MIN as i64 || x > i32::MAX as i64);
            }
            12 => self.r[n] = a.wrapping_add(b),
            13 => { let p = (s32(a) as i64).wrapping_mul(s32(b) as i64) as u64; self.mach = (p >> 32) as u32; self.macl = p as u32; }
            14 => {
                let x = a as u64 + b as u64 + (self.sr & 1) as u64;
                self.r[n] = x as u32;
                self.setb(x >> 32 != 0);
            }
            15 => {
                let x = s32(a) as i64 + s32(b) as i64;
                self.r[n] = x as u32;
                self.setb(x < i32::MIN as i64 || x > i32::MAX as i64);
            }
            _ => self.illegal_op(op, pc),
        }
    }

    fn ctl_get(&self, i: u32) -> u32 {
        match i { 0 => self.sr, 1 => self.gbr, 2 => self.vbr, 3 => self.ssr, _ => self.spc }
    }
    fn ctl_set(&mut self, i: u32, v: u32) {
        match i { 0 => self.set_sr(v), 1 => self.gbr = v, 2 => self.vbr = v, 3 => self.ssr = v, _ => self.spc = v }
    }
    fn sys_get(&self, i: u32) -> u32 { match i { 0 => self.mach, 1 => self.macl, _ => self.pr } }
    fn sys_set(&mut self, i: u32, v: u32) { match i { 0 => self.mach = v, 1 => self.macl = v, _ => self.pr = v } }

    fn op4(&mut self, op: u32, n: usize, m: usize, d: u32, pc: u32) {
        let lo = op & 0xFF;
        match d {
            12 => {
                let sft = self.r[m];
                let x = s32(self.r[n]);
                self.r[n] = if sft & 0x8000_0000 == 0 { (x << (sft & 31)) as u32 }
                    else if sft & 31 != 0 { (x >> (32 - (sft & 31))) as u32 }
                    else if x < 0 { 0xFFFF_FFFF } else { 0 };
                return;
            }
            13 => {
                let sft = self.r[m];
                let x = self.r[n];
                self.r[n] = if sft & 0x8000_0000 == 0 { x << (sft & 31) }
                    else if sft & 31 != 0 { x >> (32 - (sft & 31)) } else { 0 };
                return;
            }
            15 => {
                let a = s16(self.read16(self.r[n])) as i64;
                self.r[n] = self.r[n].wrapping_add(2);
                let b = s16(self.read16(self.r[m])) as i64;
                self.r[m] = self.r[m].wrapping_add(2);
                let p = a * b;
                if self.sr & S != 0 {
                    let x = s32(self.macl) as i64 + p;
                    if x > 0x7FFF_FFFF { self.macl = 0x7FFF_FFFF; self.mach |= 1; }
                    else if x < -0x8000_0000 { self.macl = 0x8000_0000; self.mach |= 1; }
                    else { self.macl = x as u32; }
                } else {
                    let acc = ((self.mach as u64) << 32 | self.macl as u64).wrapping_add(p as u64);
                    self.mach = (acc >> 32) as u32;
                    self.macl = acc as u32;
                }
                return;
            }
            3 if m & 8 != 0 => { let a = self.r[n].wrapping_sub(4); let v = self.bank[m & 7]; self.write32(a, v); self.r[n] = a; return; }
            7 if m & 8 != 0 => { let v = self.read32(self.r[n]); self.bank[m & 7] = v; self.r[n] = self.r[n].wrapping_add(4); return; }
            14 if m & 8 != 0 => { self.bank[m & 7] = self.r[n]; return; }
            2 if m <= 2 => { let a = self.r[n].wrapping_sub(4); let v = self.sys_get(m as u32); self.write32(a, v); self.r[n] = a; return; }
            3 if m <= 4 => { let a = self.r[n].wrapping_sub(4); let v = self.ctl_get(m as u32); self.write32(a, v); self.r[n] = a; return; }
            6 if m <= 2 => { let v = self.read32(self.r[n]); self.sys_set(m as u32, v); self.r[n] = self.r[n].wrapping_add(4); return; }
            7 if m <= 4 => { let v = self.read32(self.r[n]); self.r[n] = self.r[n].wrapping_add(4); self.ctl_set(m as u32, v); return; }
            10 if m <= 2 => { let v = self.r[n]; self.sys_set(m as u32, v); return; }
            14 if m <= 4 => { let v = self.r[n]; self.ctl_set(m as u32, v); return; }
            _ => {}
        }
        let v = self.r[n];
        match lo {
            0x00 => { self.r[n] = v << 1; self.setb(v >> 31 != 0); }
            0x01 => { self.r[n] = v >> 1; self.setb(v & 1 != 0); }
            0x04 => { self.r[n] = (v << 1) | (v >> 31); self.setb(v >> 31 != 0); }
            0x05 => { self.r[n] = (v >> 1) | (v << 31); self.setb(v & 1 != 0); }
            0x08 => self.r[n] = v << 2,
            0x09 => self.r[n] = v >> 2,
            0x18 => self.r[n] = v << 8,
            0x19 => self.r[n] = v >> 8,
            0x20 => { self.r[n] = v << 1; self.setb(v >> 31 != 0); }
            0x21 => { self.r[n] = (v >> 1) | (v & 0x8000_0000); self.setb(v & 1 != 0); }
            0x24 => { self.r[n] = (v << 1) | (self.sr & 1); self.setb(v >> 31 != 0); }
            0x25 => { self.r[n] = (v >> 1) | ((self.sr & 1) << 31); self.setb(v & 1 != 0); }
            0x28 => self.r[n] = v << 16,
            0x29 => self.r[n] = v >> 16,
            0x0B => { self.pr = pc.wrapping_add(4); let t = v; self.slot(); self.pc = t; }
            0x2B => { let t = v; self.slot(); self.pc = t; }
            0x10 => { self.r[n] = v.wrapping_sub(1); let z = self.r[n] == 0; self.setb(z); }
            0x11 => self.setb(v & 0x8000_0000 == 0),
            0x15 => self.setb(v > 0 && v < 0x8000_0000),
            0x1B => { let b = self.read8(v); self.setb(b == 0); self.write8(v, b | 0x80); }
            _ => self.illegal_op(op, pc),
        }
    }

    fn op6(&mut self, op: u32, n: usize, m: usize, d: u32, pc: u32) {
        let rm = self.r[m];
        match d {
            0 => self.r[n] = s8(self.read8(rm)) as u32,
            1 => self.r[n] = s16(self.read16(rm)) as u32,
            2 => self.r[n] = self.read32(rm),
            3 => self.r[n] = rm,
            4 => { let v = s8(self.read8(rm)) as u32; if n != m { self.r[m] = rm.wrapping_add(1); } self.r[n] = v; }
            5 => { let v = s16(self.read16(rm)) as u32; if n != m { self.r[m] = rm.wrapping_add(2); } self.r[n] = v; }
            6 => { let v = self.read32(rm); if n != m { self.r[m] = rm.wrapping_add(4); } self.r[n] = v; }
            7 => self.r[n] = !rm,
            8 => self.r[n] = (rm & 0xFFFF_0000) | (rm << 8 & 0xFF00) | (rm >> 8 & 0xFF),
            9 => self.r[n] = (rm << 16) | (rm >> 16),
            10 => {
                let x = 0u64.wrapping_sub(rm as u64).wrapping_sub((self.sr & 1) as u64);
                self.r[n] = x as u32;
                self.setb(x >> 63 != 0);
            }
            11 => self.r[n] = 0u32.wrapping_sub(rm),
            12 => self.r[n] = rm & 0xFF,
            13 => self.r[n] = rm & 0xFFFF,
            14 => self.r[n] = s8(rm) as u32,
            15 => self.r[n] = s16(rm) as u32,
            _ => self.illegal_op(op, pc),
        }
    }

    fn op8(&mut self, op: u32, n: usize, m: usize, d: u32, pc: u32) {
        match n {
            0 => { let a = self.r[m].wrapping_add(d); let v = self.r[0]; self.write8(a, v & 0xFF); }
            1 => { let a = self.r[m].wrapping_add(d * 2); let v = self.r[0]; self.write16(a, v & 0xFFFF); }
            4 => { let a = self.r[m].wrapping_add(d); self.r[0] = s8(self.read8(a)) as u32; }
            5 => { let a = self.r[m].wrapping_add(d * 2); self.r[0] = s16(self.read16(a)) as u32; }
            8 => { let c = self.r[0] == s8(op) as u32; self.setb(c); }
            9 | 11 | 13 | 15 => {
                let disp = (s8(op) * 2 + 4) as u32;
                let t = pc.wrapping_add(disp);
                let take = if n == 9 || n == 13 { self.sr & 1 != 0 } else { self.sr & 1 == 0 };
                if take {
                    if n == 13 || n == 15 { self.slot(); }
                    self.pc = t;
                }
            }
            _ => self.illegal_op(op, pc),
        }
    }

    fn opc(&mut self, op: u32, n: usize, _m: usize, _d: u32, pc: u32) {
        let i = op & 0xFF;
        match n {
            0 => { let a = self.gbr.wrapping_add(i); let v = self.r[0]; self.write8(a, v & 0xFF); }
            1 => { let a = self.gbr.wrapping_add(i * 2); let v = self.r[0]; self.write16(a, v & 0xFFFF); }
            2 => { let a = self.gbr.wrapping_add(i * 4); let v = self.r[0]; self.write32(a, v); }
            3 => { self.tra = i << 2; self.expevt = 0x160; let spc = self.pc; self.exception(0x100, spc); }
            4 => { let a = self.gbr.wrapping_add(i); self.r[0] = s8(self.read8(a)) as u32; }
            5 => { let a = self.gbr.wrapping_add(i * 2); self.r[0] = s16(self.read16(a)) as u32; }
            6 => { let a = self.gbr.wrapping_add(i * 4); self.r[0] = self.read32(a); }
            7 => self.r[0] = (pc & !3).wrapping_add(4).wrapping_add(i * 4),
            8 => { let c = self.r[0] & i == 0; self.setb(c); }
            9 => self.r[0] &= i,
            10 => self.r[0] ^= i,
            11 => self.r[0] |= i,
            12 => { let a = self.gbr.wrapping_add(self.r[0]); let v = self.read8(a); self.setb(v & i == 0); }
            13 | 14 | 15 => {
                let a = self.gbr.wrapping_add(self.r[0]);
                let v = self.read8(a);
                let nv = match n { 13 => v & i, 14 => v ^ i, _ => v | i };
                self.write8(a, nv);
            }
            _ => self.illegal_op(op, pc),
        }
    }
}

#[inline]
fn s32(x: u32) -> i32 { x as i32 }

// ------------------------------------------------------------------------------------------------ C API
#[no_mangle]
pub extern "C" fn emu_new(flash: *const u8, flash_len: usize, sdram_mb: usize) -> *mut Emu {
    let f = unsafe { slice::from_raw_parts(flash, flash_len) };
    Box::into_raw(Box::new(Emu::new(f, sdram_mb)))
}

#[no_mangle]
pub extern "C" fn emu_free(e: *mut Emu) {
    if e.is_null() { return; }
    unsafe {
        let em = &mut *e;
        em.dsp_wait();
        if let Some(l) = em.link.take() { l.quit.store(true, Ordering::Relaxed); if let Some(t) = em.dsp_thread.0.take() { let _ = t.join(); } }
        drop(Box::from_raw(e))
    }
}

#[no_mangle]
pub extern "C" fn emu_set_threaded(e: *mut Emu, on: u32) { unsafe { let em = &mut *e; em.dsp_wait(); em.dsp_exchange(); em.threaded = on != 0; } }

#[no_mangle]
pub extern "C" fn emu_run(e: *mut Emu, n: u64) -> u64 { unsafe { (*e).run(n) } }

#[no_mangle]
pub extern "C" fn emu_set_stop_pc(e: *mut Emu, pc: u32) { unsafe { (*e).stop_pc = pc } }

#[no_mangle]
pub extern "C" fn emu_set_callbacks(e: *mut Emu, rd: Option<RdCb>, wr: Option<WrCb>) {
    unsafe { (*e).rd_cb = rd; (*e).wr_cb = wr; }
}

#[no_mangle]
pub extern "C" fn emu_hook(e: *mut Emu, lo: u32, hi: u32, on_read: u32, on_write: u32) {
    unsafe { (*e).hooks.push((lo, hi, on_read != 0, on_write != 0)) }
}

#[no_mangle]
pub extern "C" fn emu_force_read(e: *mut Emu, addr: u32, mask: u32, value: u32) {
    unsafe {
        let f = &mut (*e).force;
        f.retain(|x| x.0 != addr);
        f.push((addr, mask as u8, value as u8));
    }
}

#[no_mangle]
pub extern "C" fn emu_set_timescale(e: *mut Emu, s: f64) { unsafe { (*e).tmu.scale = s } }

#[no_mangle]
pub extern "C" fn emu_nand_set(e: *mut Emu, idx: u32, data: *const u8, len: usize, maker: u32, dev: u32) {
    unsafe {
        let c = &mut (*e).chips[idx as usize];
        if data.is_null() { *c = Chip::default(); return; }
        let d = slice::from_raw_parts(data, len).to_vec();
        let pages = len / (PAGE + SPARE);
        *c = Chip { present: true, maker: maker as u8, dev: dev as u8, data: d, pages, status: 0xC0, cmd: 0xFF,
                    addr_cycles: if pages * PAGE <= 32 * 1024 * 1024 { 3 } else { 4 }, ..Chip::default() };
    }
}

#[no_mangle]
pub extern "C" fn emu_nand_ptr(e: *mut Emu, idx: u32) -> *const u8 { unsafe { (*e).chips[idx as usize].data.as_ptr() } }
#[no_mangle]
pub extern "C" fn emu_nand_len(e: *mut Emu, idx: u32) -> usize { unsafe { (*e).chips[idx as usize].data.len() } }
#[no_mangle]
pub extern "C" fn emu_nand_cmds(e: *mut Emu, idx: u32) -> u64 { unsafe { (*e).chips[idx as usize].cmds } }
#[no_mangle]
pub extern "C" fn emu_sdram_ptr(e: *mut Emu) -> *mut u8 { unsafe { (*e).sdram.as_mut_ptr() } }
#[no_mangle]
pub extern "C" fn emu_sdram_len(e: *mut Emu) -> usize { unsafe { (*e).sdram.len() } }
#[no_mangle]
pub extern "C" fn emu_flash_ptr(e: *mut Emu) -> *mut u8 { unsafe { (*e).flash.as_mut_ptr() } }
#[no_mangle]
pub extern "C" fn emu_ports_ptr(e: *mut Emu) -> *mut u8 { unsafe { (*e).ports.as_mut_ptr() } }

/// Registers: 0..15 r, 16 pc, 17 pr, 18 sr, 19 gbr, 20 vbr, 21 ssr, 22 spc, 23 mach, 24 macl, 25 sleeping,
/// 26 cycles (low 32 bits), 27 illegal count, 28 illegal pc, 29 illegal op, 30 intevt, 31 nor erases, 32 nor programmed,
/// 33 nor bad programs, 34 tmu.under0, 35 tmu.under1, 36 tmu.under2, 37 tmu.tstr, 38 tmu.tcr0, 39 tmu.tcor0
#[no_mangle]
pub extern "C" fn emu_get(e: *mut Emu, i: u32) -> u64 {
    let e = unsafe { &*e };
    match i {
        0..=15 => e.r[i as usize] as u64,
        16 => e.pc as u64, 17 => e.pr as u64, 18 => e.sr as u64, 19 => e.gbr as u64, 20 => e.vbr as u64,
        21 => e.ssr as u64, 22 => e.spc as u64, 23 => e.mach as u64, 24 => e.macl as u64,
        25 => e.sleeping as u64, 26 => e.cycles, 27 => e.illegal as u64, 28 => e.illegal_pc as u64,
        29 => e.illegal_op as u64, 30 => e.intevt as u64, 31 => e.nor.erases as u64, 32 => e.nor.programmed,
        33 => e.nor.bad, 34 => e.tmu.under[0], 35 => e.tmu.under[1], 36 => e.tmu.under[2],
        40 => e.unm_pc.last().copied().unwrap_or(0) as u64,
        41 => e.unm_pc.get(0).copied().unwrap_or(0) as u64,
        37 => e.tmu.tstr as u64, 38 => e.tmu.tcr[0] as u64, 39 => e.tmu.tcor[0] as u64,
        _ => 0,
    }
}

#[no_mangle]
pub extern "C" fn emu_set(e: *mut Emu, i: u32, v: u64) {
    let e = unsafe { &mut *e };
    match i {
        0..=15 => e.r[i as usize] = v as u32,
        16 => e.pc = v as u32, 17 => e.pr = v as u32, 18 => e.set_sr(v as u32),
        25 => e.sleeping = v != 0,
        _ => {}
    }
}

#[no_mangle]
pub extern "C" fn emu_read32(e: *mut Emu, a: u32) -> u32 { unsafe { (*e).read32(a) } }
#[no_mangle]
pub extern "C" fn emu_write8(e: *mut Emu, a: u32, v: u32) { unsafe { (*e).write8(a, v) } }
#[no_mangle]
pub extern "C" fn emu_write16(e: *mut Emu, a: u32, v: u32) { unsafe { (*e).write16(a, v) } }

#[no_mangle]
pub extern "C" fn emu_unmapped(e: *mut Emu, idx: u32, addr: *mut u32, kind: *mut u32, count: *mut u64) -> u32 {
    unsafe {
        let e = &*e;
        match e.unmapped.get(idx as usize) {
            Some(u) => { *addr = u.0; *kind = u.1 as u32; *count = u.2; 1 }
            None => 0,
        }
    }
}

/// Access counters of the register areas: idx 0..0x1FF = 0x04000000 block, 0x200..0x3FF = 0xFFFFFE00 block.
#[no_mangle]
pub extern "C" fn emu_reg_count(e: *mut Emu, write: u32, idx: u32) -> u64 {
    unsafe { let e = &*e; if write != 0 { e.reg_wr[idx as usize] } else { e.reg_rd[idx as usize] } }
}

#[no_mangle]
pub extern "C" fn emu_clear_counts(e: *mut Emu) {
    unsafe { let e = &mut *e; e.unmapped.clear(); e.unm_pc.clear(); for v in e.reg_rd.iter_mut() { *v = 0; } for v in e.reg_wr.iter_mut() { *v = 0; } }
}

#[no_mangle]
pub extern "C" fn emu_unmapped_pc(e: *mut Emu, idx: u32) -> u32 { unsafe { let e = &*e; e.unm_pc.get(idx as usize).copied().unwrap_or(0) } }

#[no_mangle]
pub extern "C" fn emu_raise_irq(e: *mut Emu, line: u32) { unsafe { (*e).irq_lines |= 1 << line } }

#[no_mangle]
pub extern "C" fn emu_watch(e: *mut Emu, lo: u32, hi: u32) { unsafe { (*e).watch = (lo, hi); (*e).watch_log.clear(); } }
#[no_mangle]
pub extern "C" fn emu_watch_get(e: *mut Emu, idx: u32, pc: *mut u32, addr: *mut u32, size: *mut u32, val: *mut u32) -> u32 {
    unsafe {
        let e = &*e;
        match e.watch_log.get(idx as usize) { Some(w) => { *pc = w.0; *addr = w.1; *size = w.2; *val = w.3; 1 } None => 0 }
    }
}

#[no_mangle]
pub extern "C" fn emu_scif_tx(e: *mut Emu, buf: *mut u8, max: usize) -> usize {
    unsafe {
        let e = &mut *e;
        let n = e.scif_tx.len().min(max);
        for i in 0..n { *buf.add(i) = e.scif_tx[i]; }
        e.scif_tx.drain(..n);
        n
    }
}

#[no_mangle]
pub extern "C" fn emu_set_adc(e: *mut Emu, ch: u32, value10: u32) {
    unsafe {
        let e = &mut *e;
        if ch < 8 { let v = (value10 & 0x3FF) << 6; e.ports[0x80 + 2 * ch as usize] = (v >> 8) as u8; e.ports[0x81 + 2 * ch as usize] = v as u8; }
    }
}

/// Periodic edge interrupt on external line `line` (0..5), period in CPU instructions at time scale 1; 0 switches it off.
#[no_mangle]
pub extern "C" fn emu_irq_period(e: *mut Emu, line: u32, period: f64) { unsafe { if line < 6 { (*e).irq_period[line as usize] = period; (*e).irq_acc[line as usize] = 0.0; } } }

/// Rows (page numbers) read (kind 0) or programmed (kind 1) since the last call; clears the list. Returns the count copied.
#[no_mangle]
pub extern "C" fn emu_nand_rows(e: *mut Emu, idx: u32, kind: u32, buf: *mut u32, max: usize) -> usize {
    unsafe {
        let c = &mut (*e).chips[idx as usize];
        let v = if kind == 0 { &mut c.read_rows } else { &mut c.write_rows };
        let n = v.len().min(max);
        for i in 0..n { *buf.add(i) = v[i]; }
        v.drain(..n);
        n
    }
}

/// Copy of the whole machine state (CPU, memories, chips, timers). Callbacks and hooks are copied too.
#[no_mangle]
pub extern "C" fn emu_snapshot(e: *mut Emu) -> *mut Emu { unsafe { Box::into_raw(Box::new((*e).clone())) } }

/// Overwrite the machine with a snapshot. Pointers handed out earlier (sdram, flash, ports) stay valid only if the sizes match,
/// which they do for snapshots of the same machine; the caller must re-read them anyway.
#[no_mangle]
pub extern "C" fn emu_restore(e: *mut Emu, snap: *const Emu) {
    unsafe {
        let s = &*snap;
        let em = &mut *e;
        em.r = s.r; em.bank = s.bank; em.pc = s.pc; em.pr = s.pr; em.gbr = s.gbr; em.vbr = s.vbr; em.ssr = s.ssr; em.spc = s.spc;
        em.mach = s.mach; em.macl = s.macl; em.sr = s.sr; em.sleeping = s.sleeping; em.in_slot = s.in_slot; em.cycles = s.cycles;
        em.tra = s.tra; em.expevt = s.expevt; em.intevt = s.intevt;
        em.flash.copy_from_slice(&s.flash); em.sdram.copy_from_slice(&s.sdram);
        em.ports.copy_from_slice(&s.ports); em.onchip.copy_from_slice(&s.onchip);
        em.nor = s.nor.clone(); em.chips = s.chips.clone(); em.tmu = s.tmu.clone();
        em.irq_lines = s.irq_lines; em.irq_acc = s.irq_acc; em.scif_tx.clear();
    }
}

#[no_mangle]
pub extern "C" fn emu_reg_read_pc(e: *mut Emu, idx: u32) -> u32 { unsafe { let e = &*e; e.reg_rd_pc[idx as usize] } }

#[no_mangle]
pub extern "C" fn emu_reg_write_pc(e: *mut Emu, idx: u32) -> u32 { unsafe { let e = &*e; e.reg_wr_pc[idx as usize] } }
#[no_mangle]
pub extern "C" fn emu_port_log(e: *mut Emu, on: u32) { unsafe { let e = &mut *e; e.port_log_on = on != 0; e.port_log.clear(); } }
#[no_mangle]
pub extern "C" fn emu_port_log_get(e: *mut Emu, idx: u32, pc: *mut u32, addr: *mut u32, val: *mut u32) -> u32 {
    unsafe { let e = &*e; match e.port_log.get(idx as usize) { Some(w) => { *pc = w.0; *addr = w.1; *val = w.2; 1 } None => 0 } }
}

/// Analog input value (10 bit) seen on A/D channel `ch` while the multiplexer address (port D low nibble) is `col`.
#[no_mangle]
pub extern "C" fn emu_set_adc_in(e: *mut Emu, col: u32, ch: u32, value10: u32) {
    unsafe { let e = &mut *e; if col < 64 && ch < 8 { e.adc_in[col as usize][ch as usize] = (value10 & 0x3FF) as u16; } }
}


#[no_mangle]
pub extern "C" fn emu_dsp_word(e: *mut Emu, i: u32) -> u64 { unsafe { if i == 100 { (*e).dma_done } else if i == 101 { (*e).sleep_instr } else { (*e).dsp.word(i) } } }

#[no_mangle]
pub extern "C" fn emu_dsp_config(e: *mut Emu, ratio: f64, aso_period: u64, trace: u32) {
    unsafe { let e = &mut *e; e.dsp_ratio = ratio; e.dsp.aso_period = aso_period; e.dsp.trace_on = trace != 0; e.dsp.trace.clear(); }
}

#[no_mangle]
pub extern "C" fn emu_dsp_unimpl(e: *mut Emu, idx: u32, addr: *mut u32, kind: *mut u32, count: *mut u64, pc: *mut u32) -> u32 {
    unsafe {
        let e = &*e;
        let mut keys: Vec<_> = e.dsp.unimpl.iter().collect();
        keys.sort();
        match keys.get(idx as usize) {
            Some(((a, k), (c, p))) => { *addr = *a as u32; *kind = *k as u32; *count = *c; *pc = *p as u32; 1 }
            None => 0,
        }
    }
}

#[no_mangle]
pub extern "C" fn emu_dsp_trace_get(e: *mut Emu, idx: u32, pc: *mut u32, w: *mut u32) -> u32 {
    unsafe { let e = &*e; match e.dsp.trace.get(idx as usize) { Some((a, b)) => { *pc = *a as u32; *w = *b; 1 } None => 0 } }
}

#[no_mangle]
pub extern "C" fn emu_dsp_audio(e: *mut Emu, which: u32, buf: *mut i16, max: usize) -> usize {
    unsafe { let e = &mut *e; let v = if which == 0 { &mut e.dsp.audio } else { &mut e.dsp.audio2 }; let n = v.len().min(max); for k in 0..n { *buf.add(k) = v[k]; } v.drain(..n); n }
}

#[no_mangle]
pub extern "C" fn emu_dsp_mem(e: *mut Emu, kind: u32, addr: u32) -> u32 { unsafe { (*e).dsp.peek(kind, addr) } }

#[no_mangle]
pub extern "C" fn emu_dsp_int0(e: *mut Emu, every: u64) { unsafe { (*e).dsp.int0_every = every } }

#[no_mangle]
pub extern "C" fn emu_dsp_wrpc(e: *mut Emu, idx: u32, pc: *mut u32, pr: *mut u32, n: *mut u64) -> u32 {
    unsafe { let e = &*e; let mut v: Vec<_> = e.dsp.wr_pcs.iter().collect(); v.sort(); match v.get(idx as usize) { Some(((a, b), c)) => { *pc = *a; *pr = *b; *n = **c; 1 } None => 0 } }
}

#[no_mangle]
pub extern "C" fn emu_dsp_watch(e: *mut Emu, lo: u32, hi: u32) { unsafe { let e = &mut *e; e.dsp.wlo = lo as u16; e.dsp.whi = hi as u16; e.dsp.wlog.clear(); e.dsp.rlog.clear(); } }

#[no_mangle]
pub extern "C" fn emu_dsp_watch_get(e: *mut Emu, idx: u32, pc: *mut u32, y: *mut u32, addr: *mut u32, val: *mut u32) -> u32 {
    unsafe { let e = &*e; match e.dsp.wlog.get(idx as usize) { Some(w) => { *pc = w.0 as u32; *y = w.1 as u32; *addr = w.2 as u32; *val = w.3 as u32; 1 } None => 0 } }
}

#[no_mangle]
pub extern "C" fn emu_dsp_rwatch_get(e: *mut Emu, idx: u32, pc: *mut u32, y: *mut u32, addr: *mut u32, val: *mut u32) -> u32 {
    unsafe { let e = &*e; match e.dsp.rlog.get(idx as usize) { Some(w) => { *pc = w.0 as u32; *y = w.1 as u32; *addr = w.2 as u32; *val = w.3 as u32; 1 } None => 0 } }
}

#[no_mangle]
pub extern "C" fn emu_dsp_tone(e: *mut Emu, amp: f32) { unsafe { (*e).dsp.tone_amp = amp; } }

#[no_mangle]
pub extern "C" fn emu_dsp_int2div(e: *mut Emu, n: u32) { unsafe { (*e).dsp.int2_div = ((n & 0xFFFF) as u64).max(1); (*e).dsp.i3_quad = n & 0x10000 != 0; } }

#[no_mangle]
pub extern "C" fn emu_cov_enable(e: *mut Emu, lo_phys: u32, len: usize) { unsafe { let e = &mut *e; e.cov_lo = lo_phys; e.cov = vec![0u8; len]; e.cov_on = true; } }
#[no_mangle]
pub extern "C" fn emu_cov_ptr(e: *mut Emu) -> *mut u8 { unsafe { (*e).cov.as_mut_ptr() } }
#[no_mangle]
pub extern "C" fn emu_cov_pause(e: *mut Emu, on: u32) { unsafe { (*e).cov_on = on != 0; } }
