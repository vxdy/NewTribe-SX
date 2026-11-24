//! Debug / profiler window (toggle: "Debug" button or F12) and the headless `--perf-report N` runner.

use crate::machine::{self, BootMode, Shared};
use crate::metrics::{Metrics, Sampler, MUTE_RMS_THRESHOLD};
use eframe::egui::{self, Color32, Pos2, Rect, Sense, Stroke, Vec2};
use std::sync::atomic::Ordering::Relaxed;
use std::time::{Duration, Instant};

pub struct DebugPanel {
    pub open: bool,
    sampler: Sampler,
    bench: Option<Sampler>,
    bench_result: String,
    status: String,
}

impl DebugPanel {
    pub fn new(shared: &Shared, open: bool) -> DebugPanel {
        let m = &shared.metrics;
        // PART MUTE key cell for the mute-latency measurement
        if let Ok(serde_json::Value::Object(o)) = serde_json::from_str(include_str!("../../keymap.json")) {
            if let Some((a, b)) = o.get("padnote").and_then(|v| v.as_str()).and_then(|s| s.split_once(',')) {
                if let (Ok(r), Ok(k)) = (a.trim().parse::<u32>(), b.trim().parse::<u32>()) {
                    m.mute_key.store(r << 8 | k, Relaxed);
                }
            }
        }
        m.on.store(open, Relaxed);
        DebugPanel { open, sampler: Sampler::new(m), bench: None, bench_result: String::new(), status: String::new() }
    }

    /// Call once per UI frame. `frame_ns` = time since previous frame, `snap_wait_ns` = snapshot lock wait.
    pub fn frame_stats(m: &Metrics, frame_ns: u64, snap_wait_ns: u64) {
        if !m.is_on() { return; }
        m.ui_frames.fetch_add(1, Relaxed);
        m.ui_frame_ns.fetch_add(frame_ns, Relaxed);
        m.ui_frame_max_ns.fetch_max(frame_ns, Relaxed);
        m.ui_snap_wait_ns.fetch_add(snap_wait_ns, Relaxed);
    }

    pub fn show(&mut self, ctx: &egui::Context, shared: &Shared) {
        let m = &*shared.metrics;
        if ctx.input(|i| i.key_pressed(egui::Key::F12)) {
            self.open = !self.open;
        }
        let was_on = m.is_on();
        let want_on = self.open || self.bench.is_some();
        if want_on != was_on {
            m.on.store(want_on, Relaxed);
            if want_on { self.sampler.reset(m); }
        }
        if !want_on { return; }
        if self.sampler.tick(m, 0.5) {
            // keep the benchmark in step
        }
        if let Some(b) = &mut self.bench {
            b.tick(m, 0.5);
            if b.elapsed() >= 10.0 {
                let (mn, av, mx) = b.speed_stats();
                self.bench_result = format!("Benchmark 10 s: speed factor min {:.4}  avg {:.4}  max {:.4}", mn, av, mx);
                println!("{}", self.bench_result);
                self.bench = None;
            }
        }
        ctx.request_repaint_after(Duration::from_millis(100));
        if !self.open { return; }
        let mut open = self.open;
        egui::Window::new("Debug / Profiler").open(&mut open).default_width(430.0).default_pos([20.0, 60.0]).show(ctx, |ui| {
            let cur = self.sampler.cur.clone();
            let h: Vec<crate::metrics::Sample> = self.sampler.hist.iter().cloned().collect();
            ui.horizontal(|ui| {
                if ui.button("Benchmark 10 s").clicked() && self.bench.is_none() {
                    self.bench = Some(Sampler::new(m));
                    self.bench_result = "Benchmark running ...".into();
                }
                if ui.button("Copy report").clicked() {
                    ui.ctx().copy_text(self.sampler.report(m));
                    self.status = "report copied".into();
                }
                if ui.button("Save report").clicked() {
                    let p = machine::esx_dir().join("perf_report.txt");
                    self.status = match std::fs::write(&p, self.sampler.report(m)) {
                        Ok(_) => format!("saved {}", p.display()),
                        Err(e) => format!("save failed: {e}"),
                    };
                }
                if ui.button("Reset").clicked() { self.sampler.reset(m); }
            });
            if let Some(b) = &self.bench {
                ui.label(format!("Benchmark running {:.1}/10 s", b.elapsed()));
            }
            if !self.bench_result.is_empty() { ui.label(&self.bench_result); }
            if !self.status.is_empty() { ui.small(&self.status); }
            ui.separator();
            let series = |f: &dyn Fn(&crate::metrics::Sample) -> f32| -> Vec<f32> { h.iter().map(f).collect() };
            egui::Grid::new("dbg").num_columns(3).spacing([10.0, 3.0]).show(ui, |ui| {
                let head = |ui: &mut egui::Ui, t: &str| { ui.strong(t); ui.label(""); ui.label(""); ui.end_row(); };
                head(ui, "Emulation");
                row(ui, "speed factor (SH)", format!("{:.3}x", cur.speed), &series(&|s| s.speed));
                row(ui, "speed factor (DSP frames)", format!("{:.3}x", cur.speed_dsp), &series(&|s| s.speed_dsp));
                row(ui, "SH MIPS", format!("{:.2}", cur.mips), &series(&|s| s.mips));
                row(ui, "DSP cycles/s", format!("{:.2} M", cur.dsp_cps / 1e6), &series(&|s| s.dsp_cps as f32));
                row(ui, "emu run ns / DSP cycle", format!("{:.1}", cur.dsp_ns_cycle), &series(&|s| s.dsp_ns_cycle));
                row(ui, "DSP frames/s (44100)", format!("{:.0}", cur.dsp_fps), &series(&|s| s.dsp_fps));
                head(ui, "Emu thread ms / s");
                row(ui, "run (SH+DSP)", format!("{:.0}", cur.run_ms), &series(&|s| s.run_ms));
                row(ui, "audio drain", format!("{:.1}", cur.drain_ms), &series(&|s| s.drain_ms));
                row(ui, "cmd/keys", format!("{:.1}", cur.cmd_ms), &series(&|s| s.cmd_ms));
                row(ui, "snapshot publish", format!("{:.1}", cur.publish_ms), &series(&|s| s.publish_ms));
                row(ui, "sleep/wait", format!("{:.1}", cur.sleep_ms), &series(&|s| s.sleep_ms));
                row(ui, "other/untracked", format!("{:.1}", cur.other_ms), &series(&|s| s.other_ms));
                head(ui, "UI");
                row(ui, "UI FPS", format!("{:.1}", cur.ui_fps), &series(&|s| s.ui_fps));
                row(ui, "frame time ms (max)", format!("{:.2} ({:.1})", cur.ui_frame_ms, cur.ui_frame_max_ms), &series(&|s| s.ui_frame_ms));
                row(ui, "snapshot lock wait us", format!("{:.1}", cur.ui_snap_wait_us), &series(&|s| s.ui_snap_wait_us));
                head(ui, "DSP audio output");
                row(ui, "frames/s", format!("{:.0}", cur.a_fps), &series(&|s| s.a_fps));
                row(ui, "rms / peak", format!("{:.0} / {:.0}", cur.rms, cur.peak), &series(&|s| s.rms));
                row(ui, "DC offset L/R", format!("{:.1} / {:.1}", cur.dc_l, cur.dc_r), &series(&|s| s.dc_l));
                row(ui, "clipped (|s|>=32000)", format!("{} ({:.3} %)", cur.clips, cur.clip_frac * 100.0), &series(&|s| s.clip_frac * 100.0));
                head(ui, "Audio out (cpal ring)");
                if cur.audio_active {
                    row(ui, "ring fill ms", format!("{:.0}", cur.ring_ms), &series(&|s| s.ring_ms));
                    row(ui, "pitch ratio", format!("{:.3}", cur.pitch), &series(&|s| s.pitch));
                    ui.label("underruns"); ui.label(cur.underruns.to_string()); ui.label(""); ui.end_row();
                    ui.label("stale trims"); ui.label(format!("{} ({} frames dropped)", cur.trims, cur.trimmed_frames)); ui.label(""); ui.end_row();
                } else {
                    ui.label("(turn sound on)"); ui.label(""); ui.label(""); ui.end_row();
                }
            });
            ui.separator();
            let mu = m.mute_lat_us.load(Relaxed);
            ui.label(if mu > 0 { format!("PART MUTE -> rms<{MUTE_RMS_THRESHOLD}: {:.0} ms (wall)", mu as f64 / 1000.0) }
                     else { "PART MUTE latency: press PART MUTE while a sound plays".into() });
            ui.label("Input latency, last 10 events (queued->consumed / ->LCD change ms):");
            let ev = m.events.lock().unwrap().clone();
            if ev.is_empty() { ui.small("(none yet: press a key or turn the dial)"); }
            for e in ev.iter().rev() {
                ui.small(format!("{:6.1} / {}", e.consume_ms, e.lcd_ms.map(|v| format!("{v:.1}")).unwrap_or("-".into())));
            }
        });
        self.open = open;
    }
}

fn row(ui: &mut egui::Ui, label: &str, value: String, data: &[f32]) {
    ui.label(label);
    ui.monospace(value);
    spark(ui, data);
    ui.end_row();
}

fn spark(ui: &mut egui::Ui, data: &[f32]) {
    let (rect, _) = ui.allocate_exact_size(Vec2::new(160.0, 18.0), Sense::hover());
    let p = ui.painter_at(rect);
    p.rect_filled(rect, 2.0, Color32::from_black_alpha(90));
    if data.len() < 2 { return; }
    let (mut lo, mut hi) = (f32::MAX, f32::MIN);
    for &v in data { if v.is_finite() { lo = lo.min(v); hi = hi.max(v); } }
    if lo > hi { return; }
    lo = lo.min(0.0);
    if hi - lo < 1e-9 { hi = lo + 1.0; }
    let n = 120.0f32;
    let pts: Vec<Pos2> = data.iter().enumerate().map(|(i, &v)| {
        let x = rect.right() - (data.len() - 1 - i) as f32 / n * rect.width();
        let y = rect.bottom() - 1.0 - ((v - lo) / (hi - lo)).clamp(0.0, 1.0) * (rect.height() - 2.0);
        Pos2::new(x.max(rect.left()), y)
    }).collect();
    p.add(egui::Shape::line(pts, Stroke::new(1.2, Color32::from_rgb(120, 200, 255))));
    let _ = Rect::NOTHING;
}

/// Headless run for `secs` seconds; prints the report to stdout.
pub fn perf_report(secs: f64) {
    let shared = Shared::new();
    shared.metrics.on.store(true, Relaxed);
    shared.boot(BootMode::Normal);
    let tb = Instant::now();
    while shared.metrics.instr.load(Relaxed) == 0 && tb.elapsed().as_secs() < 30 { std::thread::sleep(Duration::from_millis(20)); }
    let mut s = Sampler::new(&shared.metrics);
    let t0 = Instant::now();
    while t0.elapsed().as_secs_f64() < secs {
        std::thread::sleep(Duration::from_millis(50));
        s.tick(&shared.metrics, 0.5);
        let snap = shared.snapshot();
        if let Some(e) = snap.error { eprintln!("emu error: {e}"); break; }
        let _ = shared.take_audio();
    }
    println!("{}", s.report(&shared.metrics));
    shared.shutdown();
}
