//! Standalone demo of the front panel with mock data.
//! `panel_demo [--orig] [--shot out.png]`: --shot saves a screenshot after a few frames and exits.
#![allow(dead_code, deprecated)]
#[path = "../panel.rs"]
mod panel;

use eframe::egui;
use std::sync::Mutex;

struct Mock {
    log: Mutex<Vec<String>>,
}
impl panel::Control for Mock {
    fn key(&self, row: u8, mask: u8, down: bool) {
        println!("key {row},{mask:#x} {}", if down { "down" } else { "up" });
        self.log.lock().unwrap().push(format!("key {row},{mask} {down}"));
    }
    fn adc(&self, col: u8, ch: u8, v: u16) {
        println!("adc {col},{ch} = {v}");
    }
    fn encoder(&self, clicks: i32) {
        println!("encoder {clicks}");
    }
    fn arp(&self, touched: bool, slider: u16) {
        println!("arp touched={touched} slider={slider}");
    }
}

struct App {
    ctl: Mock,
    data: panel::PanelData,
    st: panel::PanelState,
    shot: Option<String>,
    frame: u32,
    shot_slot: std::sync::Arc<Mutex<Option<std::sync::Arc<egui::ColorImage>>>>,
}

fn put(row: &mut [u8; 40], s: &str) {
    row.fill(b' ');
    for (i, b) in s.bytes().enumerate().take(40) {
        row[i] = b;
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

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        egui::ScrollArea::both().show(ui, |ui| panel::show(ui, &self.data, &self.ctl, &mut self.st));
        let ctx = ui.ctx().clone();
        self.frame += 1;
        if let Some(path) = self.shot.clone() {
            if self.frame == 8 {
                let slot = self.shot_slot.clone();
                ctx.request_screenshot(move |img| {
                    *slot.lock().unwrap() = Some(img);
                });
            }
            let img = self.shot_slot.lock().unwrap().take();
            if let Some(img) = img {
                let [w, h] = img.size;
                let bytes: Vec<u8> = img.pixels.iter().flat_map(|p| p.to_array()).collect();
                write_png(&path, w, h, &bytes);
                println!("screenshot saved {path}");
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
            if self.frame > 60 {
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
        }
        ctx.request_repaint();
    }
}

fn main() -> eframe::Result {
    let args: Vec<String> = std::env::args().collect();
    let mut data = panel::PanelData { display_on: true, running: true, speed: 1.0, ..Default::default() };
    put(&mut data.lcd[0], "House1");
    put(&mut data.lcd[1], "A.01");
    data.cgram[..8].copy_from_slice(&[0, 4, 14, 31, 14, 4, 0, 0]);
    data.lcd[1][10] = 0; // CGRAM glyph 0
    data.leds = [0x05, 0x01, 0x20, 0x02, 0x08, 0x55, 0x01, 0x01, 0x00, 0x00, 0, 0, 0];
    data.pressed = vec![(9, 4)];
    let mut st = panel::PanelState::default();
    if args.iter().any(|a| a == "--orig") {
        st.view = panel::View::Original;
    }
    let shot = args.iter().position(|a| a == "--shot").and_then(|i| args.get(i + 1).cloned());
    let opts = eframe::NativeOptions { viewport: egui::ViewportBuilder::default().with_inner_size([1250.0, 900.0]), ..Default::default() };
    eframe::run_native(
        "panel_demo",
        opts,
        Box::new(move |_cc| Ok(Box::new(App { ctl: Mock { log: Mutex::new(vec![]) }, data, st, shot, frame: 0, shot_slot: Default::default() }))),
    )
}
