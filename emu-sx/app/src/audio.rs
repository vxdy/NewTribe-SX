//! Gapless audio output for the (slower than real time) ESX-1 emulator.
//!
//! Source: interleaved stereo i16 @ 44100 Hz, delivered in bursts via `push`.
//! The device callback pulls from a shared ring, resampling on the fly with
//! pitch = clamp(speed, 0.05, 1.0) so that consumption matches production.
#![allow(dead_code)]

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{FromSample, SampleFormat, SizedSample};
use std::collections::VecDeque;
use crate::metrics::audio_stats;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{mpsc, Arc, Mutex};

pub const SRC_RATE: f64 = 44100.0;
/// Start playing once this much audio is buffered (frames).
const PRIME_FRAMES: usize = (SRC_RATE * 0.12) as usize;
/// Above this the buffer is considered stale.
const MAX_FRAMES: usize = (SRC_RATE * 0.40) as usize;
/// Trim target when stale audio is dropped.
const TRIM_FRAMES: usize = (SRC_RATE * 0.15) as usize;
/// Fade step per output frame (~256 frames fade).
const FADE_STEP: f32 = 1.0 / 256.0;
const HP_R: f32 = 0.995;

/// Device-independent ring + resampler + fades + DC blocker.
pub struct Core {
    ring: VecDeque<(f32, f32)>,
    /// Fractional read position between ring[0] and ring[1].
    frac: f64,
    pitch: f64,
    playing: bool,
    gain: f32,
    enabled: bool,
    last: (f32, f32),
    hp_x: (f32, f32),
    hp_y: (f32, f32),
    pub peak: f32,
    in_underrun: bool,
}

impl Core {
    pub fn new() -> Self {
        Core {
            ring: VecDeque::new(),
            frac: 0.0,
            pitch: 1.0,
            playing: false,
            gain: 0.0,
            enabled: true,
            last: (0.0, 0.0),
            hp_x: (0.0, 0.0),
            hp_y: (0.0, 0.0),
            peak: 0.0,
            in_underrun: false,
        }
    }

    pub fn buffered_frames(&self) -> usize {
        self.ring.len()
    }

    pub fn is_playing(&self) -> bool {
        self.playing
    }

    pub fn set_enabled(&mut self, on: bool) {
        self.enabled = on;
        if !on {
            self.clear_buffer();
        }
    }

    pub fn clear_buffer(&mut self) {
        self.ring.clear();
        self.frac = 0.0;
    }

    pub fn push(&mut self, samples: &[i16], speed: f32) {
        self.pitch = speed.clamp(0.05, 1.0) as f64;
        if !self.enabled {
            return;
        }
        for c in samples.chunks_exact(2) {
            self.ring
                .push_back((c[0] as f32 / 32768.0, c[1] as f32 / 32768.0));
        }
        if self.ring.len() > MAX_FRAMES {
            let drop = self.ring.len() - TRIM_FRAMES;
            let st = audio_stats();
            st.trims.fetch_add(1, Ordering::Relaxed);
            st.trimmed_frames.fetch_add(drop as u64, Ordering::Relaxed);
            self.ring.drain(..drop);
            self.frac = 0.0;
        }
    }

    /// Render `out.len()` stereo frames at device rate `dev_rate`.
    pub fn render(&mut self, out: &mut [(f32, f32)], dev_rate: f64) {
        let step = self.pitch * SRC_RATE / dev_rate;
        for o in out.iter_mut() {
            if !self.playing && self.ring.len() >= PRIME_FRAMES {
                self.playing = true;
            }
            let have = self.ring.len() >= 2;
            let target = if self.playing && have { 1.0 } else { 0.0 };
            if self.gain < target {
                self.gain = (self.gain + FADE_STEP).min(target);
            } else if self.gain > target {
                self.gain = (self.gain - FADE_STEP).max(target);
            }

            let mut s = (0.0f32, 0.0f32);
            if self.playing && have {
                self.in_underrun = false;
                let a = self.ring[0];
                let b = self.ring[1];
                let f = self.frac as f32;
                s = (a.0 + (b.0 - a.0) * f, a.1 + (b.1 - a.1) * f);
                self.last = s;
                self.frac += step;
                let adv = self.frac.floor();
                if adv >= 1.0 {
                    let n = (adv as usize).min(self.ring.len());
                    self.ring.drain(..n);
                    self.frac -= adv;
                }
            } else if self.playing {
                // underrun: fade out holding the last sample
                if !self.in_underrun {
                    self.in_underrun = true;
                    audio_stats().underruns.fetch_add(1, Ordering::Relaxed);
                }
                if self.gain <= 0.0 {
                    self.playing = false;
                    self.frac = 0.0;
                } else {
                    s = self.last;
                }
            }

            // one-pole DC blocker: y = x - x1 + R*y1
            let y = (
                s.0 - self.hp_x.0 + HP_R * self.hp_y.0,
                s.1 - self.hp_x.1 + HP_R * self.hp_y.1,
            );
            self.hp_x = s;
            self.hp_y = y;

            let g = self.gain;
            *o = (y.0 * g, y.1 * g);
            let p = o.0.abs().max(o.1.abs());
            self.peak = if p > self.peak { p } else { self.peak * 0.9999 };
        }
        let st = audio_stats();
        st.active.store(true, Ordering::Relaxed);
        st.ring_frames.store(self.ring.len() as u32, Ordering::Relaxed);
        st.pitch_bits.store((self.pitch as f32).to_bits(), Ordering::Relaxed);
    }
}

struct Shared {
    core: Mutex<Core>,
    level: AtomicU32,
}

pub struct AudioOut {
    shared: Arc<Shared>,
    _stop: mpsc::Sender<()>, // dropping ends the stream thread
}

impl AudioOut {
    pub fn new() -> Result<AudioOut, String> {
        let shared = Arc::new(Shared {
            core: Mutex::new(Core::new()),
            level: AtomicU32::new(0),
        });
        let (stop_tx, stop_rx) = mpsc::channel::<()>();
        let (init_tx, init_rx) = mpsc::channel::<Result<(), String>>();
        let sh = shared.clone();
        // The cpal Stream may be !Send, so it lives on its own thread.
        std::thread::Builder::new()
            .name("audio-out".into())
            .spawn(move || match build_stream(sh) {
                Ok(stream) => {
                    let _ = init_tx.send(Ok(()));
                    let _ = stop_rx.recv(); // Err when AudioOut is dropped
                    drop(stream);
                }
                Err(e) => {
                    let _ = init_tx.send(Err(e));
                }
            })
            .map_err(|e| e.to_string())?;
        init_rx
            .recv()
            .map_err(|_| "audio thread died".to_string())??;
        Ok(AudioOut { shared, _stop: stop_tx })
    }

    /// Interleaved stereo i16 @ 44100 Hz; `speed` = emulated s per wall s.
    pub fn push(&self, samples: &[i16], speed: f32) {
        if let Ok(mut c) = self.shared.core.lock() {
            c.push(samples, speed);
        }
    }

    pub fn set_enabled(&self, on: bool) {
        if let Ok(mut c) = self.shared.core.lock() {
            c.set_enabled(on);
        }
    }

    /// Recent peak (0..1) for a meter.
    pub fn level(&self) -> f32 {
        f32::from_bits(self.shared.level.load(Ordering::Relaxed))
    }

    pub fn clear(&self) {
        if let Ok(mut c) = self.shared.core.lock() {
            c.clear_buffer();
        }
    }
}

fn build_stream(sh: Arc<Shared>) -> Result<cpal::Stream, String> {
    let host = cpal::default_host();
    let dev = host
        .default_output_device()
        .ok_or("no audio output device")?;
    let cfg = dev.default_output_config().map_err(|e| e.to_string())?;
    let fmt = cfg.sample_format();
    let config: cpal::StreamConfig = cfg.into();
    let stream = match fmt {
        SampleFormat::F32 => make::<f32>(&dev, &config, sh),
        SampleFormat::I16 => make::<i16>(&dev, &config, sh),
        SampleFormat::U16 => make::<u16>(&dev, &config, sh),
        SampleFormat::I32 => make::<i32>(&dev, &config, sh),
        other => Err(format!("unsupported sample format {other:?}")),
    }?;
    stream.play().map_err(|e| e.to_string())?;
    Ok(stream)
}

fn make<T>(
    dev: &cpal::Device,
    config: &cpal::StreamConfig,
    sh: Arc<Shared>,
) -> Result<cpal::Stream, String>
where
    T: SizedSample + FromSample<f32>,
{
    let ch = (config.channels as usize).max(1);
    let rate = config.sample_rate.0 as f64;
    let mut tmp: Vec<(f32, f32)> = Vec::new();
    dev.build_output_stream(
        config,
        move |data: &mut [T], _| {
            let frames = data.len() / ch;
            tmp.resize(frames, (0.0, 0.0));
            let peak = match sh.core.try_lock() {
                Ok(mut c) => {
                    c.render(&mut tmp, rate);
                    c.peak
                }
                Err(_) => {
                    tmp.iter_mut().for_each(|f| *f = (0.0, 0.0));
                    f32::from_bits(sh.level.load(Ordering::Relaxed))
                }
            };
            sh.level.store(peak.to_bits(), Ordering::Relaxed);
            for (i, f) in data.chunks_mut(ch).enumerate() {
                let (l, r) = tmp[i];
                if ch == 1 {
                    f[0] = T::from_sample((l + r) * 0.5);
                } else {
                    f[0] = T::from_sample(l);
                    f[1] = T::from_sample(r);
                    for x in f.iter_mut().skip(2) {
                        *x = T::from_sample(0.0f32);
                    }
                }
            }
        },
        |e| eprintln!("audio stream error: {e}"),
        None,
    )
    .map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ramp(n: usize, amp: i16) -> Vec<i16> {
        (0..n)
            .flat_map(|i| {
                let v = ((i as f32 * 0.05).sin() * amp as f32) as i16;
                [v, v]
            })
            .collect()
    }

    fn render(c: &mut Core, n: usize, rate: f64) -> Vec<(f32, f32)> {
        let mut o = vec![(0.0, 0.0); n];
        c.render(&mut o, rate);
        o
    }

    #[test]
    fn silent_until_primed() {
        let mut c = Core::new();
        c.push(&ramp(1000, 10000), 1.0);
        let o = render(&mut c, 512, 44100.0);
        assert!(o.iter().all(|f| *f == (0.0, 0.0)));
        assert!(!c.is_playing());
    }

    #[test]
    fn plays_after_prime_with_fade_in() {
        let mut c = Core::new();
        c.push(&ramp(PRIME_FRAMES + 2000, 10000), 1.0);
        let o = render(&mut c, 2000, 44100.0);
        assert!(c.is_playing());
        assert!(o[0].0.abs() < 0.01);
        assert!(o.iter().any(|f| f.0.abs() > 0.1));
    }

    #[test]
    fn pitch_factor_consumes_slower() {
        let mut c = Core::new();
        c.push(&ramp(15000, 10000), 0.5);
        let before = c.buffered_frames();
        render(&mut c, 4000, 44100.0);
        let used = before - c.buffered_frames();
        assert!((1990..=2010).contains(&used), "used {used}");
    }

    #[test]
    fn device_rate_resampling() {
        let mut c = Core::new();
        c.push(&ramp(15000, 10000), 1.0);
        let before = c.buffered_frames();
        render(&mut c, 4800, 48000.0);
        let used = before - c.buffered_frames();
        let want = (4800.0 * 44100.0 / 48000.0) as i64;
        assert!((used as i64 - want).abs() <= 2, "used {used} want {want}");
    }

    #[test]
    fn speed_is_clamped() {
        let mut c = Core::new();
        c.push(&[0, 0], 0.0);
        assert!((c.pitch - 0.05).abs() < 1e-6);
        c.push(&[0, 0], 5.0);
        assert_eq!(c.pitch, 1.0);
    }

    #[test]
    fn stale_audio_dropped() {
        let mut c = Core::new();
        c.push(&ramp(MAX_FRAMES + 5000, 1000), 1.0);
        assert_eq!(c.buffered_frames(), TRIM_FRAMES);
    }

    #[test]
    fn underrun_fades_out_without_jump() {
        let mut c = Core::new();
        c.push(&vec![20000i16; (PRIME_FRAMES + 600) * 2], 1.0);
        let o = render(&mut c, 20000, 44100.0);
        let max_step = o
            .windows(2)
            .map(|w| (w[1].0 - w[0].0).abs())
            .fold(0.0, f32::max);
        assert!(max_step < 0.05, "click {max_step}");
        assert!(o.last().unwrap().0.abs() < 1e-3);
        assert!(!c.is_playing());
    }

    #[test]
    fn dc_removed() {
        let mut c = Core::new();
        c.push(&vec![8000i16; 44100 * 2], 1.0);
        let o = render(&mut c, 40000, 44100.0);
        assert!(o.last().unwrap().0.abs() < 0.01);
    }

    #[test]
    fn disable_clears_and_ignores() {
        let mut c = Core::new();
        c.push(&ramp(5000, 1000), 1.0);
        c.set_enabled(false);
        assert_eq!(c.buffered_frames(), 0);
        c.push(&ramp(5000, 1000), 1.0);
        assert_eq!(c.buffered_frames(), 0);
        c.set_enabled(true);
        c.push(&ramp(5000, 1000), 1.0);
        assert_eq!(c.buffered_frames(), 5000);
    }
}
