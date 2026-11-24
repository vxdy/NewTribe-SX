//! Native egui front panel of the ESX-1 emulator (port of ui.html).
//!
//! Public API: `Control`, `PanelData`, `PanelState`, `show`.
//! Two views as in ui.html: the original-panel layout (954x681 reference coordinates) and the
//! modern dark layout. Both use the same widgets (buttons, LEDs, knobs, LCD, touchpad/slider).
#![allow(deprecated)]

use eframe::egui::{
    self, pos2, vec2, Align2, Color32, FontId, Id, Painter, Pos2, Rect, Response, Sense, Shape, Stroke, StrokeKind, Ui,
};
use std::collections::{HashMap, HashSet};
use std::sync::OnceLock;

// ------------------------------------------------------------------------------------------------
// Public interface
// ------------------------------------------------------------------------------------------------

/// Sink for panel input (the integrator adapts `machine::Shared` to this).
pub trait Control {
    fn key(&self, row: u8, mask: u8, down: bool);
    fn adc(&self, col: u8, ch: u8, v: u16);
    fn encoder(&self, clicks: i32);
    fn arp(&self, touched: bool, slider: u16);
}

/// Plain copy of what the panel paints (adapted from `machine::Snapshot`).
#[derive(Clone, Debug)]
pub struct PanelData {
    pub lcd: [[u8; 40]; 2],
    pub cgram: [u8; 64],
    pub display_on: bool,
    pub leds: [u8; 13],
    pub pressed: Vec<(u8, u8)>,
    pub speed: f32,
    pub running: bool,
    pub error: Option<String>,
}

impl Default for PanelData {
    fn default() -> Self {
        PanelData { lcd: [[b' '; 40]; 2], cgram: [0; 64], display_on: false, leds: [0; 13], pressed: Vec::new(), speed: 0.0, running: false, error: None }
    }
}

/// +1 / -1 / 0 from mouse wheel events this frame (wheel up = +1 = clockwise).
fn wheel_dir(ui: &Ui) -> i32 {
    let sum: f32 = ui.input(|i| i.events.iter().map(|e| if let egui::Event::MouseWheel { delta, .. } = e { delta.y } else { 0.0 }).sum());
    if sum > 0.0 { 1 } else if sum < 0.0 { -1 } else { 0 }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum View {
    Modern,
    Original,
}

struct Down {
    send_up: bool,
    seen: bool,
}

/// UI-side state of the panel (knob positions, latched buttons, ...). Keep one per window.
pub struct PanelState {
    pub view: View,
    pub show_map: bool,
    pub knobs: HashMap<String, f32>,
    pub fx_code: u8,
    pub slider: u16,
    pub pad_touched: bool,
    pub pad_y: f32,
    pub enc_angle: f32,
    pub adc: [[u16; 4]; 4],
    held: HashSet<String>,
    mouse_down: HashMap<String, Down>,
    kdown: HashSet<&'static str>,
}

impl Default for PanelState {
    fn default() -> Self {
        PanelState {
            view: View::Modern,
            show_map: false,
            knobs: HashMap::new(),
            fx_code: 0,
            slider: 512,
            pad_touched: false,
            pad_y: 0.5,
            enc_angle: 0.0,
            adc: { let mut a = [[512u16; 4]; 4]; a[2][2] = 1023; a },   // ribbon untouched
            held: HashSet::new(),
            mouse_down: HashMap::new(),
            kdown: HashSet::new(),
        }
    }
}

// ------------------------------------------------------------------------------------------------
// Keymap / LED tables
// ------------------------------------------------------------------------------------------------

struct Km {
    map: HashMap<String, (u8, u8)>,
    rev: HashMap<(u8, u8), String>,
    notes: HashMap<(u8, u8), String>,
}

fn parse_cell(s: &str) -> Option<(u8, u8)> {
    let (a, b) = s.split_once(',')?;
    Some((a.trim().parse().ok()?, b.trim().parse().ok()?))
}

fn km() -> &'static Km {
    static KM: OnceLock<Km> = OnceLock::new();
    KM.get_or_init(|| {
        let mut map = HashMap::new();
        let mut rev = HashMap::new();
        let mut notes = HashMap::new();
        if let Ok(serde_json::Value::Object(o)) = serde_json::from_str(include_str!("../../keymap.json")) {
            for (k, v) in o {
                if let Some(c) = v.as_str().and_then(parse_cell) {
                    map.insert(k.clone(), c);
                    rev.entry(c).or_insert(k);
                }
            }
        }
        if let Ok(serde_json::Value::Object(o)) = serde_json::from_str(include_str!("../../keymap_notes.json")) {
            for (k, v) in o {
                if let (Some(c), Some(s)) = (parse_cell(&k), v.as_str()) {
                    notes.insert(c, s.to_string());
                }
            }
        }
        Km { map, rev, notes }
    })
}

/// (byte index in the 13-byte LED table, bit) for a control/LED id. Source: ui.html LEDS / scratch/ledmap2.py.
fn led_pos(id: &str) -> Option<(usize, u8)> {
    let p = match id {
        "d1" => (5, 0),
        "d2" => (5, 1),
        "d3" => (6, 0),
        "d4" => (6, 1),
        "d5" => (7, 0),
        "d6a" => (7, 1),
        "d6b" => (8, 0),
        "d7a" => (8, 1),
        "d7b" => (9, 0),
        "accent" => (9, 1),
        "k1" => (10, 0),
        "k2" => (10, 1),
        "s1" => (11, 0),
        "s2" => (11, 1),
        "slice" => (12, 0),
        "arrange" => (12, 1),
        "pattern" => (1, 0),
        "stepedit" => (1, 1),
        "partedit" => (1, 2),
        "sample" => (0, 0),
        "song" => (0, 1),
        "global" => (0, 2),
        "write" => (1, 3),
        "autobpm" => (2, 3),
        "rec" => (3, 0),
        "audioin_trig" => (2, 1),
        "tempolock" => (2, 0),
        "reverse" => (1, 7),
        "roll" => (1, 6),
        "fxsend" => (2, 7),
        "bpmsync" => (4, 7),
        "fxmotion" => (0, 7),
        "pfx1" => (2, 4),
        "pfx2" => (2, 5),
        "pfx3" => (2, 6),
        "fx1" => (0, 4),
        "fx2" => (0, 5),
        "fx3" => (0, 6),
        "mod0" => (4, 3),
        "mod1" => (4, 4),
        "mod2" => (4, 5),
        "mod3" => (4, 6),
        "smooth" => (3, 6),
        "trighold" => (3, 7),
        "flt0" => (9, 5),
        "flt1" => (11, 5),
        "flt2" => (10, 5),
        "beatled" => (12, 3),
        "ampa" => (1, 5),
        "ampb" => (1, 4),
        "chain1" => (7, 5),
        "chain2" => (8, 5),
        "flt3" => (12, 5),
        "modt0" => (3, 3),
        "modt1" => (3, 4),
        "modt2" => (3, 5),
        "modt3" => (3, 1),
        "modt4" => (3, 2),
        _ => {
            if let Some(n) = id.strip_prefix("beat").and_then(|n| n.parse::<usize>().ok()).filter(|n| *n < 8) {
                return Some((5 + n, 2));
            }
            if let Some(n) = id.strip_prefix("bar").and_then(|n| n.parse::<usize>().ok()).filter(|n| *n < 8) {
                return Some((5 + n, 4));
            }
            if let Some(n) = id.strip_prefix("step").and_then(|n| n.parse::<usize>().ok()).filter(|n| (1..=16).contains(n)) {
                let i = n - 1;
                return Some((5 + (i >> 1), 6 + (i & 1) as u8));
            }
            return None;
        }
    };
    Some(p)
}

/// Knob -> ADC (mux col, channel), `col` = PD7<<1 | PD5 as the emulator core computes it. Reverse-engineered from the firmware scan
/// routine (0x0C08147A: 4 mux groups x 4 channels, table at 0x0C0D0730 maps each slot to a pot index; PD high nibble = mux address,
/// PD low nibble = key-matrix column). Each knob owns exactly one slot; master / tube gain / audio-in level are analog-only (not scanned).
/// The arp slider is (0,2) (see `Machine::set_arp`), the ribbon controller is (2,2) (< ~0x340 = touched, position; 0x3FF = untouched).
fn knob_adc(id: &str) -> &'static [(u8, u8)] {
    match id {
        "pitch" => &[(2, 0)],
        "pan" => &[(1, 0)],
        "fxtime" => &[(0, 0)],
        "level" => &[(3, 0)],
        "startpoint" => &[(1, 2)],
        "speed" => &[(2, 1)],
        "depth" => &[(0, 1)],
        "cutoff" => &[(0, 3)],
        "reso" => &[(1, 3)],
        "fxin" => &[(2, 3)],
        "fxc1" => &[(1, 1)],
        "fxc2" => &[(3, 1)],
        _ => &[],
    }
}

/// Ribbon controller (touch pad) ADC slot.
const RIBBON_ADC: (u8, u8) = (2, 2);

const FXN: [&str; 16] = [
    "—", "HPF", "RINGMOD", "TALKMOD", "MODDLY", "DECI", "GRAINSFT", "DIST", "BPMDLY", "LPF", "PHASER", "PITCHSFT", "SHORTDLY", "EQ",
    "CHO/FLG", "COMP",
];
const MASKS: [u8; 6] = [1, 2, 4, 8, 16, 128];
const TOGGLE: [&str; 2] = ["padnote", "solo"];

// ------------------------------------------------------------------------------------------------
// LCD font
// ------------------------------------------------------------------------------------------------

const FONT5X7: &str = "000000000000005F00000007000700147F147F14242A7F2A12231308646236495522500005030000001C2241000041221C00082A1C2A0808083E080800503000000808080808006060000020100804023E5149453E00427F400042615149462141454B311814127F1027454545393C4A49493001710905033649494936064949291E003636000000563600000008142241141414141441221408000201510906324979413E7E1111117E7F494949363E414141227F4141221C7F494949417F090901013E414151327F0808087F00417F41002040413F017F081422417F404040407F0204027F7F0408107F3E4141413E7F090909063E4151215E7F09192946464949493101017F01013F4040403F1F2040201F7F2018207F63140814630304780403615149454300007F4141020408102041417F000004020102044040404040000102040020545454787F484444383844444420384444487F3854545418087E090102081454543C7F0804047800447D40002040443D00007F10284400417F40007C041804787C0804047838444444387C14141408081414187C7C080404084854545420043F4440203C4040207C1C2040201C3C4030403C44281028440C5050503C4464544C44000836410000007F0000004136080008082A1C08";

fn font() -> &'static Vec<u8> {
    static F: OnceLock<Vec<u8>> = OnceLock::new();
    F.get_or_init(|| (0..FONT5X7.len() / 2).map(|i| u8::from_str_radix(&FONT5X7[i * 2..i * 2 + 2], 16).unwrap_or(0)).collect())
}

fn ascii_rows(code: u8) -> [u8; 8] {
    let mut rows = [0u8; 8];
    let f = font();
    let base = (code as usize - 32) * 5;
    for (y, row) in rows.iter_mut().enumerate().take(7) {
        for x in 0..5 {
            let col = f.get(base + x).copied().unwrap_or(0);
            if (col >> y) & 1 == 1 {
                *row |= 1 << (4 - x);
            }
        }
    }
    rows
}

fn glyph_rows(cg: &[u8; 64], code: u8) -> [u8; 8] {
    let i = (code as usize & 7) * 8;
    let mut r = [0u8; 8];
    for (y, v) in r.iter_mut().enumerate() {
        *v = cg[i + y] & 31;
    }
    r
}

// ------------------------------------------------------------------------------------------------
// Styles
// ------------------------------------------------------------------------------------------------

#[derive(Clone, Copy, PartialEq)]
enum Sty {
    Light,
    Dark,
    Red,
    Key,
    Tp,
    TpRec,
    TpPlay,
    Round,
    M,
    MMode,
    MTp,
    MTpRec,
    MTpPlay,
    MRound,
    MPad,
}

fn c(r: u8, g: u8, b: u8) -> Color32 {
    Color32::from_rgb(r, g, b)
}
const LCD_BG: Color32 = Color32::from_rgb(255, 154, 28);
const LCD_INK: Color32 = Color32::from_rgb(46, 21, 0);
const LED_OFF: Color32 = Color32::from_rgb(64, 8, 15);
const LED_RED: Color32 = Color32::from_rgb(255, 59, 48);
const LED_GRN: Color32 = Color32::from_rgb(61, 255, 90);
const CREAM: Color32 = Color32::from_rgb(246, 233, 236);

/// (fill, text, stroke)
fn colors(s: Sty, lit: bool, pressed: bool) -> (Color32, Color32, Color32) {
    let modern = matches!(s, Sty::M | Sty::MMode | Sty::MTp | Sty::MTpRec | Sty::MTpPlay | Sty::MRound | Sty::MPad);
    if lit {
        return if modern {
            (c(0x5d, 0x1f, 0x2a), Color32::WHITE, c(0xff, 0x4d, 0x5e))
        } else {
            (c(0xff, 0x8b, 0x95), c(0x40, 0, 0), c(0x70, 0x20, 0x20))
        };
    }
    let (f, t, st) = match s {
        Sty::Light => (c(0xe4, 0xdd, 0xcb), c(0x1b, 0x1a, 0x19), c(0x44, 0x3c, 0x30)),
        Sty::Dark => (c(0x3c, 0x3c, 0x40), c(0xf1, 0xf1, 0xf1), c(0x10, 0x10, 0x12)),
        Sty::Red => (c(0xb3, 0x2a, 0x46), c(0xff, 0xdd, 0xee), c(0x40, 0x0c, 0x18)),
        Sty::Key => (c(0xee, 0xec, 0xe4), c(0x22, 0x22, 0x22), c(0x44, 0x40, 0x38)),
        Sty::Tp | Sty::Round => (c(0xf0, 0xef, 0xec), c(0x22, 0x22, 0x22), c(0x44, 0x40, 0x38)),
        Sty::TpRec => (c(0xf0, 0xef, 0xec), c(0xe0, 0x30, 0x3c), c(0x44, 0x40, 0x38)),
        Sty::TpPlay => (c(0xf0, 0xef, 0xec), c(0x3b, 0xb5, 0x4a), c(0x44, 0x40, 0x38)),
        Sty::M | Sty::MRound => (c(0x1c, 0x1c, 0x20), c(0xd4, 0xd6, 0xda), c(0x3a, 0x3a, 0x40)),
        Sty::MMode => (c(0x1c, 0x1c, 0x20), c(0xff, 0x8a, 0x98), c(0x3a, 0x3a, 0x40)),
        Sty::MTp => (c(0x1c, 0x1c, 0x20), c(0xd4, 0xd6, 0xda), c(0x3a, 0x3a, 0x40)),
        Sty::MTpRec => (c(0x1c, 0x1c, 0x20), c(0xff, 0x5c, 0x6a), c(0x3a, 0x3a, 0x40)),
        Sty::MTpPlay => (c(0x1c, 0x1c, 0x20), c(0x59, 0xd3, 0x6b), c(0x3a, 0x3a, 0x40)),
        Sty::MPad => (c(0x08, 0x08, 0x0a), c(0x8a, 0x8d, 0x94), c(0x3a, 0x3a, 0x40)),
    };
    if pressed {
        let d = |x: Color32| Color32::from_rgb((x.r() as f32 * 0.8) as u8, (x.g() as f32 * 0.8) as u8, (x.b() as f32 * 0.8) as u8);
        let l = |x: Color32| Color32::from_rgb(x.r().saturating_add(24), x.g().saturating_add(24), x.b().saturating_add(28));
        return (if modern { l(f) } else { d(f) }, t, st);
    }
    (f, t, st)
}

fn draw_symbol(p: &Painter, name: &str, ctr: Pos2, size: f32, col: Color32) -> bool {
    let h = size * 0.5;
    let poly = |pts: Vec<Pos2>| {
        p.add(Shape::convex_polygon(pts, col, Stroke::NONE));
    };
    match name {
        "@up" => poly(vec![ctr + vec2(0.0, -h), ctr + vec2(h, h * 0.8), ctr + vec2(-h, h * 0.8)]),
        "@down" => poly(vec![ctr + vec2(0.0, h), ctr + vec2(h, -h * 0.8), ctr + vec2(-h, -h * 0.8)]),
        "@left" => poly(vec![ctr + vec2(-h, 0.0), ctr + vec2(h * 0.8, h), ctr + vec2(h * 0.8, -h)]),
        "@right" => poly(vec![ctr + vec2(h, 0.0), ctr + vec2(-h * 0.8, h), ctr + vec2(-h * 0.8, -h)]),
        "@rec" => {
            p.circle_filled(ctr, h * 0.8, col);
        }
        "@stop" => {
            p.rect_filled(Rect::from_center_size(ctr, vec2(h * 1.4, h * 1.4)), 1.0, col);
        }
        "@play" => {
            poly(vec![ctr + vec2(-h * 1.6, -h * 0.8), ctr + vec2(-h * 1.6, h * 0.8), ctr + vec2(-h * 0.4, 0.0)]);
            let r = Rect::from_center_size(ctr + vec2(h * 0.7, 0.0), vec2(h * 0.35, h * 1.4));
            p.rect_filled(r, 0.0, col);
            p.rect_filled(r.translate(vec2(h * 0.6, 0.0)), 0.0, col);
        }
        "@back" => {
            p.rect_filled(Rect::from_center_size(ctr + vec2(-h * 0.9, 0.0), vec2(h * 0.3, h * 1.4)), 0.0, col);
            poly(vec![ctr + vec2(h * 0.9, -h * 0.8), ctr + vec2(h * 0.9, h * 0.8), ctr + vec2(-h * 0.6, 0.0)]);
        }
        _ => return false,
    }
    true
}

// ------------------------------------------------------------------------------------------------
// Panel environment
// ------------------------------------------------------------------------------------------------

struct Env<'a> {
    data: &'a PanelData,
    ctl: &'a dyn Control,
    st: &'a mut PanelState,
}

impl<'a> Env<'a> {
    fn led_on(&self, id: &str) -> bool {
        led_pos(id).map(|(b, bit)| (self.data.leds[b] >> bit) & 1 == 1).unwrap_or(false)
    }

    fn is_pressed(&self, id: &str) -> bool {
        km().map.get(id).map(|k| self.data.pressed.contains(k)).unwrap_or(false)
    }

    /// Edge handling for a mouse-held control (toggle-latching, Ctrl+click hold) like `wire()` in ui.html.
    fn edge(&mut self, id: &str, key: (u8, u8), down_now: bool, ctrl: bool) {
        let tog = ctrl || TOGGLE.contains(&id);
        let known = self.st.mouse_down.contains_key(id);
        if down_now && !known {
            if tog && self.st.held.contains(id) {
                self.st.held.remove(id);
                self.ctl.key(key.0, key.1, false);
                self.st.mouse_down.insert(id.to_string(), Down { send_up: false, seen: true });
            } else {
                self.ctl.key(key.0, key.1, true);
                if tog {
                    self.st.held.insert(id.to_string());
                }
                self.st.mouse_down.insert(id.to_string(), Down { send_up: true, seen: true });
            }
        } else if down_now {
            if let Some(d) = self.st.mouse_down.get_mut(id) {
                d.seen = true;
            }
        } else if known {
            let d = self.st.mouse_down.remove(id).unwrap();
            if d.send_up && !self.st.held.contains(id) {
                self.ctl.key(key.0, key.1, false);
            }
        }
    }

    fn btn(&mut self, ui: &mut Ui, rect: Rect, id: &str, label: &str, sty: Sty, fs: f32) -> Response {
        let resp = ui.interact(rect, Id::new(("btn", id, self.st.view as u8)), Sense::click_and_drag());
        let key = km().map.get(id).copied();
        if let Some(k) = key {
            let ctrl = ui.input(|i| i.modifiers.ctrl);
            self.edge(id, k, resp.is_pointer_button_down_on(), ctrl);
        }
        let lit = led_pos(id).is_some() && self.led_on(id);
        let pressed = self.is_pressed(id) || resp.is_pointer_button_down_on();
        let (fill, tcol, stroke) = colors(sty, lit, pressed);
        let p = ui.painter_at(rect.expand(8.0));
        let modern = matches!(sty, Sty::M | Sty::MMode | Sty::MTp | Sty::MTpRec | Sty::MTpPlay | Sty::MRound | Sty::MPad);
        let mut r = rect;
        let rad = match sty {
            Sty::Round | Sty::MRound => rect.height().min(rect.width()) * 0.5,
            Sty::MPad => 8.0,
            _ => (rect.height() * 0.18).clamp(2.0, 8.0),
        };
        if !modern {
            // drop shadow / key travel
            if pressed {
                r = r.translate(vec2(0.0, rect.height() * 0.05));
            } else {
                p.rect_filled(rect.translate(vec2(0.0, rect.height() * 0.07)), rad, Color32::from_black_alpha(150));
            }
        }
        p.rect_filled(r, rad, fill);
        p.rect_stroke(r, rad, Stroke::new(1.0, stroke), StrokeKind::Inside);
        if !modern && !lit {
            let hl = Rect::from_min_size(r.min + vec2(rad * 0.6, 1.0), vec2(r.width() - rad * 1.2, 1.0));
            p.rect_filled(hl, 0.0, Color32::from_white_alpha(120));
        }
        if sty == Sty::MPad {
            let (num, sub) = label.split_once('\n').unwrap_or((label, ""));
            p.text(r.right_top() + vec2(-6.0, 5.0), Align2::RIGHT_TOP, num, FontId::proportional(fs), tcol);
            p.text(r.left_bottom() + vec2(6.0, -4.0), Align2::LEFT_BOTTOM, sub, FontId::proportional(fs * 0.6), c(0x6a, 0x6d, 0x74));
        } else if label.starts_with('@') {
            draw_symbol(&p, label, r.center(), fs, tcol);
        } else {
            p.text(r.center(), Align2::CENTER_CENTER, label, FontId::proportional(fs), tcol);
        }
        if self.st.show_map {
            if modern {
                let col = if key.is_some() { c(0x2f, 0x9e, 0x44) } else { c(0xe0, 0x31, 0x31) };
                p.rect_stroke(rect.expand(1.0), rad, Stroke::new(1.5, col), StrokeKind::Outside);
            } else if key.is_some() {
                p.circle_filled(rect.right_top() + vec2(-4.0, 4.0), 2.2, c(0x2f, 0x9e, 0x44));
            }
        }
        if let Some(k) = key {
            let tip = match km().notes.get(&k) {
                Some(n) => format!("{id}  ({},{:#x})  display: {n}", k.0, k.1),
                None => format!("{id}  ({},{:#x})", k.0, k.1),
            };
            return resp.on_hover_text(tip);
        }
        resp
    }

    fn led(&self, ui: &Ui, ctr: Pos2, diam: f32, id: &str, green: bool) {
        let p = ui.painter();
        let on = self.led_on(id);
        let r = diam * 0.5;
        if on {
            let col = if green { LED_GRN } else { LED_RED };
            p.circle_filled(ctr, r * 1.9, Color32::from_rgba_unmultiplied(col.r(), col.g(), col.b(), 40));
            p.circle_filled(ctr, r, col);
        } else {
            p.circle_filled(ctr, r, LED_OFF);
            p.circle_stroke(ctr, r, Stroke::new(0.8, Color32::from_black_alpha(160)));
        }
    }

    fn knob(&mut self, ui: &mut Ui, ctr: Pos2, r: f32, id: &str, big: bool, modern: bool) {
        let rect = Rect::from_center_size(ctr, vec2(r * 2.0, r * 2.0));
        let resp = ui.interact(rect, Id::new(("knob", id, self.st.view as u8)), Sense::click_and_drag());
        let default_v = 0.5;
        let mut v = *self.st.knobs.get(id).unwrap_or(&default_v);
        let old = v;
        if resp.dragged() {
            v = (v - resp.drag_delta().y / 175.0).clamp(0.0, 1.0);
        }
        if resp.double_clicked() {
            v = default_v;
        }
        if (v - old).abs() > f32::EPSILON {
            self.st.knobs.insert(id.to_string(), v);
            let raw = (v * 1023.0).round() as u16;
            for &(col, ch) in knob_adc(id) {
                self.ctl.adc(col, ch, raw);
            }
        }
        self.paint_knob(ui, ctr, r, -140.0 + 280.0 * v, big, modern);
        if !knob_adc(id).is_empty() {
            resp.on_hover_text(format!("{id}: {:.0}", v * 1023.0));
        } else {
            resp.on_hover_text(format!("{id} (analog only, not scanned by the firmware)"));
        }
    }

    fn paint_knob(&self, ui: &Ui, ctr: Pos2, r: f32, deg: f32, big: bool, modern: bool) {
        let p = ui.painter();
        if !modern {
            p.circle_filled(ctr + vec2(0.0, r * 0.1), r, Color32::from_black_alpha(140));
        }
        let (a, b) = if modern { (c(0x22, 0x22, 0x26), c(0x44, 0x44, 0x4a)) } else if big { (c(0x4a, 0x4a, 0x50), c(0x11, 0x11, 0x11)) } else { (c(0x3a, 0x3a, 0x40), c(0x11, 0x11, 0x11)) };
        p.circle_filled(ctr, r, a);
        p.circle_stroke(ctr, r, Stroke::new(1.2, b));
        if !modern {
            p.circle_filled(ctr + vec2(-r * 0.2, -r * 0.25), r * 0.45, Color32::from_white_alpha(28));
        }
        let ang = deg.to_radians();
        let dir = vec2(ang.sin(), -ang.cos());
        p.line_segment([ctr + dir * r * 0.32, ctr + dir * r * 0.88], Stroke::new((r * 0.12).max(2.0), c(0xf2, 0xf2, 0xf2)));
    }

    /// Encoder (VALUE dial): wheel or vertical drag.
    fn encoder(&mut self, ui: &mut Ui, ctr: Pos2, r: f32, modern: bool) {
        let rect = Rect::from_center_size(ctr, vec2(r * 2.0, r * 2.0));
        let resp = ui.interact(rect, Id::new(("enc", self.st.view as u8)), Sense::click_and_drag());
        let mut clicks = 0;
        if resp.hovered() {
            clicks = wheel_dir(ui);
        }
        if resp.dragged() {
            let id = Id::new(("encacc", self.st.view as u8));
            let mut acc: f32 = ui.data(|d| d.get_temp(id).unwrap_or(0.0));
            acc -= resp.drag_delta().y;
            let step = 10.0;
            while acc >= step {
                clicks += 1;
                acc -= step;
            }
            while acc <= -step {
                clicks -= 1;
                acc += step;
            }
            ui.data_mut(|d| d.insert_temp(id, acc));
        }
        if clicks != 0 {
            self.ctl.encoder(clicks);
            self.st.enc_angle += 15.0 * clicks as f32;
        }
        let p = ui.painter();
        let base = if modern { c(0x2a, 0x2a, 0x2e) } else { c(0x55, 0x55, 0x55) };
        p.circle_filled(ctr, r, base);
        let a0 = self.st.enc_angle.to_radians();
        for i in 0..16 {
            let a = a0 + i as f32 * std::f32::consts::TAU / 16.0;
            let d = vec2(a.sin(), -a.cos());
            p.line_segment([ctr + d * r * 0.8, ctr + d * r], Stroke::new(2.0, if i % 2 == 0 { c(0x99, 0x99, 0x99) } else { c(0x44, 0x44, 0x48) }));
        }
        p.circle_filled(ctr, r * 0.64, c(0x3c, 0x3c, 0x42));
        p.circle_filled(ctr + vec2(-r * 0.12, -r * 0.15), r * 0.3, Color32::from_white_alpha(40));
        p.line_segment([ctr + vec2(a0.sin(), -a0.cos()) * r * 0.2, ctr + vec2(a0.sin(), -a0.cos()) * r * 0.6], Stroke::new(2.0, Color32::from_white_alpha(120)));
        resp.on_hover_text("VALUE: mouse wheel / drag");
    }

    /// EFFECT selector: click / wheel steps through the 16 positions (sent as FX rotary key bits fxrot0..3).
    fn fx_knob(&mut self, ui: &mut Ui, ctr: Pos2, r: f32, modern: bool) {
        let rect = Rect::from_center_size(ctr, vec2(r * 2.0, r * 2.0));
        let resp = ui.interact(rect, Id::new(("fxknob", self.st.view as u8)), Sense::click());
        let mut code = self.st.fx_code;
        if resp.clicked() {
            code = (code + 1) & 15;
        }
        if resp.hovered() {
            match wheel_dir(ui) {
                1 => code = (code + 1) & 15,
                -1 => code = (code + 15) & 15,
                _ => {}
            }
        }
        if code != self.st.fx_code {
            self.st.fx_code = code;
            for i in 0..4 {
                if let Some(&(row, mask)) = km().map.get(&format!("fxrot{i}")) {
                    self.ctl.key(row, mask, (code >> i) & 1 == 1);
                }
            }
        }
        self.paint_knob(ui, ctr, r, self.st.fx_code as f32 * 22.5, true, modern);
        resp.on_hover_text(format!("EFFECT: {}  (click / wheel)", FXN[self.st.fx_code as usize]));
    }

    /// 16x2 dot matrix LCD with CGRAM glyphs; stretches to `rect`.
    fn lcd(&self, ui: &Ui, rect: Rect) {
        let p = ui.painter_at(rect);
        p.rect_filled(rect, 3.0, LCD_BG);
        let (cw, ch) = (640.0f32, 224.0f32);
        let (fx, fy) = (rect.width() / cw, rect.height() / ch);
        let px = cw / (16.0 * 6.0 + 1.0);
        let py = px * 1.12;
        let oy = (ch - (2.0 * 9.0 + 0.6) * py) / 2.0;
        let (dw, dh) = (px * 0.8, py * 0.78);
        let on = self.data.display_on;
        for row in 0..2usize {
            for col in 0..16usize {
                let code = self.data.lcd[row][col];
                let g = if !on {
                    [0u8; 8]
                } else if code < 16 {
                    glyph_rows(&self.data.cgram, code)
                } else if code > 32 && code < 127 {
                    ascii_rows(code)
                } else {
                    [0u8; 8]
                };
                for (yy, bits) in g.iter().enumerate() {
                    for xx in 0..5 {
                        if (bits >> (4 - xx)) & 1 == 1 {
                            let x = (col as f32 * 6.0 + xx as f32 + 0.6) * px;
                            let y = oy + (row as f32 * 9.0 + yy as f32 + row as f32 * 0.6) * py;
                            let r = Rect::from_min_size(rect.min + vec2(x * fx, y * fy), vec2(dw * fx, dh * fy));
                            p.rect_filled(r, 0.0, LCD_INK);
                        }
                    }
                }
            }
        }
    }

    /// Y touchpad (`pad`) and the vertical slider strip (`slot`; cap travels over its full height).
    fn arp(&mut self, ui: &mut Ui, pad: Rect, slot: Rect, cap_w: f32, cap_h: f32, modern: bool) {
        let p = ui.painter();
        // touchpad
        let pr = ui.interact(pad, Id::new(("arppad", self.st.view as u8)), Sense::click_and_drag());
        let down = pr.is_pointer_button_down_on();
        if down {
            if let Some(pos) = pr.interact_pointer_pos().or_else(|| ui.input(|i| i.pointer.interact_pos())) {
                self.st.pad_y = ((pos.y - pad.top()) / pad.height()).clamp(0.0, 1.0);
            }
        }
        if down != self.st.pad_touched {
            self.st.pad_touched = down;
            self.ctl.arp(down, self.st.slider);
        }
        {
            // ribbon controller: position while touched (0..~800), 1023 = untouched
            let rv = if down { (self.st.pad_y * 800.0).round() as u16 } else { 1023 };
            if rv != self.st.adc[RIBBON_ADC.0 as usize][RIBBON_ADC.1 as usize] {
                self.st.adc[RIBBON_ADC.0 as usize][RIBBON_ADC.1 as usize] = rv;
                self.ctl.adc(RIBBON_ADC.0, RIBBON_ADC.1, rv);
            }
        }
        p.rect_filled(pad, 6.0, if modern { c(0x10, 0x10, 0x12) } else { c(0xb4, 0xb2, 0xb8) });
        p.rect_stroke(pad, 6.0, Stroke::new(1.0, c(0x2a, 0x2a, 0x2e)), StrokeKind::Inside);
        let ly = pad.top() + self.st.pad_y * pad.height();
        let lcol = if down { c(0xff, 0x9a, 0x1c) } else { c(0xaa, 0xaa, 0xaa) };
        p.line_segment([pos2(pad.left() + 6.0, ly), pos2(pad.right() - 6.0, ly)], Stroke::new(3.0, lcol));
        // slider
        p.rect_filled(slot, 3.0, c(0x0e, 0x0e, 0x10));
        let hit = Rect::from_min_max(pos2(slot.center().x - cap_w * 0.5, slot.top() - cap_h * 0.5), pos2(slot.center().x + cap_w * 0.5, slot.bottom() + cap_h * 0.5));
        let sr = ui.interact(hit, Id::new(("arpslide", self.st.view as u8)), Sense::click_and_drag());
        if sr.is_pointer_button_down_on() {
            if let Some(pos) = ui.input(|i| i.pointer.interact_pos()) {
                let t = ((slot.bottom() - pos.y) / slot.height()).clamp(0.0, 1.0);
                let v = (t * 1023.0).round() as u16;
                if v != self.st.slider {
                    self.st.slider = v;
                    self.ctl.arp(self.st.pad_touched, v);
                }
            }
        }
        let cy = slot.bottom() - self.st.slider as f32 / 1023.0 * slot.height();
        let cap = Rect::from_center_size(pos2(slot.center().x, cy), vec2(cap_w, cap_h));
        p.rect_filled(cap.translate(vec2(0.0, 2.0)), 3.0, Color32::from_black_alpha(160));
        p.rect_filled(cap, 3.0, c(0xa8, 0xa8, 0xae));
        p.line_segment([cap.left_center(), cap.right_center()], Stroke::new(1.5, c(0x33, 0x33, 0x38)));
        sr.on_hover_text(format!("slider {}", self.st.slider));
    }

    // --------------------------------------------------------------------------------------------
    // Keyboard shortcuts (ui.html: Space=play Esc=stop arrows=cursor Enter=write Tab=tap Shift=SHIFT)
    // --------------------------------------------------------------------------------------------
    fn keyboard(&mut self, ui: &Ui) {
        let mut changes: Vec<(&'static str, bool)> = Vec::new();
        let (focused, shift) = ui.input(|i| (i.focused, i.modifiers.shift));
        ui.input(|i| {
            for e in &i.events {
                if let egui::Event::Key { key, pressed, repeat, .. } = e {
                    if *repeat {
                        continue;
                    }
                    let id = match key {
                        egui::Key::Space => "play",
                        egui::Key::Escape => "stop",
                        egui::Key::ArrowUp => "up",
                        egui::Key::ArrowDown => "down",
                        egui::Key::ArrowLeft => "left",
                        egui::Key::ArrowRight => "right",
                        egui::Key::Enter => "write",
                        egui::Key::Tab => "tap",
                        _ => continue,
                    };
                    changes.push((id, *pressed));
                }
            }
        });
        if shift != self.st.kdown.contains("shift") {
            changes.push(("shift", shift));
        }
        if !focused {
            let all: Vec<&'static str> = self.st.kdown.iter().copied().collect();
            for id in all {
                changes.push((id, false));
            }
        }
        for (id, down) in changes {
            let Some(&(row, mask)) = km().map.get(id) else { continue };
            if down {
                if self.st.kdown.insert(id) {
                    self.ctl.key(row, mask, true);
                }
            } else if self.st.kdown.remove(id) {
                self.ctl.key(row, mask, false);
            }
        }
    }

    fn end_frame(&mut self) {
        let stale: Vec<String> = self.st.mouse_down.iter().filter(|(_, d)| !d.seen).map(|(k, _)| k.clone()).collect();
        for id in stale {
            if let Some(d) = self.st.mouse_down.remove(&id) {
                if d.send_up && !self.st.held.contains(&id) {
                    if let Some(&(r, m)) = km().map.get(&id) {
                        self.ctl.key(r, m, false);
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------------------------------------
// show()
// ------------------------------------------------------------------------------------------------

pub fn show(ui: &mut Ui, data: &PanelData, ctl: &dyn Control, state: &mut PanelState) {
    for d in state.mouse_down.values_mut() {
        d.seen = false;
    }
    let mut env = Env { data, ctl, st: state };
    env.keyboard(ui);

    // status bar
    ui.horizontal_wrapped(|ui| {
        let label = if env.st.view == View::Modern { "View: modern" } else { "View: original" };
        if ui.button(label).clicked() {
            env.st.view = if env.st.view == View::Modern { View::Original } else { View::Modern };
        }
        ui.checkbox(&mut env.st.show_map, "show key mapping");
        let sp = if data.running { format!("x{:.2}", data.speed) } else { "paused".to_string() };
        ui.label(egui::RichText::new(sp).monospace().weak());
        if let Some(e) = &data.error {
            ui.colored_label(c(0xff, 0x87, 0x87), e);
        }
    });

    match env.st.view {
        View::Original => original_view(&mut env, ui),
        View::Modern => modern_view(&mut env, ui),
    }

    // matrix + ADC (collapsible, like ui.html)
    egui::CollapsingHeader::new("Key matrix (row = PJ pattern, column = PG bit)").show(ui, |ui| matrix(&mut env, ui));
    egui::CollapsingHeader::new("ADC inputs (4 groups x 4 channels, raw 0-1023)").show(ui, |ui| {
        ui.label("Firmware scans 4 mux groups x 4 channels: 12 knobs, arp slider (0,2), ribbon (2,2); (3,2) and (3,3) are unused.");
        let notes = [
            ("0,0", "EG Time"), ("0,1", "Depth"), ("0,2", "Arp slider"), ("0,3", "Cutoff"),
            ("1,0", "Pan"), ("1,1", "FX Edit 1"), ("1,2", "Start Pt"), ("1,3", "Resonance"),
            ("2,0", "Pitch/Glide"), ("2,1", "Speed"), ("2,2", "Ribbon (1023 = untouched)"), ("2,3", "EG Int"),
            ("3,0", "Level"), ("3,1", "FX Edit 2"),
        ];
        egui::Grid::new("adcgrid").num_columns(2).show(ui, |ui| {
            for col in 0..4usize {
                for ch in 0..4usize {
                    let key = format!("{col},{ch}");
                    let note = notes.iter().find(|n| n.0 == key).map(|n| n.1).unwrap_or("unused");
                    ui.label(format!("G{col} Ch{ch}: {note}"));
                    let mut v = env.st.adc[col][ch];
                    if ui.add(egui::Slider::new(&mut v, 0..=1023)).changed() {
                        env.st.adc[col][ch] = v;
                        env.ctl.adc(col as u8, ch as u8, v);
                    }
                    ui.end_row();
                }
            }
        });
    });
    env.end_frame();
}

fn matrix(env: &mut Env, ui: &mut Ui) {
    egui::Grid::new("matrixgrid").spacing([3.0, 3.0]).show(ui, |ui| {
        ui.label("");
        for m in MASKS {
            ui.label(format!("{m:#x}"));
        }
        ui.end_row();
        for r in 0..16u8 {
            ui.label(r.to_string());
            for m in MASKS {
                let k = (r, m);
                let name = km().rev.get(&k).cloned();
                let note = km().notes.get(&k);
                let txt = name.clone().unwrap_or_else(|| if note.is_some() { "●".into() } else { "·".into() });
                let mut b = egui::Button::new(egui::RichText::new(txt).size(10.0)).min_size(vec2(54.0, 20.0));
                if name.is_some() {
                    b = b.stroke(Stroke::new(1.0, c(0x2f, 0x9e, 0x44)));
                }
                let mut resp = ui.add(b.sense(Sense::click_and_drag()));
                if let Some(n) = note {
                    resp = resp.on_hover_text(format!("display: {n}"));
                }
                let id = format!("cell{r},{m}");
                env.edge(&id, k, resp.is_pointer_button_down_on(), false);
            }
            ui.end_row();
        }
    });
}

// ------------------------------------------------------------------------------------------------
// Original-panel view (coordinates of the 954 x 681 reference picture, scaled)
// ------------------------------------------------------------------------------------------------

fn original_view(env: &mut Env, ui: &mut Ui) {
    let w = ui.available_width().max(320.0);
    let (rect, _) = ui.allocate_exact_size(vec2(w, w * 681.0 / 954.0), Sense::hover());
    let u = w / 954.0; // coordinate unit
    let s = w / 720.0; // size unit (--s in ui.html)
    let p = ui.painter_at(rect);
    let o = rect.min;
    let pt = move |x: f32, y: f32| o + vec2(x * u, y * u);
    let rc = move |cx: f32, cy: f32, w: f32, h: f32| Rect::from_center_size(o + vec2(cx * u, cy * u), vec2(w * u, h * u));
    let tl = move |x: f32, y: f32, w: f32, h: f32| Rect::from_min_size(o + vec2(x * u, y * u), vec2(w * u, h * u));
    let fsz = move |px: f32| (px * s).max(5.5);

    // face
    p.rect_filled(rect, 16.0 * s, c(0x8d, 0x1d, 0x37));
    p.rect_filled(Rect::from_min_max(rect.min, pos2(rect.max.x, rect.min.y + rect.height() * 0.45)), 16.0 * s, c(0xa6, 0x23, 0x40));
    p.rect_filled(Rect::from_min_max(pos2(rect.min.x, rect.min.y + rect.height() * 0.4), pos2(rect.max.x, rect.min.y + rect.height() * 0.5)), 0.0, c(0x9a, 0x20, 0x3b));
    p.rect_stroke(rect, 16.0 * s, Stroke::new(2.0 * s, Color32::from_black_alpha(100)), StrokeKind::Inside);
    for (x, y) in [(62.0, 47.0), (890.0, 47.0), (62.0, 640.0), (890.0, 640.0), (477.0, 662.0), (455.0, 16.0)] {
        p.circle_filled(pt(x, y), 4.5 * u, c(0x44, 0x44, 0x48));
    }
    let txt = |x: f32, y: f32, t: &str, px: f32| {
        p.text(pt(x, y), Align2::CENTER_CENTER, t, FontId::proportional(fsz(px)), CREAM);
    };
    let txtd = |x: f32, y: f32, t: &str, px: f32| {
        p.text(pt(x, y), Align2::CENTER_CENTER, t, FontId::proportional(fsz(px)), c(0x2a, 0x0d, 0x14));
    };
    let txtl = |x: f32, y: f32, t: &str, px: f32, dark: bool| {
        p.text(pt(x, y), Align2::LEFT_CENTER, t, FontId::proportional(fsz(px)), if dark { c(0x2a, 0x0d, 0x14) } else { CREAM });
    };
    let bx = |x: f32, y: f32, w: f32, h: f32| {
        p.rect_stroke(tl(x, y, w, h), 4.0 * s, Stroke::new(1.3 * s, c(0x4a, 0x14, 0x20)), StrokeKind::Inside);
    };
    let hline = |x: f32, y: f32, w: f32| {
        p.rect_filled(tl(x, y, w, 1.2 * s / u), 0.0, c(0x4a, 0x14, 0x20));
    };
    let sled_d = 4.5 * s;

    // top connector strip
    txt(150.0, 20.0, "L/MONO  OUTPUT  R", 3.6);
    txt(246.0, 20.0, "3   INDIV. OUT   4", 3.6);
    txt(324.0, 20.0, "ST./MONO AUDIO IN", 3.6);
    txt(366.0, 30.0, "MIC  LINE", 3.6);
    txt(690.0, 20.0, "IN  MIDI  OUT   THRU", 3.6);
    txt(830.0, 20.0, "DC 12V", 3.6);
    txt(890.0, 20.0, "STANDBY  ON", 3.6);
    // logo
    txtl(62.0, 78.0, "KORG", 20.0, false);
    p.rect_stroke(rc(232.0, 78.0, 112.0, 24.0), 3.0, Stroke::new(1.6 * s, CREAM), StrokeKind::Inside);
    txt(232.0, 78.0, "ELECTRIBE", 13.0);
    txtl(312.0, 78.0, "SX", 22.0, false);
    txt(75.0, 105.0, "MASTER VOLUME", 4.6);
    txt(153.0, 105.0, "TUBE GAIN", 4.6);
    txt(262.0, 105.0, "AUDIO IN LEVEL", 4.6);
    env.knob(ui, pt(75.0, 140.0), 22.0 * u, "master", false, false);
    env.knob(ui, pt(153.0, 143.0), 22.0 * u, "mic", false, false);
    env.knob(ui, pt(262.0, 143.0), 22.0 * u, "audioin", false, false);
    // valve
    txt(480.0, 20.0, "VALVE FORCE", 7.0);
    p.rect_filled(rc(545.0, 108.0, 300.0, 160.0), 80.0 * u, c(0x1c, 0x14, 0x0e));
    p.rect_stroke(rc(545.0, 108.0, 300.0, 160.0), 80.0 * u, Stroke::new(3.0 * s, c(0x20, 0x18, 0x1b)), StrokeKind::Inside);
    for cx in [545.0 - 80.0, 545.0 + 80.0] {
        p.rect_filled(rc(cx, 112.0, 40.0, 120.0), 20.0 * u, c(0x6a, 0x52, 0x30));
        p.rect_stroke(rc(cx, 112.0, 40.0, 120.0), 20.0 * u, Stroke::new(1.0 * s, c(0xc8, 0x98, 0x50)), StrokeKind::Inside);
    }

    // display
    p.rect_filled(tl(57.0, 172.0, 383.0, 140.0), 6.0 * s, c(0xc4, 0xc0, 0xb8));
    p.rect_stroke(tl(57.0, 172.0, 383.0, 140.0), 6.0 * s, Stroke::new(2.0 * s, c(0x1d, 0x1d, 0x20)), StrokeKind::Inside);
    txtl(90.0, 188.0, "ESX-1 Music Production Sampler", 6.0, true);
    let glass = tl(88.0, 198.0, 232.0, 72.0);
    env.lcd(ui, glass);
    p.rect_stroke(glass, 3.0 * s, Stroke::new(2.0 * s, c(0x1d, 0x1d, 0x20)), StrokeKind::Outside);
    txtl(96.0, 284.0, "1  2  3  4  5  6A 6B 7A 7B  1  2  1  2", 3.8, true);
    env.btn(ui, rc(352.0, 192.0, 62.0, 20.0), "audioin_trig", "AUDIO IN TRIG", Sty::Light, fsz(4.2));
    env.btn(ui, rc(352.0, 222.0, 62.0, 20.0), "tempolock", "TEMPO LOCK", Sty::Light, fsz(4.2));
    env.btn(ui, rc(352.0, 252.0, 62.0, 20.0), "autobpm", "AUTO BPM SCAN", Sty::Light, fsz(3.9));
    txtd(352.0, 275.0, "RENAME", 3.6);
    env.btn(ui, rc(352.0, 292.0, 62.0, 18.0), "write", "WRITE", Sty::Light, fsz(5.0));
    txtd(345.0, 200.0, "BEAT", 3.6);
    env.led(ui, pt(331.0, 213.0), sled_d, "beatled", false);
    env.encoder(ui, pt(412.0, 252.0), 30.0 * u, false);
    env.btn(ui, rc(72.0, 330.0, 34.0, 26.0), "up", "@up", Sty::Dark, fsz(9.0));
    env.btn(ui, rc(72.0, 360.0, 34.0, 26.0), "down", "@down", Sty::Dark, fsz(9.0));

    // function labels + mode keys
    let cols: [(&str, f32, &[&str]); 6] = [
        ("PATTERN", 127.0, &["TEMPO", "SWING", "ROLL TYPE", "LENGTH", "BEAT", "ARPEGGIO SCALE", "COMPARE"]),
        ("SAMPLE", 186.0, &["SLICE NO.", "OUTPUT BUS", "GATE TIME", "ACCENT SW"]),
        ("MOTION DEST", 243.0, &["MOTION VALUE", "MOTION TIME", "NOTE DO.", "STEP REC"]),
        ("SONG", 300.0, &["SONG", "POSITION", "PATTERN", "NOTE OFFSET", "MUTE HOLD", "NEXT SONG"]),
        ("SAMPLE", 355.0, &["START", "END", "LOOP START", "SAMPLE TUNE", "STRETCH STEP", "AUTO SAMPLING"]),
        ("METRONOME", 418.0, &["AUDIO IN MODE", "ARP CONTROL", "CLOCK", "MIDI CH", "MEMORY", "PROTECT"]),
    ];
    for (n, x, l) in cols {
        txt(x, 318.0, n, 4.4);
        for (i, t) in l.iter().enumerate() {
            txt(x, 329.0 + i as f32 * 9.0, t, 3.3);
        }
    }
    for (id, l, x) in [("pattern", "PATTERN", 122.0), ("partedit", "PART EDIT", 181.0), ("stepedit", "STEP EDIT", 239.0), ("song", "SONG", 296.0), ("sample", "SAMPLE", 351.0), ("global", "GLOBAL", 406.0)] {
        env.btn(ui, rc(x, 382.0, 50.0, 18.0), id, l, Sty::Red, fsz(4.4));
    }

    // transport
    txt(78.0, 412.0, "ERASE", 3.8);
    txt(137.0, 412.0, "SAMPLING", 3.8);
    env.btn(ui, rc(78.0, 436.0, 52.0, 40.0), "back", "@back", Sty::Tp, fsz(15.0));
    env.btn(ui, rc(137.0, 436.0, 52.0, 40.0), "rec", "@rec", Sty::TpRec, fsz(17.0));
    env.btn(ui, rc(196.0, 436.0, 52.0, 40.0), "stop", "@stop", Sty::Tp, fsz(14.0));
    env.btn(ui, rc(264.0, 436.0, 64.0, 40.0), "play", "@play", Sty::TpPlay, fsz(15.0));
    env.btn(ui, rc(345.0, 436.0, 50.0, 40.0), "tap", "TAP", Sty::Dark, fsz(9.0));
    txt(408.0, 412.0, "REST/TIE", 3.8);
    txt(453.0, 412.0, "TRANSPOSE", 3.8);
    env.btn(ui, rc(408.0, 436.0, 34.0, 38.0), "padnote", "PART\nMUTE", Sty::Light, fsz(4.4));
    env.btn(ui, rc(453.0, 436.0, 34.0, 38.0), "solo", "SOLO", Sty::Light, fsz(5.0));

    // effect
    txt(545.0, 182.0, "EFFECT", 7.0);
    for (i, t) in FXN.iter().enumerate() {
        let a = (-90.0 + i as f32 * 22.5).to_radians();
        txt(545.0 + a.cos() * 62.0 * 1.25, 242.0 + a.sin() * 62.0, t, 2.7);
    }
    env.fx_knob(ui, pt(545.0, 242.0), 32.0 * u, false);
    txt(497.0, 297.0, "FX EDIT 1", 4.6);
    env.knob(ui, pt(497.0, 328.0), 22.0 * u, "fxc1", false, false);
    txt(582.0, 297.0, "FX EDIT 2", 4.6);
    env.knob(ui, pt(582.0, 328.0), 22.0 * u, "fxc2", false, false);
    txt(517.0, 372.0, "FX 1", 4.6);
    txt(510.0, 390.0, "FX 2", 4.6);
    txt(510.0, 408.0, "FX 3", 4.6);
    p.rect_filled(tl(560.0, 364.0, 1.2 * s / u, 50.0), 0.0, c(0x4a, 0x14, 0x20));
    env.led(ui, pt(536.0, 380.0), sled_d, "chain1", false);
    env.led(ui, pt(536.0, 399.0), sled_d, "chain2", false);
    for (i, id) in ["fx1", "fx2", "fx3"].iter().enumerate() {
        env.led(ui, pt(572.0, 372.0 + i as f32 * 19.0), sled_d, id, false);
        txt(600.0, 372.0 + i as f32 * 19.0, &format!("FX {}", i + 1), 4.2);
    }
    env.btn(ui, rc(590.0, 424.0, 66.0, 20.0), "editsel", "EDIT SELECT", Sty::Light, fsz(4.4));
    env.btn(ui, rc(512.0, 440.0, 56.0, 20.0), "fxchain", "FX CHAIN", Sty::Light, fsz(4.4));
    env.btn(ui, rc(590.0, 448.0, 66.0, 20.0), "fxmotion", "MOTION SEQ", Sty::Light, fsz(4.4));

    // part common
    bx(628.0, 62.0, 138.0, 375.0);
    txt(697.0, 63.0, "PART COMMON", 5.6);
    txt(655.0, 100.0, "PITCH/GLIDE", 4.4);
    env.knob(ui, pt(655.0, 135.0), 22.0 * u, "pitch", false, false);
    txt(733.0, 100.0, "PAN", 4.4);
    env.knob(ui, pt(733.0, 135.0), 22.0 * u, "pan", false, false);
    txt(651.0, 172.0, "EG TIME", 4.4);
    env.knob(ui, pt(655.0, 205.0), 22.0 * u, "fxtime", false, false);
    txt(733.0, 172.0, "LEVEL", 4.4);
    env.knob(ui, pt(733.0, 205.0), 22.0 * u, "level", false, false);
    txt(655.0, 250.0, "START POINT", 4.4);
    env.knob(ui, pt(655.0, 282.0), 22.0 * u, "startpoint", false, false);
    for (i, id) in ["pfx1", "pfx2", "pfx3"].iter().enumerate() {
        env.led(ui, pt(720.0, 300.0 + i as f32 * 17.0), sled_d, id, false);
        txt(742.0, 300.0 + i as f32 * 17.0, &format!("FX {}", i + 1), 4.0);
    }
    txt(640.0, 306.0, "A", 5.0);
    env.led(ui, pt(652.0, 316.0), sled_d, "ampa", false);
    txt(640.0, 334.0, "B", 5.0);
    env.led(ui, pt(652.0, 340.0), sled_d, "ampb", false);
    env.btn(ui, rc(658.0, 363.0, 52.0, 18.0), "ampeg", "AMP EG", Sty::Light, fsz(4.4));
    env.btn(ui, rc(734.0, 363.0, 56.0, 18.0), "fxselect", "FX SELECT", Sty::Light, fsz(4.4));
    env.btn(ui, rc(658.0, 392.0, 52.0, 18.0), "roll", "ROLL", Sty::Light, fsz(4.6));
    env.btn(ui, rc(734.0, 392.0, 56.0, 18.0), "fxsend", "FX SEND", Sty::Light, fsz(4.6));
    env.btn(ui, rc(658.0, 420.0, 52.0, 18.0), "reverse", "REVERSE", Sty::Light, fsz(4.4));

    // modulation
    bx(770.0, 62.0, 166.0, 225.0);
    txt(853.0, 63.0, "MODULATION", 5.6);
    txt(815.0, 100.0, "SPEED", 4.4);
    env.knob(ui, pt(815.0, 132.0), 22.0 * u, "speed", false, false);
    txt(898.0, 100.0, "DEPTH", 4.4);
    env.knob(ui, pt(898.0, 132.0), 22.0 * u, "depth", false, false);
    for (i, sym) in ["~", "/\\", "[]", "_|", "#"].iter().enumerate() {
        txt(804.0, 166.0 + i as f32 * 14.0, sym, 5.0);
        env.led(ui, pt(788.0, 166.0 + i as f32 * 14.0), sled_d, &format!("modt{i}"), false);
    }
    for (i, t) in ["PITCH", "CUTOFF", "AMP", "PAN"].iter().enumerate() {
        env.led(ui, pt(862.0, 170.0 + i as f32 * 17.0), sled_d, &format!("mod{i}"), false);
        txtl(874.0, 170.0 + i as f32 * 17.0, t, 4.4, false);
    }
    env.btn(ui, rc(835.0, 244.0, 46.0, 18.0), "modtype", "TYPE", Sty::Light, fsz(4.4));
    env.btn(ui, rc(832.0, 268.0, 56.0, 18.0), "bpmsync", "BPM SYNC", Sty::Light, fsz(4.0));
    env.btn(ui, rc(890.0, 268.0, 44.0, 18.0), "dest", "DEST", Sty::Light, fsz(4.4));
    bx(738.0, 218.0, 66.0, 62.0);
    env.led(ui, pt(752.0, 232.0), sled_d, "smooth", false);
    txtl(762.0, 232.0, "SMOOTH", 3.6, false);
    env.led(ui, pt(752.0, 248.0), sled_d, "trighold", false);
    txtl(762.0, 248.0, "TRIG HOLD", 3.6, false);
    env.btn(ui, rc(772.0, 268.0, 62.0, 16.0), "motionseq2", "MOTION SEQ", Sty::Light, fsz(3.8));

    // filter
    bx(770.0, 292.0, 166.0, 153.0);
    txt(853.0, 293.0, "FILTER", 5.6);
    txt(808.0, 322.0, "CUTOFF", 4.4);
    env.knob(ui, pt(808.0, 352.0), 20.0 * u, "cutoff", false, false);
    txt(892.0, 322.0, "RESONANCE", 4.4);
    env.knob(ui, pt(892.0, 352.0), 20.0 * u, "reso", false, false);
    txt(806.0, 382.0, "EG INT", 4.4);
    env.knob(ui, pt(806.0, 408.0), 18.0 * u, "fxin", false, false);
    env.btn(ui, rc(806.0, 438.0, 46.0, 18.0), "filtertype", "TYPE", Sty::Light, fsz(4.4));
    for (id, t, x, y) in [("flt0", "LPF", 860.0, 418.0), ("flt1", "HPF", 900.0, 418.0), ("flt2", "BPF", 860.0, 436.0), ("flt3", "BPF+", 900.0, 436.0)] {
        env.led(ui, pt(x, y), sled_d, id, false);
        txtl(x + 8.0, y, t, 4.2, false);
    }

    // lower strip
    p.rect_filled(tl(45.0, 458.0, 890.0, 208.0), 8.0 * s, Color32::from_black_alpha(34));
    p.rect_stroke(tl(45.0, 458.0, 890.0, 208.0), 8.0 * s, Stroke::new(1.4 * s, c(0x4a, 0x14, 0x20)), StrokeKind::Inside);
    txt(112.0, 470.0, "ARPEGGIATOR", 5.4);
    env.arp(ui, tl(68.0, 484.0, 76.0, 150.0), tl(160.0, 505.0, 10.0, 120.0), 54.0 * u, 26.0 * u, false);

    txt(440.0, 470.0, "DRUM PART", 5.4);
    hline(255.0, 470.0, 140.0);
    hline(488.0, 470.0, 115.0);
    for (id, l, x) in [("d1", "1/ST.", 246.0), ("d2", "2/-", 289.0), ("d3", "3/ST.", 332.0), ("d4", "4/-", 375.0), ("d5", "5", 418.0), ("d6a", "6A", 461.0), ("d6b", "6B", 504.0), ("d7a", "7A", 547.0), ("d7b", "7B", 590.0)] {
        env.btn(ui, rc(x, 498.0, 40.0, 46.0), id, l, Sty::Key, fsz(11.0));
    }
    env.btn(ui, rc(633.0, 505.0, 38.0, 22.0), "accent", "ACCENT", Sty::Light, fsz(4.2));
    txt(689.0, 470.0, "KEYBOARD PART", 4.6);
    hline(655.0, 470.0, 10.0);
    hline(724.0, 470.0, 10.0);
    env.btn(ui, rc(672.0, 498.0, 40.0, 46.0), "k1", "1", Sty::Key, fsz(11.0));
    env.btn(ui, rc(716.0, 498.0, 40.0, 46.0), "k2", "2", Sty::Key, fsz(11.0));
    txt(792.0, 470.0, "STRETCH PART", 4.6);
    hline(748.0, 470.0, 10.0);
    hline(829.0, 470.0, 14.0);
    env.btn(ui, rc(762.0, 498.0, 40.0, 46.0), "s1", "1/ST.", Sty::Key, fsz(11.0));
    env.btn(ui, rc(806.0, 498.0, 40.0, 46.0), "s2", "2/-", Sty::Key, fsz(11.0));
    env.btn(ui, rc(850.0, 498.0, 44.0, 46.0), "slice", "SLICE", Sty::Key, fsz(8.0));
    env.btn(ui, rc(904.0, 505.0, 36.0, 20.0), "arrange", "AUDIO IN", Sty::Light, fsz(3.4));
    // row 2
    env.btn(ui, rc(222.0, 556.0, 36.0, 36.0), "shift", "SHIFT", Sty::Round, fsz(5.0));
    env.btn(ui, rc(299.0, 556.0, 52.0, 26.0), "patset", "PATTERN\nSET", Sty::Dark, fsz(4.2));
    env.btn(ui, rc(367.0, 556.0, 52.0, 22.0), "option", "KEYBOARD", Sty::Dark, fsz(4.2));
    txt(414.0, 538.0, "<<", 4.0);
    txt(468.0, 538.0, ">>", 4.0);
    env.btn(ui, rc(423.0, 560.0, 40.0, 26.0), "left", "@left", Sty::Dark, fsz(9.0));
    env.btn(ui, rc(468.0, 560.0, 40.0, 26.0), "right", "@right", Sty::Dark, fsz(9.0));
    for i in 0..8 {
        let x = 506.0 + i as f32 * 26.0;
        txt(x, 545.0, &(i + 1).to_string(), 4.6);
        env.led(ui, pt(x, 563.0), sled_d, &format!("beat{i}"), true);
        env.led(ui, pt(x, 578.0), sled_d, &format!("bar{i}"), false);
    }
    let labels = [
        "LAST STEP", "MOVE DATA", "COPY PART", "COPY SOUND", "CLEAR MOTION", "CLEAR PART", "CLEAR PATTERN", "INSERT PATTERN", "DELETE PATTERN", "CLEAR SONG", "NORMALIZE",
        "TRUNCATE", "TIME SLICE", "DELETE SAMPLE", "MIDI UTILITY", "CARD",
    ];
    for i in 0..16 {
        let x = 245.0 + i as f32 * 42.7;
        env.btn(ui, rc(x, 610.0, 38.0, 46.0), &format!("step{}", i + 1), &(i + 1).to_string(), Sty::Key, fsz(12.0));
        let l = labels[i].replacen(' ', "\n", 1);
        p.text(pt(x, 648.0), Align2::CENTER_CENTER, l, FontId::proportional(fsz(3.4).max(6.0)), CREAM);
    }
}

// ------------------------------------------------------------------------------------------------
// Modern dark view (egui layout; widgets as above)
// ------------------------------------------------------------------------------------------------

const MLABEL: Color32 = Color32::from_rgb(154, 160, 168);

fn m_btn(env: &mut Env, ui: &mut Ui, id: &str, label: &str, w: f32, h: f32, sty: Sty) {
    let (rect, _) = ui.allocate_exact_size(vec2(w, h), Sense::hover());
    let fs = match sty {
        Sty::MMode => 9.0,
        Sty::MTp | Sty::MTpRec | Sty::MTpPlay => 15.0,
        Sty::MPad => 12.0,
        _ => 10.0,
    };
    env.btn(ui, rect, id, label, sty, fs);
}

fn m_knob(env: &mut Env, ui: &mut Ui, id: &str, label: &str, r: f32) {
    ui.vertical(|ui| {
        ui.set_width(r * 2.0 + 28.0);
        let (rect, _) = ui.allocate_exact_size(vec2(r * 2.0 + 28.0, r * 2.0 + 4.0), Sense::hover());
        env.knob(ui, rect.center_top() + vec2(0.0, r + 2.0), r, id, false, true);
        ui.vertical_centered(|ui| ui.label(egui::RichText::new(label.to_uppercase()).size(9.0).color(MLABEL)));
    });
}

fn m_led(env: &mut Env, ui: &mut Ui, id: &str, label: &str, green: bool) {
    ui.horizontal(|ui| {
        let (rect, _) = ui.allocate_exact_size(vec2(10.0, 10.0), Sense::hover());
        env.led(ui, rect.center(), 8.0, id, green);
        if !label.is_empty() {
            ui.label(egui::RichText::new(label).size(9.0).color(MLABEL));
        }
    });
}

fn section(ui: &mut Ui, title: &str, add: impl FnOnce(&mut Ui)) {
    egui::Frame::new().stroke(Stroke::new(1.0, c(0x2a, 0x2a, 0x2e))).corner_radius(14.0).inner_margin(egui::Margin::symmetric(10, 8)).show(ui, |ui| {
        ui.vertical(|ui| {
            ui.label(egui::RichText::new(title).size(11.0).color(MLABEL));
            add(ui);
        });
    });
}

fn modern_view(env: &mut Env, ui: &mut Ui) {
    egui::Frame::new().fill(c(0x0c, 0x0c, 0x0e)).stroke(Stroke::new(1.0, c(0x2a, 0x2a, 0x2e))).corner_radius(24.0).inner_margin(egui::Margin::same(18)).show(ui, |ui| {
        ui.visuals_mut().override_text_color = Some(c(0xcf, 0xd2, 0xd6));
        let total = ui.available_width();
        let wb = 210.0;
        let wa = ((total - wb - 40.0) * 0.52).max(380.0);
        let _wc = total - wb - wa - 40.0;
        ui.horizontal_top(|ui| {
            // ---- column A
            ui.vertical(|ui| {
                ui.set_width(wa);
                ui.horizontal(|ui| {
                    ui.add_space(wa * 0.05);
                    m_knob(env, ui, "master", "Master Volume", 24.0);
                    ui.add_space(wa * 0.08);
                    m_knob(env, ui, "mic", "Tube Gain", 24.0);
                    ui.add_space(wa * 0.08);
                    m_knob(env, ui, "audioin", "Audio In Level", 24.0);
                });
                ui.horizontal(|ui| {
                    ui.vertical(|ui| {
                        ui.add_space(70.0);
                        m_btn(env, ui, "up", "@up", 40.0, 28.0, Sty::M);
                        m_btn(env, ui, "down", "@down", 40.0, 28.0, Sty::M);
                    });
                    ui.vertical(|ui| {
                        let lw = (wa - 40.0 - 74.0 - 96.0 - 36.0).max(160.0);
                        egui::Frame::new().fill(Color32::BLACK).stroke(Stroke::new(1.0, c(0x2a, 0x2a, 0x2e))).corner_radius(6.0).inner_margin(egui::Margin::same(6)).show(ui, |ui| {
                            ui.label(egui::RichText::new("ESX-1 Music Production Sampler").size(8.0).color(c(0x6a, 0x6d, 0x74)));
                            let (rect, _) = ui.allocate_exact_size(vec2(lw, lw * 224.0 / 640.0), Sense::hover());
                            env.lcd(ui, rect);
                        });
                    });
                    ui.vertical(|ui| {
                        m_btn(env, ui, "audioin_trig", "AUDIO IN TRIG", 92.0, 24.0, Sty::M);
                        m_btn(env, ui, "tempolock", "TEMPO LOCK", 92.0, 24.0, Sty::M);
                        m_btn(env, ui, "autobpm", "AUTO BPM SCAN", 92.0, 24.0, Sty::M);
                        m_btn(env, ui, "write", "WRITE", 92.0, 24.0, Sty::M);
                    });
                    ui.vertical(|ui| {
                        m_led(env, ui, "beatled", "BEAT", true);
                        let (rect, _) = ui.allocate_exact_size(vec2(74.0, 74.0), Sense::hover());
                        env.encoder(ui, rect.center(), 34.0, true);
                        ui.label(egui::RichText::new("VALUE").size(9.0).color(MLABEL));
                    });
                });
                ui.add_space(6.0);
                let modes = [
                    ("pattern", "PATTERN", "PATTERN", "TEMPO / SWING / ROLL TYPE / LENGTH / BEAT / ARP SCALE / COMPARE"),
                    ("partedit", "PART EDIT", "SAMPLE", "SLICE NO. / OUTPUT BUS / GATE TIME / ACCENT SW"),
                    ("stepedit", "STEP EDIT", "MOTION DEST", "MOTION VALUE / MOTION TIME / NOTE DO. / STEP REC"),
                    ("song", "SONG", "SONG", "SONG / POSITION / PATTERN / NOTE OFFSET / MUTE HOLD / NEXT SONG"),
                    ("sample", "SAMPLE", "SAMPLE", "START / END / LOOP START / SAMPLE TUNE / STRETCH STEP / AUTO SAMPLING"),
                    ("global", "GLOBAL", "METRONOME", "AUDIO IN MODE / ARP CONTROL / CLOCK / MIDI CH / MEMORY / PROTECT"),
                ];
                let mw = (wa - 6.0 * 6.0) / 6.0;
                ui.horizontal(|ui| {
                    for (id, l, head, tip) in modes {
                        ui.vertical(|ui| {
                            ui.set_width(mw);
                            ui.label(egui::RichText::new(head).size(8.0).color(MLABEL));
                            let (rect, _) = ui.allocate_exact_size(vec2(mw, 28.0), Sense::hover());
                            env.btn(ui, rect, id, l, Sty::MMode, 9.0).on_hover_text(tip);
                        });
                    }
                });
                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    m_btn(env, ui, "back", "@back", 54.0, 46.0, Sty::MTp);
                    m_btn(env, ui, "rec", "@rec", 54.0, 46.0, Sty::MTpRec);
                    m_btn(env, ui, "stop", "@stop", 54.0, 46.0, Sty::MTp);
                    m_btn(env, ui, "play", "@play", 54.0, 46.0, Sty::MTpPlay);
                    m_btn(env, ui, "tap", "TAP", 54.0, 46.0, Sty::MTp);
                    ui.add_space((wa - 5.0 * 62.0 - 2.0 * 80.0).max(4.0));
                    m_btn(env, ui, "padnote", "PART MUTE", 78.0, 30.0, Sty::M);
                    m_btn(env, ui, "solo", "SOLO", 60.0, 30.0, Sty::M);
                });
            });
            // ---- column B
            ui.vertical(|ui| {
                ui.set_width(wb);
                section(ui, "EFFECT", |ui| {
                    ui.set_width(wb - 24.0);
                    ui.vertical_centered(|ui| {
                        let (rect, _) = ui.allocate_exact_size(vec2(84.0, 84.0), Sense::hover());
                        env.fx_knob(ui, rect.center(), 40.0, true);
                        ui.label(egui::RichText::new(FXN[env.st.fx_code as usize]).size(10.0).color(c(0xff, 0x9a, 0x1c)));
                    });
                    ui.horizontal(|ui| {
                        m_knob(env, ui, "fxc1", "FX Edit 1", 20.0);
                        m_knob(env, ui, "fxc2", "FX Edit 2", 20.0);
                    });
                    ui.horizontal(|ui| {
                        ui.vertical(|ui| {
                            ui.label(egui::RichText::new("FX 1").size(8.0).color(MLABEL));
                            m_led(env, ui, "chain1", "", false);
                            ui.label(egui::RichText::new("FX 2").size(8.0).color(MLABEL));
                            m_led(env, ui, "chain2", "", false);
                            ui.label(egui::RichText::new("FX 3").size(8.0).color(MLABEL));
                        });
                        ui.add_space(14.0);
                        ui.vertical(|ui| {
                            m_led(env, ui, "fx1", "FX 1", false);
                            m_led(env, ui, "fx2", "FX 2", false);
                            m_led(env, ui, "fx3", "FX 3", false);
                        });
                    });
                    ui.horizontal(|ui| {
                        ui.spacing_mut().item_spacing.x = 4.0;
                        m_btn(env, ui, "editsel", "EDIT SEL", 60.0, 26.0, Sty::M);
                        m_btn(env, ui, "fxchain", "FX CHAIN", 60.0, 26.0, Sty::M);
                        m_btn(env, ui, "fxmotion", "MOTION", 60.0, 26.0, Sty::M);
                    });
                });
            });
            // ---- column C
            ui.horizontal_top(|ui| {
                section(ui, "PART COMMON", |ui| {
                    ui.set_width(130.0);
                    ui.horizontal(|ui| {
                        m_knob(env, ui, "pitch", "Pitch/Glide", 20.0);
                        m_knob(env, ui, "pan", "Pan", 20.0);
                    });
                    ui.horizontal(|ui| {
                        m_knob(env, ui, "fxtime", "EG Time", 20.0);
                        m_knob(env, ui, "level", "Level", 20.0);
                    });
                    ui.horizontal(|ui| {
                        m_knob(env, ui, "startpoint", "Start Pt", 20.0);
                        ui.vertical(|ui| {
                            m_led(env, ui, "pfx1", "FX 1", false);
                            m_led(env, ui, "pfx2", "FX 2", false);
                            m_led(env, ui, "pfx3", "FX 3", false);
                        });
                    });
                    ui.horizontal(|ui| {
                        ui.vertical(|ui| {
                            m_led(env, ui, "ampa", "A", false);
                            m_led(env, ui, "ampb", "B", false);
                        });
                        m_btn(env, ui, "ampeg", "AMP EG", 56.0, 26.0, Sty::M);
                    });
                    m_btn(env, ui, "fxselect", "FX SELECT", 70.0, 26.0, Sty::M);
                    ui.horizontal(|ui| {
                        m_btn(env, ui, "roll", "ROLL", 54.0, 26.0, Sty::M);
                        m_btn(env, ui, "fxsend", "FX SEND", 60.0, 26.0, Sty::M);
                    });
                    m_btn(env, ui, "reverse", "REVERSE", 70.0, 26.0, Sty::M);
                });
                ui.vertical(|ui| {
                    section(ui, "MODULATION", |ui| {
                        ui.set_width(150.0);
                        ui.horizontal(|ui| {
                            m_knob(env, ui, "speed", "Speed", 20.0);
                            m_knob(env, ui, "depth", "Depth", 20.0);
                        });
                        ui.horizontal(|ui| {
                            ui.vertical(|ui| {
                                for (i, s) in ["~", "/\\", "[]", "_|", "#"].iter().enumerate() {
                                    m_led(env, ui, &format!("modt{i}"), s, false);
                                }
                            });
                            ui.vertical(|ui| {
                                for (i, s) in ["PITCH", "CUTOFF", "AMP", "PAN"].iter().enumerate() {
                                    m_led(env, ui, &format!("mod{i}"), s, false);
                                }
                            });
                        });
                        m_led(env, ui, "smooth", "SMOOTH", false);
                        m_led(env, ui, "trighold", "TRIG HOLD", false);
                        ui.horizontal(|ui| {
                            m_btn(env, ui, "motionseq2", "MOTION SEQ", 76.0, 24.0, Sty::M);
                            m_btn(env, ui, "modtype", "TYPE", 44.0, 24.0, Sty::M);
                        });
                        ui.horizontal(|ui| {
                            m_btn(env, ui, "bpmsync", "BPM SYNC", 66.0, 24.0, Sty::M);
                            m_btn(env, ui, "dest", "DEST", 44.0, 24.0, Sty::M);
                        });
                    });
                    section(ui, "FILTER", |ui| {
                        ui.set_width(150.0);
                        ui.horizontal(|ui| {
                            m_knob(env, ui, "cutoff", "Cutoff", 20.0);
                            m_knob(env, ui, "reso", "Resonance", 20.0);
                        });
                        ui.horizontal(|ui| {
                            m_knob(env, ui, "fxin", "EG Int", 20.0);
                            ui.vertical(|ui| {
                                m_led(env, ui, "flt0", "LPF", false);
                                m_led(env, ui, "flt1", "HPF", false);
                                m_led(env, ui, "flt2", "BPF", false);
                                m_led(env, ui, "flt3", "BPF+", false);
                            });
                        });
                        m_btn(env, ui, "filtertype", "TYPE", 54.0, 24.0, Sty::M);
                    });
                });
            });
        });
        ui.separator();
        // ---- bottom row
        ui.horizontal_top(|ui| {
            ui.vertical(|ui| {
                ui.label(egui::RichText::new("ARPEGGIATOR").size(11.0).color(MLABEL));
                let (rect, _) = ui.allocate_exact_size(vec2(130.0, 210.0), Sense::hover());
                let pad = Rect::from_min_size(rect.min, vec2(84.0, 210.0));
                let slot = Rect::from_min_size(rect.min + vec2(102.0, 8.0), vec2(8.0, 194.0));
                env.arp(ui, pad, slot, 26.0, 16.0, true);
            });
            ui.add_space(14.0);
            ui.vertical(|ui| {
                ui.horizontal(|ui| {
                    ui.vertical(|ui| {
                        ui.label(egui::RichText::new("DRUM PART").size(9.0).color(MLABEL));
                        ui.horizontal(|ui| {
                            ui.spacing_mut().item_spacing.x = 5.0;
                            for (id, l) in [("d1", "1/ST."), ("d2", "2/-"), ("d3", "3/ST."), ("d4", "4/-"), ("d5", "5"), ("d6a", "6A"), ("d6b", "6B"), ("d7a", "7A"), ("d7b", "7B")] {
                                m_btn(env, ui, id, l, 46.0, 46.0, Sty::M);
                            }
                            m_btn(env, ui, "accent", "ACCENT", 50.0, 34.0, Sty::M);
                        });
                    });
                    ui.vertical(|ui| {
                        ui.label(egui::RichText::new("KEYBOARD PART").size(9.0).color(MLABEL));
                        ui.horizontal(|ui| {
                            ui.spacing_mut().item_spacing.x = 5.0;
                            m_btn(env, ui, "k1", "1", 46.0, 46.0, Sty::M);
                            m_btn(env, ui, "k2", "2", 46.0, 46.0, Sty::M);
                        });
                    });
                    ui.vertical(|ui| {
                        ui.label(egui::RichText::new("STRETCH PART").size(9.0).color(MLABEL));
                        ui.horizontal(|ui| {
                            ui.spacing_mut().item_spacing.x = 5.0;
                            m_btn(env, ui, "s1", "1/ST.", 46.0, 46.0, Sty::M);
                            m_btn(env, ui, "s2", "2/-", 46.0, 46.0, Sty::M);
                            m_btn(env, ui, "slice", "SLICE", 46.0, 46.0, Sty::M);
                            m_btn(env, ui, "arrange", "AUDIO IN", 50.0, 34.0, Sty::M);
                        });
                    });
                });
                ui.horizontal(|ui| {
                    m_btn(env, ui, "shift", "SHIFT", 40.0, 40.0, Sty::MRound);
                    m_btn(env, ui, "patset", "PATTERN SET", 80.0, 30.0, Sty::M);
                    m_btn(env, ui, "option", "KEYBOARD", 70.0, 30.0, Sty::M);
                    m_btn(env, ui, "left", "@left", 40.0, 30.0, Sty::M);
                    m_btn(env, ui, "right", "@right", 40.0, 30.0, Sty::M);
                    ui.add_space(12.0);
                    for i in 0..8 {
                        ui.vertical(|ui| {
                            ui.set_width(24.0);
                            ui.label(egui::RichText::new((i + 1).to_string()).size(8.0).color(MLABEL));
                            m_led(env, ui, &format!("beat{i}"), "", true);
                            m_led(env, ui, &format!("bar{i}"), "", false);
                        });
                    }
                });
                let labels = [
                    "LAST STEP", "MOVE DATA", "COPY PART", "COPY SOUND", "CLEAR MOTION", "CLEAR PART", "CLEAR PATTERN", "INSERT PATTERN", "DELETE PATTERN", "CLEAR SONG",
                    "NORMALIZE", "TRUNCATE", "TIME SLICE", "DELETE SAMPLE", "MIDI UTILITY", "CARD",
                ];
                let avail = ui.available_width();
                let bw = ((avail - 15.0 * 5.0) / 16.0).clamp(40.0, 90.0);
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 5.0;
                    for i in 0..16 {
                        let (rect, _) = ui.allocate_exact_size(vec2(bw, 62.0), Sense::hover());
                        env.btn(ui, rect, &format!("step{}", i + 1), &format!("{}\n{}", i + 1, labels[i]), Sty::MPad, 12.0);
                    }
                });
            });
        });
    });
}
