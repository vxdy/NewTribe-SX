//! Plays a decaying 440 Hz tone through AudioOut::push(), emulating a
//! slow producer (speed 0.6) delivering bursts every ~16 ms.
#[path = "../metrics.rs"]
mod metrics;
#[path = "../audio.rs"]
mod audio;

use std::time::{Duration, Instant};

fn main() {
    let out = match audio::AudioOut::new() {
        Ok(o) => o,
        Err(e) => {
            eprintln!("no audio available: {e}");
            return;
        }
    };
    let speed = 0.6f32;
    let start = Instant::now();
    let mut produced: u64 = 0;
    let total_s = 4.0;
    while start.elapsed().as_secs_f64() < total_s / speed as f64 + 1.0 {
        let want = (start.elapsed().as_secs_f64() * 44100.0 * speed as f64) as u64;
        let want = want.min((total_s * 44100.0) as u64);
        if want > produced {
            let mut buf = Vec::with_capacity(((want - produced) * 2) as usize);
            for n in produced..want {
                let t = n as f64 / 44100.0;
                let v = (t * 440.0 * std::f64::consts::TAU).sin() * (-t).exp() * 0.5;
                let s = (v * 32767.0) as i16;
                buf.push(s);
                buf.push(s);
            }
            out.push(&buf, speed);
            produced = want;
        }
        print!("\rlevel {:.3}  ", out.level());
        std::thread::sleep(Duration::from_millis(16));
    }
    println!("\ndone");
}
