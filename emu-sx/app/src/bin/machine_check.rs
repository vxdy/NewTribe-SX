#[path = "../metrics.rs"]
mod metrics;
#[path = "../machine.rs"]
mod machine;

use machine::{BootMode, Shared};
use std::time::{Duration, Instant};

fn main() {
    let dir = machine::esx_dir();
    let km: serde_json::Value = serde_json::from_slice(&std::fs::read(dir.join("keymap.json")).unwrap()).unwrap();
    let play = km["play"].as_str().unwrap();
    let (r, k) = play.split_once(',').unwrap();
    let (row, mask) = (r.parse::<u8>().unwrap(), k.parse::<u8>().unwrap());

    let sh = Shared::new();
    sh.boot(BootMode::Normal);
    let t0 = Instant::now();
    let mut ok = false;
    while t0.elapsed() < Duration::from_secs(120) {
        std::thread::sleep(Duration::from_millis(200));
        let s = sh.snapshot();
        if let Some(e) = &s.error { panic!("error: {e}"); }
        if s.lcd[0].starts_with(b"House1") {
            ok = true;
            break;
        }
    }
    let s = sh.snapshot();
    println!("LCD after {:.1}s: {:?} / {:?} speed={:.2} dsp_boot={} display_on={}", t0.elapsed().as_secs_f32(),
             String::from_utf8_lossy(&s.lcd[0]), String::from_utf8_lossy(&s.lcd[1]), s.speed, s.dsp_boot, s.display_on);
    assert!(ok, "House1 not shown");
    sh.take_audio();
    sh.set_key(row, mask, true);
    std::thread::sleep(Duration::from_millis(300));
    sh.set_key(row, mask, false);
    std::thread::sleep(Duration::from_secs(4));
    let a = sh.take_audio();
    let (mn, mx) = (a.iter().min().copied().unwrap_or(0), a.iter().max().copied().unwrap_or(0));
    let s = sh.snapshot();
    println!("audio samples={} min={} max={} leds={:?} speed={:.2}", a.len(), mn, mx, s.leds, s.speed);
    assert!(a.len() > 1000 && mn != mx, "audio missing or constant");
    sh.boot(BootMode::Normal); // reboot path (frees the old Emu)
    std::thread::sleep(Duration::from_secs(1));
    sh.shutdown();
    println!("OK");
}
