#![allow(dead_code)]
//! Machine glue on top of the `sh3core` emulation core: HD44780 LCD, key matrix, ADC inputs, encoder, NAND setup,
//! emulation thread and audio drain. Port of rmachine.py / lcd.py / keys.py / smartmedia.py / container.py / server.py (Unit).
//!
//! Everything that talks to the core lives on one emulation thread (the core callbacks have no user data pointer, so the
//! LCD/key state sits in a thread_local that belongs to that thread).

use std::cell::RefCell;
use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};
use std::sync::{Arc, Mutex};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use crate::metrics::{self, EvRec, Metrics};
use sh3core as core;
use sh3core::Emu;

// ------------------------------------------------------------------------------------------------ public interface

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BootMode {
    Normal,
    Update,
    /// restart with the modified (Newtribe) firmware installed by make_custom.py
    Custom,
}

#[derive(Clone, Debug)]
pub struct Snapshot {
    pub lcd: [[u8; 40]; 2],
    pub cgram: [u8; 64],
    pub display_on: bool,
    pub leds: [u8; 13],
    pub pressed: Vec<(u8, u8)>,
    /// emulated seconds per wall second
    pub speed: f32,
    pub running: bool,
    pub error: Option<String>,
    pub dsp_boot: u8,
}

impl Default for Snapshot {
    fn default() -> Self {
        Snapshot { lcd: [[b' '; 40]; 2], cgram: [0; 64], display_on: false, leds: [0; 13], pressed: Vec::new(),
                   speed: 0.0, running: false, error: None, dsp_boot: 0 }
    }
}

enum Cmd {
    Adc(u8, u8, u16),
    Arp,
}

struct Inner {
    snap: Mutex<Snapshot>,
    audio: Mutex<Vec<i16>>,
    cmds: Mutex<Vec<Cmd>>,
    enc: AtomicI32,
    adc: Mutex<HashMap<(u8, u8), u16>>,
    arp: Mutex<(bool, u16)>,
    metrics: Arc<Metrics>,
}

pub struct Shared {
    /// pressed (row,mask), written by UI, read by the emulation thread
    pub keys: Arc<Mutex<HashSet<(u8, u8)>>>,
    inner: Arc<Inner>,
    /// performance counters (debug panel / --perf-report)
    pub metrics: Arc<Metrics>,
    thread: Mutex<Option<(Arc<AtomicBool>, JoinHandle<()>)>>,
}

impl Default for Shared {
    fn default() -> Self {
        Self::new()
    }
}

impl Shared {
    pub fn new() -> Shared {
        let metrics = Arc::new(Metrics::default());
        Shared {
            metrics: metrics.clone(),
            keys: Arc::new(Mutex::new(HashSet::new())),
            inner: Arc::new(Inner {
                snap: Mutex::new(Snapshot::default()),
                audio: Mutex::new(Vec::new()),
                cmds: Mutex::new(Vec::new()),
                enc: AtomicI32::new(0),
                adc: Mutex::new(HashMap::new()),
                arp: Mutex::new((false, 512)),
                metrics,
            }),
            thread: Mutex::new(None),
        }
    }

    /// 10-bit knob/slider value on A/D channel `ch` while the multiplexer column is `col`.
    pub fn set_adc(&self, col: u8, ch: u8, v: u16) {
        let v = v.min(1023);
        self.metrics.event_queued();
        self.inner.adc.lock().unwrap().insert((col, ch), v);
        self.inner.cmds.lock().unwrap().push(Cmd::Adc(col, ch, v));
    }

    pub fn set_key(&self, row: u8, mask: u8, down: bool) {
        self.metrics.key_queued(row, mask, down);
        let mut k = self.keys.lock().unwrap();
        if down { k.insert((row, mask)); } else { k.remove(&(row, mask)); }
    }

    /// VALUE dial turn, positive = clockwise (value up).
    pub fn set_encoder(&self, clicks: i32) {
        self.metrics.event_queued();
        self.inner.enc.fetch_add(clicks, Ordering::Relaxed);
    }

    /// Arp slider position (ADC col 0 / ch 2). `touched` is unused (the ribbon is ADC (2,2), see panel.rs).
    pub fn set_arp(&self, touched: bool, slider: u16) {
        self.metrics.event_queued();
        *self.inner.arp.lock().unwrap() = (touched, slider.min(1023));
        self.inner.cmds.lock().unwrap().push(Cmd::Arp);
    }

    pub fn snapshot(&self) -> Snapshot {
        self.inner.snap.lock().unwrap().clone()
    }

    /// Drained interleaved stereo i16 at 44100 Hz.
    pub fn take_audio(&self) -> Vec<i16> {
        std::mem::take(&mut *self.inner.audio.lock().unwrap())
    }

    /// (Re)start the emulation in the given mode; the previous emulation thread is stopped and its Emu freed.
    pub fn boot(&self, mode: BootMode) {
        self.shutdown();
        self.inner.audio.lock().unwrap().clear();
        self.inner.cmds.lock().unwrap().clear();
        self.inner.enc.store(0, Ordering::Relaxed);
        {
            let mut k = self.keys.lock().unwrap();
            k.clear();
            if mode == BootMode::Update {
                k.insert((8, 0x10));
                k.insert((8, 0x80));
            }
        }
        *self.inner.snap.lock().unwrap() = Snapshot { running: true, ..Snapshot::default() };
        let stop = Arc::new(AtomicBool::new(false));
        let (st, inner, keys) = (stop.clone(), self.inner.clone(), self.keys.clone());
        let h = std::thread::Builder::new().name("esx-emu".into()).stack_size(16 << 20)
            .spawn(move || emu_thread(mode, st, inner, keys)).expect("spawn emu thread");
        *self.thread.lock().unwrap() = Some((stop, h));
    }

    /// Stop the emulation thread (frees the Emu).
    pub fn shutdown(&self) {
        if let Some((stop, h)) = self.thread.lock().unwrap().take() {
            stop.store(true, Ordering::Relaxed);
            let _ = h.join();
        }
        self.inner.snap.lock().unwrap().running = false;
    }
}

impl Drop for Shared {
    fn drop(&mut self) {
        self.shutdown();
    }
}

// ------------------------------------------------------------------------------------------------ file locations

/// emu-sx directory: env ESX_DIR, else the parent of app/ (compile-time manifest dir).
pub fn esx_dir() -> PathBuf {
    if let Ok(d) = std::env::var("ESX_DIR") {
        return PathBuf::from(d);
    }
    let m = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    m.parent().map(|p| p.to_path_buf()).unwrap_or(m)
}

// ------------------------------------------------------------------------------------------------ hardware (thread local)

const PORT0: u32 = 0x0400_0000;
const PE: u32 = 0x0400_0128;
const SC: u32 = 0x0400_0136;
const PG: u32 = 0x0400_012C;
const PJ: u32 = 0x0400_0130;
const KEY_TABLE: u32 = 0x0C00_A170;
const SDRAM0: u32 = 0x0C00_0000;
const LED_PTR: u32 = 0x0C0B_3D08;
const DELAY_FN: u32 = 0x0C00_9B50;

struct Lcd {
    ddram: [u8; 80],
    cgram: [u8; 64],
    addr: u32,
    in_cgram: bool,
    bits4: bool,
    phase: u8,
    hi: u8,
    e: u8,
    inc: i32,
    shift: u8,
    display_on: bool,
    read_byte: u8,
    out_nibble: u8,
}

impl Lcd {
    fn new() -> Lcd {
        Lcd { ddram: [b' '; 80], cgram: [0; 64], addr: 0, in_cgram: false, bits4: false, phase: 0, hi: 0, e: 0, inc: 1,
              shift: 0, display_on: false, read_byte: 0, out_nibble: 0 }
    }

    fn index(addr: u32) -> Option<usize> {
        if addr < 0x28 { Some(addr as usize) } else if (0x40..0x68).contains(&addr) { Some(40 + (addr - 0x40) as usize) } else { None }
    }

    fn on_write(&mut self, sc: u8, a: u32, val: u32) {
        if a != PE { return; }
        let e = ((val >> 2) & 1) as u8;
        let old = std::mem::replace(&mut self.e, e);
        let (rs, rw, nib) = (sc & 0x20 != 0, sc & 0x40 != 0, sc & 0x0F);
        if e != 0 && old == 0 && rw {
            self.read_rising(rs);
        } else if old != 0 && e == 0 && !rw {
            self.write_falling(rs, nib);
        } else if old != 0 && e == 0 && rw {
            self.read_falling(rs);
        }
    }

    fn read_sc(&self, sc: u8) -> Option<u32> {
        let rw = sc & 0x40 != 0;
        if self.e != 0 && rw { Some(((sc & 0xF0) | self.out_nibble) as u32) } else { None }
    }

    fn write_falling(&mut self, rs: bool, nib: u8) {
        if !self.bits4 {
            let byte = nib << 4;
            if !rs && byte == 0x20 {
                self.bits4 = true;
                self.phase = 0;
            } else if !rs {
                self.exec(byte);
            }
            return;
        }
        if self.phase == 0 {
            self.hi = nib;
            self.phase = 1;
        } else {
            self.phase = 0;
            let b = self.hi << 4 | nib;
            if rs { self.data(b) } else { self.exec(b) }
        }
    }

    fn exec(&mut self, c: u8) {
        if c == 0x01 {
            self.ddram = [b' '; 80];
            self.addr = 0;
            self.in_cgram = false;
        } else if c & 0xFE == 0x02 {
            self.addr = 0;
            self.in_cgram = false;
        } else if c & 0xFC == 0x04 {
            self.inc = if c & 2 != 0 { 1 } else { -1 };
            self.shift = c & 1;
        } else if c & 0xF8 == 0x08 {
            self.display_on = c & 4 != 0;
        } else if c & 0xE0 == 0x20 {
        } else if c & 0xC0 == 0x40 {
            self.in_cgram = true;
            self.addr = (c & 0x3F) as u32;
        } else if c & 0x80 != 0 {
            self.in_cgram = false;
            self.addr = (c & 0x7F) as u32;
        }
    }

    fn step(&self, a: u32, m: u32) -> u32 {
        (a as i32 + self.inc) as u32 & m
    }

    fn data(&mut self, d: u8) {
        if self.in_cgram {
            self.cgram[(self.addr & 0x3F) as usize] = d;
            self.addr = self.step(self.addr, 0x3F);
        } else {
            if let Some(i) = Self::index(self.addr) { self.ddram[i] = d; }
            self.addr = self.step(self.addr, 0x7F);
        }
    }

    fn read_rising(&mut self, rs: bool) {
        if self.phase == 0 {
            if rs {
                self.read_byte = if self.in_cgram {
                    self.cgram[(self.addr & 0x3F) as usize]
                } else {
                    Self::index(self.addr).map(|i| self.ddram[i]).unwrap_or(0)
                };
            } else {
                self.read_byte = (self.addr & 0x7F) as u8;
            }
            self.out_nibble = self.read_byte >> 4;
        } else {
            self.out_nibble = self.read_byte & 15;
        }
    }

    fn read_falling(&mut self, rs: bool) {
        if self.phase == 0 {
            self.phase = 1;
        } else {
            self.phase = 0;
            if rs { self.addr = self.step(self.addr, 0x7F); }
        }
    }
}

struct Hw {
    lcd: Lcd,
    ports: *const u8,
    sdram: *const u8,
    sdram_len: usize,
    /// pressed (row, mask) including the fixed key (6,1)
    keys: Vec<(u8, u8)>,
}

impl Hw {
    fn port(&self, addr: u32) -> u8 {
        unsafe { *self.ports.add((addr - PORT0) as usize) }
    }
    fn sdram8(&self, addr: u32) -> u8 {
        let o = (addr & 0x1FFF_FFFF).wrapping_sub(SDRAM0) as usize;
        if o < self.sdram_len { unsafe { *self.sdram.add(o) } } else { 0 }
    }
    fn read_pg(&self) -> u32 {
        let sel = (self.port(PJ) >> 4) & 0x0F;
        let mut v = 0xFFu8;
        for &(row, mask) in &self.keys {
            if self.sdram8(KEY_TABLE + row as u32) & 0x0F == sel { v &= !mask; }
        }
        v as u32
    }
}

thread_local! {
    static HW: RefCell<Option<Hw>> = const { RefCell::new(None) };
}

extern "C" fn on_read(addr: u32, _size: u32) -> i64 {
    HW.with(|h| {
        let h = h.borrow();
        let Some(h) = h.as_ref() else { return -1 };
        match addr {
            SC => h.lcd.read_sc(h.port(SC)).map(|v| v as i64).unwrap_or(-1),
            PG => h.read_pg() as i64,
            _ => -1,
        }
    })
}

extern "C" fn on_write(addr: u32, _size: u32, val: u32) {
    HW.with(|h| {
        if let Some(h) = h.borrow_mut().as_mut() {
            let sc = h.port(SC);
            h.lcd.on_write(sc, addr, val);
        }
    })
}

// ------------------------------------------------------------------------------------------------ machine wrapper

struct Machine {
    h: *mut Emu,
    patched: bool,
    instr: u64,
    enc: EncInj,
    /// cumulative wall ns spent inside core::emu_run
    run_ns: u64,
}

const ENC_UP: [u32; 4] = [0, 2, 3, 1];
const ENC_DOWN: [u32; 4] = [0, 1, 3, 2];

/// Time-based (emulated time) encoder injection: every quadrature phase is held until the firmware's scan routine has read
/// port H `ENC_HOLD_READS` times (about 1 ms emulated per read), so clicks neither pile up nor get lost.
const ENC_HOLD_READS: u64 = 2;
const ENC_PH_REG: u32 = 0x12E;
const ENC_PHASE_TIMEOUT: u64 = 600_000;

#[derive(Default)]
struct EncInj {
    pending: i32,
    active: bool,
    up: bool,
    idx: usize,
    base_reads: u64,
    phase_instr: u64,
}

impl Machine {
    /// Queue `add` clicks, advance the quadrature state machine; returns the instruction slice to run next.
    fn enc_tick(&mut self, add: i32) -> u64 {
        self.enc.pending += add;
        if !self.enc.active && self.enc.pending == 0 { return 200_000; }
        let reads = core::emu_reg_count(self.h, 0, ENC_PH_REG);
        loop {
            if !self.enc.active {
                if self.enc.pending == 0 { self.ph56(0); return 200_000; }
                self.enc.up = self.enc.pending > 0;
                self.enc.idx = 0;
                self.enc.active = true;
            } else if reads - self.enc.base_reads >= ENC_HOLD_READS || self.instr - self.enc.phase_instr >= ENC_PHASE_TIMEOUT {
                self.enc.idx += 1;
                if self.enc.idx == 4 {
                    self.enc.pending -= if self.enc.up { 1 } else { -1 };
                    self.enc.active = false;
                    continue;
                }
            } else { return 25_000; }
            let seq = if self.enc.up { ENC_UP } else { ENC_DOWN };
            self.ph56(seq[self.enc.idx]);
            self.enc.base_reads = reads;
            self.enc.phase_instr = self.instr;
            return 25_000;
        }
    }

    fn new(flash: &[u8], card_present: bool) -> Machine {
        let h = core::emu_new(flash.as_ptr(), flash.len(), 32);
        let ports = core::emu_ports_ptr(h) as *const u8;
        let sdram = core::emu_sdram_ptr(h) as *const u8;
        let sdram_len = core::emu_sdram_len(h);
        HW.with(|c| *c.borrow_mut() = Some(Hw { lcd: Lcd::new(), ports, sdram, sdram_len, keys: vec![(6, 1)] }));
        core::emu_set_threaded(h, 1); // DSP interpreter on its own thread, in lock step with the SH
        core::emu_set_callbacks(h, Some(on_read), Some(on_write));
        core::emu_hook(h, PE, PE + 1, 0, 1);
        core::emu_hook(h, SC, SC + 1, 1, 1);
        core::emu_hook(h, PG, PG + 1, 1, 0);
        core::emu_force_read(h, 0x0400_012A, 0xFF, 0x0C); // NAND ready lines
        core::emu_force_read(h, 0x0400_012E, 0x70, 0x00); // PH4 = 0, encoder idle
        core::emu_force_read(h, 0x0400_0134, 0x8C, if card_present { 0x80 } else { 0x00 });
        core::emu_irq_period(h, 3, 50.0 * 2177.0); // one IRQ3 per 50-frame DSP block (108,850 instr at ratio 1.0)
        Machine { h, patched: false, instr: 0, enc: EncInj::default(), run_ns: 0 }
    }

    fn read16(&self, a: u32) -> u16 {
        HW.with(|c| {
            let c = c.borrow();
            let h = c.as_ref().unwrap();
            (h.sdram8(a) as u16) << 8 | h.sdram8(a + 1) as u16
        })
    }

    fn run(&mut self, n: u64) -> u64 {
        if !self.patched && self.read16(DELAY_FN) == 0x7FFC {
            core::emu_write16(self.h, DELAY_FN, 0x000B);
            core::emu_write16(self.h, DELAY_FN + 2, 0x0009);
            self.patched = true;
        }
        let t = Instant::now();
        let r = core::emu_run(self.h, n);
        self.run_ns += t.elapsed().as_nanos() as u64;
        self.instr += r;
        r
    }

    fn set_keys(&self, keys: &HashSet<(u8, u8)>) {
        HW.with(|c| {
            if let Some(h) = c.borrow_mut().as_mut() {
                h.keys = keys.iter().copied().collect();
                h.keys.push((6, 1));
            }
        });
    }

    fn ph56(&self, v: u32) {
        core::emu_force_read(self.h, 0x0400_012E, 0x70, (v << 5) & 0x60);
    }

    fn apply_arp(&self, arp: (bool, u16)) {
        // slider = mux col 0 / ch 2 (the ribbon controller is ADC (2,2), driven separately via set_adc by the panel)
        core::emu_set_adc_in(self.h, 0, 2, arp.1 as u32);
    }

    fn leds(&self) -> [u8; 13] {
        let mut out = [0u8; 13];
        let p = core::emu_read32(self.h, LED_PTR);
        if (SDRAM0..0x0E00_0000).contains(&p) {
            HW.with(|c| {
                let c = c.borrow();
                let h = c.as_ref().unwrap();
                for (i, o) in out.iter_mut().enumerate() { *o = h.sdram8(p + i as u32); }
            });
        }
        out
    }
}

impl Drop for Machine {
    fn drop(&mut self) {
        core::emu_set_callbacks(self.h, None, None);
        core::emu_free(self.h);
        HW.with(|c| *c.borrow_mut() = None);
    }
}

// ------------------------------------------------------------------------------------------------ boot images

fn read(p: PathBuf) -> Result<Vec<u8>, String> {
    std::fs::read(&p).map_err(|e| format!("{}: {}", p.display(), e))
}

fn load_machine(mode: BootMode) -> Result<Machine, String> {
    let dir = esx_dir();
    match mode {
        BootMode::Normal => {
            let flash = read(dir.join("out_flash.bin"))?;
            let fac = dir.join("out_nand_factory.bin");
            let nand = if fac.exists() { read(fac)? } else { read(dir.join("out_nand.bin"))? };
            let m = Machine::new(&flash, false);
            set_nand(m.h, 1, Some(&nand), 0x98, 0x75);
            Ok(m)
        }
        BootMode::Custom => {
            let (f, n) = (dir.join("custom_flash.bin"), dir.join("custom_nand.bin"));
            if !f.exists() || !n.exists() { return Err("custom_flash.bin/custom_nand.bin fehlen - erst `python make_custom.py` ausführen".into()); }
            let (flash, nand) = (read(f)?, read(n)?);
            let m = Machine::new(&flash, false);
            set_nand(m.h, 1, Some(&nand), 0x98, 0x75);
            Ok(m)
        }
        BootMode::Update => {
            let fw = dir.parent().map(|p| p.join("factory-firmware-sm")).unwrap_or_default();
            let bfs = read(fw.join("ESX0101F.BFS"))?;
            let flash = container_payload(&bfs).to_vec();
            let card = load_card(&dir, &fw)?;
            let m = Machine::new(&flash, true);
            set_nand(m.h, 0, Some(&card), 0xEC, 0x73);
            set_nand(m.h, 1, Some(&smartmedia::formatted_blank(32)), 0x98, 0x75);
            Ok(m)
        }
    }
}

fn set_nand(h: *mut Emu, idx: u32, data: Option<&[u8]>, maker: u32, dev: u32) {
    match data {
        Some(d) => core::emu_nand_set(h, idx, d.as_ptr(), d.len(), maker, dev),
        None => core::emu_nand_set(h, idx, std::ptr::null(), 0, 0, 0),
    }
}

/// container.payload: everything after the 0x20 byte KORG header.
pub fn container_payload(data: &[u8]) -> &[u8] {
    if data.len() > 0x20 { &data[0x20..] } else { &[] }
}

fn load_card(dir: &std::path::Path, fw: &std::path::Path) -> Result<Vec<u8>, String> {
    let cache = dir.join("card.cache");
    if cache.exists() {
        return read(cache);
    }
    let mut files = Vec::new();
    for n in ["ESX0101F.BFS", "ESX0102N.BSS", "ESX0102D.BDS"] {
        files.push((n.to_string(), read(fw.join(n))?));
    }
    let data = smartmedia::build_card(&files, 16);
    let _ = std::fs::write(&cache, &data);
    Ok(data)
}

// ------------------------------------------------------------------------------------------------ emulation thread

/// FNV hash of the LCD DDRAM text (input->LCD latency measurement).
fn lcd_hash() -> u64 {
    HW.with(|c| {
        let c = c.borrow();
        let mut h = 0xcbf2_9ce4_8422_2325u64;
        if let Some(hw) = c.as_ref() {
            for &b in &hw.lcd.ddram { h = (h ^ b as u64).wrapping_mul(0x100_0000_01b3); }
        }
        h
    })
}

fn emu_thread(mode: BootMode, stop: Arc<AtomicBool>, inner: Arc<Inner>, keys: Arc<Mutex<HashSet<(u8, u8)>>>) {
    let mut m = match load_machine(mode) {
        Ok(m) => m,
        Err(e) => {
            let mut s = inner.snap.lock().unwrap();
            s.error = Some(e);
            s.running = false;
            return;
        }
    };
    // restore remembered analog inputs
    for (&(c, ch), &v) in inner.adc.lock().unwrap().iter() {
        core::emu_set_adc_in(m.h, c as u32, ch as u32, v as u32);
    }
    m.apply_arp(*inner.arp.lock().unwrap());

    let t0 = Instant::now();
    let (mut sp_t, mut sp_i) = (t0, 0u64);
    let mut speed = 0.0f32;
    let mut last_pub = Instant::now() - Duration::from_secs(1);
    let mut abuf = vec![0i16; 1 << 16];
    let mx = inner.metrics.clone();
    let (mut cmd_acc, mut drain_acc, mut pub_acc) = (0u64, 0u64, 0u64);
    // input latency watch: (queued ns, consumed ns, lcd hash at consume time)
    let mut watch: Option<(u64, u64, u64)> = None;
    while !stop.load(Ordering::Relaxed) {
        let t_cmd = Instant::now();
        if mx.is_on() {
            let p = mx.pend_ns.swap(0, Ordering::Relaxed);
            if p != 0 {
                let now_n = metrics::now_ns();
                if watch.is_none() { watch = Some((p, now_n, lcd_hash())); }
            }
        }
        // pending commands
        let cmds = std::mem::take(&mut *inner.cmds.lock().unwrap());
        for c in cmds {
            match c {
                Cmd::Adc(col, ch, v) => core::emu_set_adc_in(m.h, col as u32, ch as u32, v as u32),
                Cmd::Arp => m.apply_arp(*inner.arp.lock().unwrap()),
            }
        }
        let ks = keys.lock().unwrap().clone();
        m.set_keys(&ks);
        let clicks = inner.enc.swap(0, Ordering::Relaxed);
        cmd_acc += t_cmd.elapsed().as_nanos() as u64;
        let slice = m.enc_tick(clicks);
        m.run(slice);
        let now = Instant::now();
        let dt = now.duration_since(sp_t).as_secs_f64();
        if dt >= 1.0 {
            speed = ((m.instr - sp_i) as f64 / 96e6 / dt) as f32;
            sp_t = now;
            sp_i = m.instr;
        }
        // audio drain
        let t_drain = Instant::now();
        let mut got_all = Vec::new();
        loop {
            let n = core::emu_dsp_audio(m.h, 0, abuf.as_mut_ptr(), abuf.len());
            got_all.extend_from_slice(&abuf[..n]);
            if n < abuf.len() { break; }
        }
        if mx.is_on() { mx.audio_chunk(&got_all); }
        if !got_all.is_empty() {
            let mut a = inner.audio.lock().unwrap();
            a.extend_from_slice(&got_all);
            if a.len() > 176_400 {
                let cut = a.len() - 176_400;
                a.drain(..cut);
            }
        }
        drain_acc += t_drain.elapsed().as_nanos() as u64;
        if now.duration_since(last_pub) >= Duration::from_millis(16) {
            last_pub = now;
            let t_pub = Instant::now();
            let mut s = Snapshot { speed, running: true, ..Snapshot::default() };
            HW.with(|c| {
                let c = c.borrow();
                let h = c.as_ref().unwrap();
                s.lcd[0].copy_from_slice(&h.lcd.ddram[..40]);
                s.lcd[1].copy_from_slice(&h.lcd.ddram[40..]);
                s.cgram = h.lcd.cgram;
                s.display_on = h.lcd.display_on;
            });
            s.leds = m.leds();
            s.dsp_boot = core::emu_dsp_word(m.h, 2) as u8;
            let mut p: Vec<(u8, u8)> = ks.iter().copied().collect();
            p.sort();
            s.pressed = p;
            *inner.snap.lock().unwrap() = s;
            pub_acc += t_pub.elapsed().as_nanos() as u64;
            mx.run_ns.store(m.run_ns, Ordering::Relaxed);
            mx.cmd_ns.store(cmd_acc, Ordering::Relaxed);
            mx.drain_ns.store(drain_acc, Ordering::Relaxed);
            mx.publish_ns.store(pub_acc, Ordering::Relaxed);
            mx.instr.store(m.instr, Ordering::Relaxed);
            mx.dsp_frames.store(core::emu_dsp_word(m.h, 32), Ordering::Relaxed);
            mx.dsp_cycles.store(core::emu_dsp_word(m.h, 1), Ordering::Relaxed);
            mx.loops.fetch_add(1, Ordering::Relaxed);
            if let Some((q, c, h0)) = watch {
                let nn = metrics::now_ns();
                if lcd_hash() != h0 {
                    mx.push_event(EvRec { consume_ms: (c - q) as f32 / 1e6, lcd_ms: Some((nn - q) as f32 / 1e6) });
                    watch = None;
                } else if nn - q > 2_000_000_000 {
                    mx.push_event(EvRec { consume_ms: (c - q) as f32 / 1e6, lcd_ms: None });
                    watch = None;
                }
            }
        }
    }
    inner.snap.lock().unwrap().running = false;
    // Machine::drop frees the Emu
}


// ------------------------------------------------------------------------------------------------ headless bench / regression

/// Run `total` instructions from boot without UI; returns (instructions, seconds, hash of LCD + registers + audio + SDRAM).
pub fn headless_run(total: u64) -> (u64, f64, u64, String) {
    let mut m = load_machine(BootMode::Normal).expect("load");
    if std::env::var("ESX_UNTHREADED").is_ok() { core::emu_set_threaded(m.h, 0); }
    let mut hash = 0xcbf29ce484222325u64;
    let mut mix = |b: &[u8]| { for &x in b { hash ^= x as u64; hash = hash.wrapping_mul(0x100000001b3); } };
    let mut abuf = vec![0i16; 1 << 16];
    let t = Instant::now();
    let mut done = 0u64;
    let mut last_t = 0.0f64;
    while done < total {
        let n = m.run(100_000.min(total - done));
        done += n;
        if done >= 300_000_000 && n > 0 && done - n < 300_000_000 && std::env::var("ESX_DSP0").is_ok() { core::emu_dsp_config(m.h, 0.0, 2177, 0); }
        if done / 100_000_000 != (done - n) / 100_000_000 {
            let now = t.elapsed().as_secs_f64();
            eprintln!("  {}M: {:.1} MIPS (last 100M)", done / 1_000_000, 100.0 / (now - last_t));
            last_t = now;
        }
        loop {
            let k = core::emu_dsp_audio(m.h, 0, abuf.as_mut_ptr(), abuf.len());
            for v in &abuf[..k] { mix(&v.to_le_bytes()); }
            if k < abuf.len() { break; }
        }
    }
    let dt = t.elapsed().as_secs_f64();
    if let Ok(v) = std::env::var("ESX_ENC") {
        let n: i32 = v.parse().unwrap();
        let show = |m: &Machine| HW.with(|c| { let c = c.borrow(); let h = c.as_ref().unwrap(); String::from_utf8_lossy(&h.lcd.ddram).into_owned() });
        eprintln!("  before: {:?}", show(&m));
        let (i0, t0) = (m.instr, Instant::now());
        let mut add = n;
        loop {
            let sl = m.enc_tick(add);
            add = 0;
            if m.enc.pending == 0 && !m.enc.active { break; }
            m.run(sl);
        }
        let (i1, t1) = (m.instr, t0.elapsed());
        m.run(3_000_000);
        eprintln!("  injected {} clicks: {} instr = {:.0} ms emulated, {:.0} ms wall (+3M settle)", n, i1 - i0, (i1 - i0) as f64 / 96e3, t1.as_secs_f64() * 1e3);
        eprintln!("  after:  {:?}", show(&m));
    }
    if std::env::var("ESX_SCAN").is_ok() {
        for idx in [0x12Eu32, 0x12A, 0x12C, 0x130, 0x128] {
            let a = core::emu_reg_count(m.h, 0, idx);
            m.run(10_000_000);
            let b = core::emu_reg_count(m.h, 0, idx);
            eprintln!("  port {:03x}: {} reads / 10M instr, last pc {:08x}", idx, b - a, core::emu_reg_read_pc(m.h, idx));
        }
    }
    if std::env::var("ESX_PROF").is_ok() {
        let mut h: HashMap<u32, u32> = HashMap::new();
        for i in 0..150_000u64 { m.run(1009 + (i % 7)); *h.entry((core::emu_get(m.h, 16) as u32) & !7).or_insert(0) += 1; }
        let mut v: Vec<_> = h.into_iter().collect();
        v.sort_by(|a, b| b.1.cmp(&a.1));
        for (pc, c) in v.iter().take(40) { eprintln!("  pc {:08x} {:5.2}%", pc, *c as f64 / 1500.0); }
    }
    let mut lcd = String::new();
    HW.with(|c| { let c = c.borrow(); let h = c.as_ref().unwrap(); mix(&h.lcd.ddram); mix(&h.lcd.cgram); lcd = String::from_utf8_lossy(&h.lcd.ddram).into_owned(); });
    for i in 0..41 { mix(&core::emu_get(m.h, i).to_le_bytes()); }
    let sd = unsafe { std::slice::from_raw_parts(core::emu_sdram_ptr(m.h), core::emu_sdram_len(m.h)) };
    mix(sd);
    (done, dt, hash, lcd)
}

// ------------------------------------------------------------------------------------------------ smartmedia.py

pub mod smartmedia {
    const PAGE: usize = 512;
    const SPARE: usize = 16;
    const PPB: usize = 32;

    fn cis() -> Vec<u8> {
        let s = ["0103d901ff1802df0120040000000021020401220201012203020407",
                 "1a050103000 20f1b08c0c0a10155080020",
                 "1b0ac1419901556 4f0ffff20",
                 "1b0c8241 18ea61f00107f60301ee",
                 "1b0c8341 18ea61700107f60301ee",
                 "15140500202020202020002020202020200000ff1400ff00"].concat().replace(' ', "");
        (0..s.len() / 2).map(|i| u8::from_str_radix(&s[2 * i..2 * i + 2], 16).unwrap()).collect()
    }

    fn lba_field(lba: u32) -> u16 {
        let mut v = 0x1000 | (lba << 1);
        if v.count_ones() % 2 == 1 { v |= 1; }
        v as u16
    }

    fn col_pairs(k: u32) -> u32 {
        (0..3).map(|n| (if (k >> n) & 1 != 0 { 2u32 } else { 1 }) << (2 + 2 * n)).sum()
    }

    pub fn ecc256(chunk: &[u8]) -> [u8; 3] {
        let (mut lp, mut cp) = (0u32, 0u32);
        for (i, &v) in chunk.iter().enumerate() {
            let mut cb = 0u32;
            for k in 0..8 { if (v >> k) & 1 != 0 { cb ^= col_pairs(k); } }
            cp ^= cb;
            if v.count_ones() & 1 == 1 {
                let mut l = 0u32;
                for j in 0..8 { l |= (if (i >> j) & 1 != 0 { 2u32 } else { 1 }) << (2 * j); }
                lp ^= l;
            }
        }
        [!(lp >> 8) as u8, !lp as u8, !cp as u8]
    }

    fn spare_ecc(chunk: &[u8]) -> [u8; 3] {
        let e = ecc256(chunk);
        [e[1], e[0], e[2]]
    }

    fn fat12_volume(files: &[(String, Vec<u8>)], total_sectors: usize) -> Vec<u8> {
        let spc = 16usize;
        let (reserved, nfats, root_entries) = (1usize, 2usize, 512usize);
        let root_sectors = root_entries * 32 / 512;
        let clusters_guess = total_sectors / spc;
        let fat_sectors = (clusters_guess * 3 / 2 + 511) / 512 + 1;
        let data_start = reserved + nfats * fat_sectors + root_sectors;
        let clusters = (total_sectors - data_start) / spc;
        assert!(clusters < 4085, "not FAT12");
        let mut vol = vec![0u8; total_sectors * 512];
        let mut b = Vec::new();
        b.extend_from_slice(&[0xEB, 0x3C, 0x90]);
        b.extend_from_slice(b"MSDOS5.0");
        b.extend_from_slice(&512u16.to_le_bytes());
        b.push(spc as u8);
        b.extend_from_slice(&(reserved as u16).to_le_bytes());
        b.push(nfats as u8);
        b.extend_from_slice(&(root_entries as u16).to_le_bytes());
        b.extend_from_slice(&0u16.to_le_bytes());
        b.push(0xF8);
        b.extend_from_slice(&(fat_sectors as u16).to_le_bytes());
        b.extend_from_slice(&16u16.to_le_bytes());
        b.extend_from_slice(&4u16.to_le_bytes());
        b.extend_from_slice(&16u32.to_le_bytes());
        b.extend_from_slice(&(total_sectors as u32).to_le_bytes());
        b.extend_from_slice(&[0x80, 0, 0x29]);
        b.extend_from_slice(&0x1234_5678u32.to_le_bytes());
        b.extend_from_slice(b"NO NAME    ");
        b.extend_from_slice(b"FAT12   ");
        vol[..b.len()].copy_from_slice(&b);
        vol[510] = 0x55;
        vol[511] = 0xAA;
        let mut entries = vec![0u32; clusters + 4];
        entries[0] = 0xFF8;
        entries[1] = 0xFFF;
        let mut root = vec![0u8; root_sectors * 512];
        let mut nxt = 2usize;
        let mut data: Vec<(usize, &Vec<u8>)> = Vec::new();
        for (idx, (name, content)) in files.iter().enumerate() {
            let (base, ext) = name.split_once('.').unwrap_or((name, ""));
            let n = ((content.len() + spc * 512 - 1) / (spc * 512)).max(1);
            let first = nxt;
            for c in 0..n {
                entries[first + c] = if c < n - 1 { (first + c + 1) as u32 } else { 0xFFF };
            }
            nxt += n;
            let mut e = Vec::new();
            e.extend_from_slice(format!("{:<8}", base.to_uppercase()).as_bytes());
            e.extend_from_slice(format!("{:<3}", ext.to_uppercase()).as_bytes());
            e.push(0x20);
            e.extend_from_slice(&[0u8; 10]);
            e.extend_from_slice(&0u16.to_le_bytes());
            e.extend_from_slice(&0x2021u16.to_le_bytes());
            e.extend_from_slice(&(first as u16).to_le_bytes());
            e.extend_from_slice(&(content.len() as u32).to_le_bytes());
            root[idx * 32..(idx + 1) * 32].copy_from_slice(&e);
            data.push((first, content));
        }
        let mut fat = vec![0u8; fat_sectors * 512];
        let mut i = 0;
        while i + 1 < entries.len() {
            let v = entries[i] | (entries[i + 1] << 12);
            let o = i * 3 / 2;
            if o + 2 < fat.len() {
                fat[o] = v as u8;
                fat[o + 1] = (v >> 8) as u8;
                fat[o + 2] = (v >> 16) as u8;
            }
            i += 2;
        }
        for f in 0..2 {
            let o = (reserved + f * fat_sectors) * 512;
            vol[o..o + fat.len()].copy_from_slice(&fat);
        }
        let ro = (reserved + nfats * fat_sectors) * 512;
        vol[ro..ro + root.len()].copy_from_slice(&root);
        for (first, content) in data {
            let o = (data_start + (first - 2) * spc) * 512;
            vol[o..o + content.len()].copy_from_slice(content);
        }
        vol
    }

    pub fn build_card(files: &[(String, Vec<u8>)], size_mb: usize) -> Vec<u8> {
        let blocks = size_mb * 1024 * 1024 / (PAGE * PPB);
        let zones = blocks / 1024;
        let logical_blocks = 1000usize;
        let total = zones * logical_blocks * PPB;
        let fatvol = fat12_volume(files, total - 16);
        let mut mbr = vec![0u8; 512];
        let mut entry = vec![0x80, 0x01, 0x01, 0x00, 0x01, 0x03, 0xF0, 0xF3];
        entry.extend_from_slice(&16u32.to_le_bytes());
        entry.extend_from_slice(&((total - 16) as u32).to_le_bytes());
        mbr[0x1BE..0x1BE + 16].copy_from_slice(&entry);
        mbr[510] = 0x55;
        mbr[511] = 0xAA;
        let mut sectors = mbr;
        sectors.extend(vec![0u8; 15 * 512]);
        sectors.extend_from_slice(&fatvol);
        sectors.resize(total * 512, 0);
        let mut pages = vec![0xFFu8; blocks * PPB * (PAGE + SPARE)];
        let mut put = |page_no: usize, data: &[u8], spare: &[u8]| {
            let o = page_no * (PAGE + SPARE);
            pages[o..o + PAGE].copy_from_slice(data);
            pages[o + PAGE..o + PAGE + SPARE].copy_from_slice(spare);
        };
        let mut c = cis();
        c.resize(PAGE, 0);
        let mut sp = vec![0xFF; 6];
        sp.extend_from_slice(&[0, 0]);
        sp.extend_from_slice(&spare_ecc(&c[256..]));
        sp.extend_from_slice(&[0, 0]);
        sp.extend_from_slice(&spare_ecc(&c[..256]));
        put(0, &c, &sp);
        for z in 0..zones {
            for lb in 0..logical_blocks {
                let phys = z * 1024 + lb + if z == 0 { 1 } else { 0 };
                let ba = lba_field(lb as u32).to_be_bytes();
                for p in 0..PPB {
                    let sidx = (z * logical_blocks + lb) * PPB + p;
                    let data = &sectors[sidx * 512..(sidx + 1) * 512];
                    let mut sp = vec![0xFF; 6];
                    sp.extend_from_slice(&ba);
                    sp.extend_from_slice(&spare_ecc(&data[256..]));
                    sp.extend_from_slice(&ba);
                    sp.extend_from_slice(&spare_ecc(&data[..256]));
                    put(phys * PPB + p, data, &sp);
                }
            }
        }
        pages
    }

    pub fn formatted_blank(size_mb: usize) -> Vec<u8> {
        let blocks = size_mb * 1024 * 1024 / (PAGE * PPB);
        let mut pages = vec![0xFFu8; blocks * PPB * (PAGE + SPARE)];
        let mut c = cis();
        c.resize(PAGE, 0);
        let mut sp = vec![0xFF; 6];
        sp.extend_from_slice(&[0, 0]);
        sp.extend_from_slice(&spare_ecc(&c[256..]));
        sp.extend_from_slice(&[0, 0]);
        sp.extend_from_slice(&spare_ecc(&c[..256]));
        pages[..PAGE].copy_from_slice(&c);
        pages[PAGE..PAGE + SPARE].copy_from_slice(&sp);
        pages
    }
}
