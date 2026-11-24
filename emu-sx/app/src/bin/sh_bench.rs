#[path = "../metrics.rs"]
mod metrics;
#[path = "../machine.rs"]
mod machine;

fn main() {
    let n: u64 = std::env::args().nth(1).and_then(|a| a.parse().ok()).unwrap_or(300_000_000);
    let (done, dt, hash, lcd) = machine::headless_run(n);
    println!("instr={} time={:.2}s MIPS={:.1} hash={:016x}
lcd={:?}", done, dt, done as f64 / dt / 1e6, hash, lcd);
}
