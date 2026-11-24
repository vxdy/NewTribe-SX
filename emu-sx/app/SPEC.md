# esx-ui: native Rust UI for the ESX-1 emulator

Crate `app/` (binary `esx-ui`) depends on `../core` (crate `sh3core`, now crate-type cdylib+rlib; its `extern "C"` fns
`emu_new/emu_run/emu_hook/...` can be called directly from Rust, make them `pub` if needed).
It replaces `server.py` + `ui.html` + the Python glue (`rmachine.py`, `lcd.py`, `keys.py`, `nand.py`, `smartmedia.py`, `container.py`).
Reference behaviour = the Python files in `emu-sx/` (they work; port them faithfully). Keymap: `emu-sx/keymap.json`
(id -> "row,mask"), key-name notes `keymap_notes.json`. Firmware: `../factory-firmware-sm`, images `out_flash.bin`, `out_nand_factory.bin`
(normal boot), test data `../test-data/factory.esx`.

Shared interface (module `machine`, owned by the machine agent; panel/audio agents code against it):

```rust
pub struct Shared {                      // Arc<Shared>, lives in main
    pub keys:   Mutex<std::collections::HashSet<(u8,u8)>>,   // pressed (row,mask), written by UI, read by emu thread
    pub fn set_adc(&self, col:u8, ch:u8, v:u16);              // 10-bit knob/slider values
    pub fn set_key(&self, row:u8, mask:u8, down:bool);
    pub fn set_encoder(&self, clicks:i32);                    // dial turn (positive = clockwise)
    pub fn set_arp(&self, touched:bool, slider:u16);          // touchpad + slider (see server.py _apply_arp)
    pub fn snapshot(&self) -> Snapshot;                        // cheap copy for painting (updated by emu thread ~60 Hz)
    pub fn take_audio(&self) -> Vec<i16>;                      // drained interleaved stereo i16 @44100 Hz
    pub fn boot(&self, mode: BootMode);                        // BootMode::{Normal, Update}; restarts the emu thread
}
pub struct Snapshot { pub lcd: [[u8;40];2], pub cgram: [u8;64], pub display_on: bool, pub leds: [u8;13],
                      pub pressed: Vec<(u8,u8)>, pub speed: f32 /*emu seconds per wall second*/, pub running: bool,
                      pub error: Option<String>, pub dsp_boot: u8 }
```
Key ids / knob ids used by the panel are the ones in keymap.json (e.g. "play","shift","step1".."step16","d1".. ) and the panel
must also cover knobs/slider/touchpad exactly like ui.html does (knob -> ADC mapping is in ui.html / `scratch/adc*.py`).
