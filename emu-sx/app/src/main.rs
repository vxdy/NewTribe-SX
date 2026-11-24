#![allow(dead_code)]
mod audio;
mod debug;
mod machine;
mod metrics;
mod panel;

use eframe::egui;
use std::sync::Arc;

use machine::{BootMode, Shared};

struct Ctl(Arc<Shared>);

impl panel::Control for Ctl {
    fn key(&self, row: u8, mask: u8, down: bool) { self.0.set_key(row, mask, down); }
    fn adc(&self, col: u8, ch: u8, v: u16) { self.0.set_adc(col, ch, v); }
    fn encoder(&self, clicks: i32) { self.0.set_encoder(clicks); }
    fn arp(&self, touched: bool, slider: u16) { self.0.set_arp(touched, slider); }
}

struct App {
    t0: std::time::Instant,
    shot: Option<String>,
    shot_slot: Arc<std::sync::Mutex<Option<Arc<egui::ColorImage>>>>,
    shot_req: bool,
    shared: Arc<Shared>,
    ctl: Ctl,
    state: panel::PanelState,
    audio: Option<audio::AudioOut>,
    sound: bool,
    audio_err: Option<String>,
    dbg: debug::DebugPanel,
    last_frame: std::time::Instant,
}

impl App {
    fn new() -> App {
        let shared = Arc::new(Shared::new());
        shared.boot(BootMode::Normal);
        let dbg = debug::DebugPanel::new(&shared, std::env::args().any(|a| a == "--debug"));
        App { t0: std::time::Instant::now(), shot: std::env::args().skip_while(|a| a != "--shot").nth(1), shot_slot: Default::default(), shot_req: false, ctl: Ctl(shared.clone()), shared, state: panel::PanelState::default(), audio: None, sound: false, audio_err: None, dbg, last_frame: std::time::Instant::now() }
    }
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        let frame_ns = self.last_frame.elapsed().as_nanos() as u64;
        self.last_frame = std::time::Instant::now();
        let t_snap = std::time::Instant::now();
        let snap = self.shared.snapshot();
        debug::DebugPanel::frame_stats(&self.shared.metrics, frame_ns, t_snap.elapsed().as_nanos() as u64);
        let samples = self.shared.take_audio();
        if let Some(a) = &self.audio {
            if self.sound { a.push(&samples, snap.speed); }
        }
        {
            ui.horizontal(|ui| {
                if ui.button("Neustart (normal)").clicked() { self.shared.boot(BootMode::Normal); }
                if ui.button("Neustart (custom)").clicked() { self.shared.boot(BootMode::Custom); }
                if ui.button("Update von Karte").clicked() { self.shared.boot(BootMode::Update); }
                let label = if self.sound { "Ton: an" } else { "Ton: aus" };
                if ui.button(label).clicked() {
                    self.sound = !self.sound;
                    if self.sound && self.audio.is_none() {
                        match audio::AudioOut::new() { Ok(a) => self.audio = Some(a), Err(e) => { self.audio_err = Some(e); self.sound = false; } }
                    }
                    if let Some(a) = &self.audio { a.set_enabled(self.sound); }
                }
                if ui.selectable_label(self.dbg.open, "Debug").clicked() { self.dbg.open = !self.dbg.open; }
                if let Some(a) = &self.audio { ui.label(format!("Pegel {:.2}", a.level())); }
                if let Some(e) = &self.audio_err { ui.colored_label(egui::Color32::LIGHT_RED, e); }
            });
        }
        let data = panel::PanelData {
            lcd: snap.lcd, cgram: snap.cgram, display_on: snap.display_on, leds: snap.leds,
            pressed: snap.pressed.clone(), speed: snap.speed, running: snap.running, error: snap.error.clone(),
        };
        egui::ScrollArea::both().show(ui, |ui| panel::show(ui, &data, &self.ctl, &mut self.state));
        self.dbg.show(&ctx, &self.shared);
        if let Some(path) = self.shot.clone() {
            if !self.shot_req && self.t0.elapsed().as_secs_f32() > 6.0 {
                self.shot_req = true;
                let slot = self.shot_slot.clone();
                ctx.request_screenshot(move |img| { *slot.lock().unwrap() = Some(img); });
            }
            if let Some(img) = self.shot_slot.lock().unwrap().take() {
                let [w, h] = img.size;
                let bytes: Vec<u8> = img.pixels.iter().flat_map(|p| p.to_array()).collect();
                write_png(&path, w, h, &bytes);
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }
        ctx.request_repaint();
    }
}

fn write_png(path: &str, w: usize, h: usize, rgba: &[u8]) {
    fn crc(data: &[u8]) -> u32 {
        let mut c = 0xffff_ffffu32;
        for &b in data {
            c ^= b as u32;
            for _ in 0..8 {
                c = if c & 1 == 1 { 0xedb8_8320 ^ (c >> 1) } else { c >> 1 };
            }
        }
        !c
    }
    fn chunk(out: &mut Vec<u8>, ty: &[u8; 4], d: &[u8]) {
        out.extend((d.len() as u32).to_be_bytes());
        let mut b = ty.to_vec();
        b.extend(d);
        out.extend(&b);
        out.extend(crc(&b).to_be_bytes());
    }
    let mut raw = Vec::new();
    for y in 0..h {
        raw.push(0);
        raw.extend(&rgba[y * w * 4..(y + 1) * w * 4]);
    }
    let mut z = vec![0x78, 0x01];
    let mut i = 0;
    while i < raw.len() {
        let n = (raw.len() - i).min(65535);
        z.push(if i + n == raw.len() { 1 } else { 0 });
        z.extend((n as u16).to_le_bytes());
        z.extend((!(n as u16)).to_le_bytes());
        z.extend(&raw[i..i + n]);
        i += n;
    }
    let (mut a, mut b) = (1u32, 0u32);
    for &x in &raw {
        a = (a + x as u32) % 65521;
        b = (b + a) % 65521;
    }
    z.extend(((b << 16) | a).to_be_bytes());
    let mut out = vec![0x89, b'P', b'N', b'G', 13, 10, 26, 10];
    let mut ihdr = Vec::new();
    ihdr.extend((w as u32).to_be_bytes());
    ihdr.extend((h as u32).to_be_bytes());
    ihdr.extend([8, 6, 0, 0, 0]);
    chunk(&mut out, b"IHDR", &ihdr);
    chunk(&mut out, b"IDAT", &z);
    chunk(&mut out, b"IEND", &[]);
    std::fs::write(path, out).unwrap();
}

fn main() -> eframe::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    if let Some(i) = args.iter().position(|a| a == "--perf-report") {
        let n: f64 = args.get(i + 1).and_then(|v| v.parse().ok()).unwrap_or(10.0);
        debug::perf_report(n);
        return Ok(());
    }
    let opts = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default().with_inner_size([1100.0, 800.0]).with_title("ESX-1 Emulator"),
        ..Default::default()
    };
    eframe::run_native("ESX-1 Emulator", opts, Box::new(|_cc| Ok(Box::new(App::new()))))
}
