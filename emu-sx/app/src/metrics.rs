//! Cheap performance counters shared between the emu thread, the UI and the audio callback, plus the sampler that turns
//! the cumulative counters into per-interval rates (used by the Debug panel and by `--perf-report`).
//! Heavy counters (sample statistics, Instant timing) only run while `Metrics::on` is set.

use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicI64, AtomicU32, AtomicU64, Ordering::Relaxed};
use std::sync::{Mutex, OnceLock};
use std::time::Instant;

pub fn now_ns() -> u64 {
    static T0: OnceLock<Instant> = OnceLock::new();
    T0.get_or_init(Instant::now).elapsed().as_nanos() as u64 + 1
}

/// RMS (in i16 units) below which the output counts as silent for the mute-latency measurement.
pub const MUTE_RMS_THRESHOLD: f32 = 150.0;

#[derive(Default)]
pub struct Metrics {
    pub on: AtomicBool,
    // emu thread: cumulative ns per activity
    pub run_ns: AtomicU64,     // core emu_run (SH + overlapped DSP thread)
    pub drain_ns: AtomicU64,   // audio drain + audio mutex
    pub cmd_ns: AtomicU64,     // commands / keys / encoder bookkeeping (excl. the run)
    pub publish_ns: AtomicU64, // snapshot build + snap lock wait
    pub sleep_ns: AtomicU64,   // explicit sleeping/waiting (0 while the loop never sleeps)
    pub loops: AtomicU64,
    // cumulative absolute counters (always cheap)
    pub instr: AtomicU64,
    pub dsp_frames: AtomicU64,
    pub dsp_cycles: AtomicU64,
    // DSP output statistics (frames = stereo sample pairs)
    pub a_frames: AtomicU64,
    pub a_clips: AtomicU64, // samples with |s| >= 32000
    pub a_sumsq: AtomicU64, // sum of squares over both channels
    pub a_sum_l: AtomicI64,
    pub a_sum_r: AtomicI64,
    pub a_peak: AtomicU32,     // max |s| since last sampler read
    pub a_rms_last: AtomicU32, // f32 bits, rms of the most recent drain chunk
    // UI
    pub ui_frames: AtomicU64,
    pub ui_frame_ns: AtomicU64,
    pub ui_frame_max_ns: AtomicU64,
    pub ui_snap_wait_ns: AtomicU64,
    // input latency
    pub pend_ns: AtomicU64,  // queued time of the oldest unconsumed input event (0 = none)
    pub mute_key: AtomicU32, // (row << 8) | mask of PART MUTE, 0 = unknown
    pub mute_press_ns: AtomicU64,
    pub mute_pre_rms: AtomicU32,
    pub mute_lat_us: AtomicU64, // last result, 0 = none/pending
    pub mute_done: AtomicU64,
    pub events: Mutex<VecDeque<EvRec>>,
}

#[derive(Clone, Copy, Debug)]
pub struct EvRec {
    /// queued -> consumed by the emu thread (ms)
    pub consume_ms: f32,
    /// queued -> LCD text changed (ms), None = no change within 2 s
    pub lcd_ms: Option<f32>,
}

impl Metrics {
    pub fn is_on(&self) -> bool {
        self.on.load(Relaxed)
    }
    /// Call when the UI queues a key/encoder/adc event.
    pub fn event_queued(&self) {
        if self.is_on() {
            let _ = self.pend_ns.compare_exchange(0, now_ns(), Relaxed, Relaxed);
        }
    }
    pub fn key_queued(&self, row: u8, mask: u8, down: bool) {
        if !self.is_on() {
            return;
        }
        self.event_queued();
        if down && self.mute_key.load(Relaxed) == ((row as u32) << 8 | mask as u32) {
            self.mute_pre_rms.store(self.a_rms_last.load(Relaxed), Relaxed);
            self.mute_lat_us.store(0, Relaxed);
            self.mute_press_ns.store(now_ns(), Relaxed);
        }
    }
    pub fn push_event(&self, r: EvRec) {
        let mut e = self.events.lock().unwrap();
        e.push_back(r);
        while e.len() > 10 {
            e.pop_front();
        }
    }
    /// Accumulate output statistics for one drained chunk (interleaved stereo i16) and handle mute latency.
    pub fn audio_chunk(&self, s: &[i16]) {
        if s.is_empty() {
            return;
        }
        let (mut ss, mut sl, mut sr, mut clip, mut pk) = (0u64, 0i64, 0i64, 0u64, 0u32);
        for c in s.chunks_exact(2) {
            let (l, r) = (c[0] as i32, c[1] as i32);
            ss += (l * l) as u64 + (r * r) as u64;
            sl += l as i64;
            sr += r as i64;
            let (al, ar) = (l.unsigned_abs(), r.unsigned_abs());
            clip += (al >= 32000) as u64 + (ar >= 32000) as u64;
            pk = pk.max(al).max(ar);
        }
        let n = (s.len() / 2) as u64;
        self.a_frames.fetch_add(n, Relaxed);
        self.a_clips.fetch_add(clip, Relaxed);
        self.a_sumsq.fetch_add(ss, Relaxed);
        self.a_sum_l.fetch_add(sl, Relaxed);
        self.a_sum_r.fetch_add(sr, Relaxed);
        self.a_peak.fetch_max(pk, Relaxed);
        let rms = (ss as f64 / (2 * n) as f64).sqrt() as f32;
        self.a_rms_last.store(rms.to_bits(), Relaxed);
        let mp = self.mute_press_ns.load(Relaxed);
        if mp != 0 && self.mute_lat_us.load(Relaxed) == 0 {
            let pre = f32::from_bits(self.mute_pre_rms.load(Relaxed));
            if pre < MUTE_RMS_THRESHOLD * 2.0 {
                self.mute_press_ns.store(0, Relaxed); // nothing audible to mute
            } else if rms < MUTE_RMS_THRESHOLD {
                self.mute_lat_us.store(((now_ns() - mp) / 1000).max(1), Relaxed);
                self.mute_done.fetch_add(1, Relaxed);
                self.mute_press_ns.store(0, Relaxed);
            } else if now_ns() - mp > 5_000_000_000 {
                self.mute_press_ns.store(0, Relaxed);
            }
        }
    }
}

// ------------------------------------------------------------------------------------------------ audio output stats

/// Written by the audio ring (audio.rs), read by the sampler.
#[derive(Default)]
pub struct AudioStats {
    pub active: AtomicBool,
    pub ring_frames: AtomicU32,
    pub pitch_bits: AtomicU32,
    pub underruns: AtomicU64,
    pub trims: AtomicU64,
    pub trimmed_frames: AtomicU64,
}

pub fn audio_stats() -> &'static AudioStats {
    static A: OnceLock<AudioStats> = OnceLock::new();
    A.get_or_init(AudioStats::default)
}

// ------------------------------------------------------------------------------------------------ sampler

#[derive(Clone, Debug, Default)]
pub struct Sample {
    pub t: f64,
    pub speed: f32,     // emulated s / wall s from SH instr count (96 MHz)
    pub speed_dsp: f32, // dsp frames / 44100 per wall s
    pub mips: f32,
    pub dsp_cps: f64,
    pub dsp_ns_cycle: f32, // emu-thread run wall ns per DSP cycle (upper bound: SH + DSP overlapped)
    pub dsp_fps: f32,
    pub run_ms: f32,
    pub drain_ms: f32,
    pub cmd_ms: f32,
    pub publish_ms: f32,
    pub sleep_ms: f32,
    pub other_ms: f32, // all in ms per wall second
    pub ui_fps: f32,
    pub ui_frame_ms: f32,
    pub ui_frame_max_ms: f32,
    pub ui_snap_wait_us: f32,
    pub a_fps: f32,
    pub rms: f32,
    pub peak: f32,
    pub dc_l: f32,
    pub dc_r: f32,
    pub clip_frac: f32,
    pub clips: u64,
    pub ring_ms: f32,
    pub pitch: f32,
    pub underruns: u64,
    pub trims: u64,
    pub trimmed_frames: u64,
    pub audio_active: bool,
}

#[derive(Default, Clone, Copy)]
struct Cum {
    run: u64,
    drain: u64,
    cmd: u64,
    publish: u64,
    sleep: u64,
    instr: u64,
    frames: u64,
    cycles: u64,
    af: u64,
    clips: u64,
    sumsq: u64,
    sl: i64,
    sr: i64,
    uf: u64,
    uns: u64,
    usnap: u64,
}

fn read_cum(m: &Metrics) -> Cum {
    Cum {
        run: m.run_ns.load(Relaxed),
        drain: m.drain_ns.load(Relaxed),
        cmd: m.cmd_ns.load(Relaxed),
        publish: m.publish_ns.load(Relaxed),
        sleep: m.sleep_ns.load(Relaxed),
        instr: m.instr.load(Relaxed),
        frames: m.dsp_frames.load(Relaxed),
        cycles: m.dsp_cycles.load(Relaxed),
        af: m.a_frames.load(Relaxed),
        clips: m.a_clips.load(Relaxed),
        sumsq: m.a_sumsq.load(Relaxed),
        sl: m.a_sum_l.load(Relaxed),
        sr: m.a_sum_r.load(Relaxed),
        uf: m.ui_frames.load(Relaxed),
        uns: m.ui_frame_ns.load(Relaxed),
        usnap: m.ui_snap_wait_ns.load(Relaxed),
    }
}

pub struct Sampler {
    start: Instant,
    last: Instant,
    c0: Cum,
    cl: Cum,
    pub hist: VecDeque<Sample>,
    pub cur: Sample,
    pub min_speed: f32,
    pub max_speed: f32,
    sum_speed: f64,
    n_speed: u64,
}

const HIST: usize = 120;

impl Sampler {
    pub fn new(m: &Metrics) -> Sampler {
        let c = read_cum(m);
        Sampler { start: Instant::now(), last: Instant::now(), c0: c, cl: c, hist: VecDeque::new(), cur: Sample::default(),
                  min_speed: f32::MAX, max_speed: 0.0, sum_speed: 0.0, n_speed: 0 }
    }

    pub fn reset(&mut self, m: &Metrics) {
        *self = Sampler::new(m);
    }

    pub fn elapsed(&self) -> f64 {
        self.start.elapsed().as_secs_f64()
    }

    /// Compute a new sample if at least `interval` seconds passed since the previous one.
    pub fn tick(&mut self, m: &Metrics, interval: f64) -> bool {
        let dt = self.last.elapsed().as_secs_f64();
        if dt < interval {
            return false;
        }
        let c = read_cum(m);
        let l = self.cl;
        let d = |a: u64, b: u64| a.wrapping_sub(b) as f64;
        let ms = |a: u64, b: u64| (d(a, b) / 1e6 / dt) as f32;
        let ui_n = d(c.uf, l.uf).max(1.0);
        let af = d(c.af, l.af);
        let aspl = (af * 2.0).max(1.0);
        let st = audio_stats();
        let tracked = ms(c.run, l.run) + ms(c.drain, l.drain) + ms(c.cmd, l.cmd) + ms(c.publish, l.publish) + ms(c.sleep, l.sleep);
        let s = Sample {
            t: self.start.elapsed().as_secs_f64(),
            speed: (d(c.instr, l.instr) / 96e6 / dt) as f32,
            speed_dsp: (d(c.frames, l.frames) / 44100.0 / dt) as f32,
            mips: (d(c.instr, l.instr) / 1e6 / dt) as f32,
            dsp_cps: d(c.cycles, l.cycles) / dt,
            dsp_ns_cycle: if c.cycles > l.cycles { (d(c.run, l.run) / d(c.cycles, l.cycles)) as f32 } else { 0.0 },
            dsp_fps: (d(c.frames, l.frames) / dt) as f32,
            run_ms: ms(c.run, l.run),
            drain_ms: ms(c.drain, l.drain),
            cmd_ms: ms(c.cmd, l.cmd),
            publish_ms: ms(c.publish, l.publish),
            sleep_ms: ms(c.sleep, l.sleep),
            other_ms: (1000.0 - tracked).max(0.0),
            ui_fps: (ui_n / dt) as f32,
            ui_frame_ms: (d(c.uns, l.uns) / ui_n / 1e6) as f32,
            ui_frame_max_ms: m.ui_frame_max_ns.swap(0, Relaxed) as f32 / 1e6,
            ui_snap_wait_us: (d(c.usnap, l.usnap) / ui_n / 1e3) as f32,
            a_fps: (af / dt) as f32,
            rms: (d(c.sumsq, l.sumsq) / aspl).sqrt() as f32,
            peak: m.a_peak.swap(0, Relaxed) as f32,
            dc_l: ((c.sl - l.sl) as f64 / af.max(1.0)) as f32,
            dc_r: ((c.sr - l.sr) as f64 / af.max(1.0)) as f32,
            clip_frac: (d(c.clips, l.clips) / aspl) as f32,
            clips: c.clips,
            ring_ms: st.ring_frames.load(Relaxed) as f32 / 44.1,
            pitch: f32::from_bits(st.pitch_bits.load(Relaxed)),
            underruns: st.underruns.load(Relaxed),
            trims: st.trims.load(Relaxed),
            trimmed_frames: st.trimmed_frames.load(Relaxed),
            audio_active: st.active.load(Relaxed),
        };
        if s.speed > 0.0 {
            self.min_speed = self.min_speed.min(s.speed);
            self.max_speed = self.max_speed.max(s.speed);
            self.sum_speed += s.speed as f64;
            self.n_speed += 1;
        }
        self.cur = s.clone();
        self.hist.push_back(s);
        while self.hist.len() > HIST {
            self.hist.pop_front();
        }
        self.cl = c;
        self.last = Instant::now();
        true
    }

    /// (min, avg, max) speed factor over the samples since the last reset.
    pub fn speed_stats(&self) -> (f32, f32, f32) {
        if self.n_speed == 0 {
            return (0.0, 0.0, 0.0);
        }
        (self.min_speed, (self.sum_speed / self.n_speed as f64) as f32, self.max_speed)
    }

    /// Plain-text report: averages since the sampler was created plus the latest sample.
    pub fn report(&self, m: &Metrics) -> String {
        let c = read_cum(m);
        let dt = self.start.elapsed().as_secs_f64().max(1e-6);
        let d = |a: u64, b: u64| a.wrapping_sub(b) as f64;
        let (mn, av, mx) = self.speed_stats();
        let cur = &self.cur;
        let mut o = String::new();
        let mut p = |s: String| {
            o.push_str(&s);
            o.push('\n');
        };
        p(format!("ESX-1 emulator performance report ({:.1} s window, esx-ui {})", dt, env!("CARGO_PKG_VERSION")));
        p("-- emulation".into());
        p(format!("speed factor (SH instr / 96 MHz) per 0.5 s: avg {:.4}  min {:.4}  max {:.4}  (n={})", av, mn, mx, self.n_speed));
        p(format!("speed factor overall: {:.4}   by DSP frames: {:.4}", d(c.instr, self.c0.instr) / 96e6 / dt, d(c.frames, self.c0.frames) / 44100.0 / dt));
        p(format!("SH MIPS avg: {:.2}", d(c.instr, self.c0.instr) / 1e6 / dt));
        p(format!("DSP frames/s avg: {:.0} (target 44100)   DSP cycles/s avg: {:.0}", d(c.frames, self.c0.frames) / dt, d(c.cycles, self.c0.cycles) / dt));
        p(format!("emu-thread run ns per DSP cycle avg: {:.1} (upper bound, SH+DSP overlapped)", d(c.run, self.c0.run) / d(c.cycles, self.c0.cycles).max(1.0)));
        p("-- emu thread time per wall second (ms)".into());
        let ms = |a: u64, b: u64| d(a, b) / 1e6 / dt;
        p(format!("run (SH+DSP) {:.1}  audio drain {:.1}  cmd/keys {:.1}  publish {:.1}  sleep {:.1}",
                  ms(c.run, self.c0.run), ms(c.drain, self.c0.drain), ms(c.cmd, self.c0.cmd), ms(c.publish, self.c0.publish), ms(c.sleep, self.c0.sleep)));
        p("-- UI".into());
        let un = d(c.uf, self.c0.uf).max(1.0);
        p(format!("UI frames {:.0}  fps {:.1}  avg frame {:.2} ms  snapshot lock wait avg {:.1} us", un, un / dt, d(c.uns, self.c0.uns) / un / 1e6, d(c.usnap, self.c0.usnap) / un / 1e3));
        p("-- DSP audio output".into());
        let af = d(c.af, self.c0.af);
        let aspl = (af * 2.0).max(1.0);
        p(format!("frames/s {:.0}  rms {:.0}  DC L/R {:.1}/{:.1}  clipped samples {} ({:.4} %)",
                  af / dt, (d(c.sumsq, self.c0.sumsq) / aspl).sqrt(), (c.sl - self.c0.sl) as f64 / af.max(1.0), (c.sr - self.c0.sr) as f64 / af.max(1.0),
                  c.clips - self.c0.clips, d(c.clips, self.c0.clips) / aspl * 100.0));
        p(format!("recent peak {:.0}", cur.peak));
        if cur.audio_active {
            p(format!("audio out: ring {:.0} ms  pitch {:.3}  underruns {}  stale trims {} ({} frames)", cur.ring_ms, cur.pitch, cur.underruns, cur.trims, cur.trimmed_frames));
        } else {
            p("audio out: not active".into());
        }
        let mu = m.mute_lat_us.load(Relaxed);
        p(if mu > 0 { format!("last PART MUTE -> output rms<{} latency: {:.0} ms (wall)", MUTE_RMS_THRESHOLD, mu as f64 / 1000.0) } else { "mute latency: no measurement".into() });
        p("-- last input events (queued->consumed / queued->LCD change, ms)".into());
        for e in m.events.lock().unwrap().iter() {
            p(format!("  {:.1} / {}", e.consume_ms, e.lcd_ms.map(|v| format!("{:.1}", v)).unwrap_or("-".into())));
        }
        o
    }
}
