#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Browser front end of the ESX-1 emulator (Python standard library only).

    python server.py [--port 8765]        then open http://127.0.0.1:8765/

The emulator runs in a background thread. The page polls /state (display text, custom characters, counters),
sends key presses to /key and starts the unit with /boot. Needs `out_flash.bin` and `out_nand.bin` (written by
`run_update.py`) for a normal start; the update mode builds a card from the files given in `--fw`.
"""
import os
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import container
from rmachine import RMachine

HERE = Path(__file__).resolve().parent


class Unit:
    """One emulated ESX-1 plus the thread that runs it."""

    def __init__(self, fw_dir):
        self.fw = Path(fw_dir)
        self.lock = threading.Lock()
        self.m = None
        self.mode = "off"
        self.running = False
        self.instr = 0
        self.t0 = 0.0
        self.error = None
        self.thread = None
        self.stop = threading.Event()
        self.turn = 0
        self.audio_buf = []                                 # interleaved stereo int16 from the DSP audio serial port
        self.audio_seq = 0
        self.speed = 1.0                                    # emulierte Sekunden pro echte Sekunde (1.0 = Echtzeit)
        self._sp_t, self._sp_i = time.time(), 0
        self.touched = False                                # Arpeggiator-Touchpad gedrückt?
        self.slider = 512                                   # Arpeggiator-Schieber 0..1023 (512 = Grundnote)
        self.card_cache = HERE / "card.cache"

    # ----------------------------------------------------------------- start modes
    def _card(self):
        import smartmedia
        if self.card_cache.exists():
            return self.card_cache.read_bytes()
        files = [(n, (self.fw / n).read_bytes()) for n in ("ESX0101F.BFS", "ESX0102N.BSS", "ESX0102D.BDS")]
        data = smartmedia.build_card(files)
        self.card_cache.write_bytes(data)
        return data

    def boot(self, mode):
        self.shutdown()
        import smartmedia
        try:
            if mode == "normal":
                flash = (HERE / "out_flash.bin").read_bytes()
                fac = HERE / "out_nand_factory.bin"
                nand = (fac if fac.exists() else HERE / "out_nand.bin").read_bytes()
                m = RMachine(flash)
                m.set_nand(1, nand, 0x98, 0x75)
            elif mode == "update":
                flash = container.payload((self.fw / "ESX0101F.BFS").read_bytes())
                m = RMachine(flash, card_present=True)
                m.set_nand(0, self._card(), 0xEC, 0x73)
                m.set_nand(1, smartmedia.formatted_blank(32), 0x98, 0x75)
                m.keys.pressed = {(8, 0x10), (8, 0x80)}          # Cursor up + down held at power-on
            else:
                raise ValueError(mode)
        except Exception as e:                                    # missing images etc.
            self.error = f"{type(e).__name__}: {e}"
            return
        m.fast_delays = True
        if os.environ.get('ESX_THREADS') == '0':
            m.threaded(False)
        self.error = None
        self._apply_arp(m)
        old, self.m, self.mode, self.instr = self.m, m, mode, 0
        if old is not None:
            try: old.close()
            except Exception: pass
        self.t0 = time.time()
        self._sp_t, self._sp_i, self.speed = self.t0, 0, 0.0
        self.stop.clear()
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def shutdown(self):
        if self.thread and self.thread.is_alive():
            self.stop.set()
            self.thread.join(5)
        self.running = False
        self.mode = "off"

    def _loop(self):
        m = self.m
        try:
            while not self.stop.is_set():
                if self.running:
                    if self.turn:
                        c, self.turn = self.turn, 0
                        m.turn(c)
                    self.instr += m.run(1_000_000)
                    now = time.time()
                    if now - self._sp_t >= 1.0:
                        self.speed = round((self.instr - self._sp_i) / 96e6 / (now - self._sp_t), 3)
                        self._sp_t, self._sp_i = now, self.instr
                    a = m.dsp.audio(1 << 16)
                    if a:
                        self.audio_buf.extend(a)
                        self.audio_seq += len(a)
                        if len(self.audio_buf) > 176400:
                            del self.audio_buf[:len(self.audio_buf) - 176400]
                else:
                    time.sleep(0.05)
        except Exception as e:
            self.error = f"{type(e).__name__}: {e} bei pc=0x{m.cpu.pc:08x}"
            self.running = False

    # ----------------------------------------------------------------- views
    def state(self):
        m = self.m
        out = {"mode": self.mode, "running": self.running, "error": self.error, "instr": self.instr, "speed": self.speed,
               "seconds": round(time.time() - self.t0, 1) if m else 0}
        if m:
            l = m.lcd
            out.update(lines=[bytes(l.ddram[:40]).hex(), bytes(l.ddram[40:80]).hex()], cgram=bytes(l.cgram).hex(),
                       display_on=l.display_on, pc=f"0x{m.cpu.pc:08x}", sleeping=m.cpu.sleeping,
                       irq=m.tmu.underflows[0], scale=m.tmu.scale, illegal=len(m.cpu.illegal_log),
                       pressed=[list(k) for k in sorted(m.keys.pressed)])
            out["dsp"] = m.dsp.summary()
            try:
                p = m.bus.read32(0x0C0B3D08)               # pointer to the 13-byte LED column table
                if 0x0C000000 <= p < 0x0E000000:
                    out["leds"] = bytes(m.bus.peek(p, 13)).hex()
            except Exception:
                pass
        return out

    def _apply_arp(self, m=None):
        """Schieber = ADC (col 0, ch 2); Ribbon/Touchpad = ADC (col 2, ch 2), siehe scratch/adc*.py."""
        m = m or self.m
        if not m:
            return
        m.set_adc_in(0, 2, self.slider)                       # Schieber = ADC (mux col 0, ch 2)
        m.set_adc_in(2, 2, 400 if self.touched else 1023)    # Ribbon = ADC (2, 2): <~832 beruehrt (Position), 1023 = nicht beruehrt

    def key(self, row, mask, down):
        if not self.m:
            return
        k = (row, mask)
        s = set(self.m.keys.pressed)
        (s.add if down else s.discard)(k)
        self.m.keys.pressed = s


def make_handler(unit):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body).encode()
            elif isinstance(body, str):
                body = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, (HERE / "ui.html").read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/state":
                self._send(200, unit.state())
            elif self.path.startswith("/audio"):
                import base64, array
                since = 0
                if "since=" in self.path:
                    since = int(self.path.split("since=")[1].split("&")[0] or 0)
                with unit.lock:
                    seq = unit.audio_seq
                    n = max(0, min(len(unit.audio_buf), seq - since))
                    chunk = unit.audio_buf[len(unit.audio_buf) - n:] if n else []
                arr = array.array("h", chunk)
                self._send(200, {"seq": seq, "rate": 44100, "speed": unit.speed, "channels": 2, "pcm": base64.b64encode(arr.tobytes()).decode()})
            elif self.path == "/notes":
                p = HERE / "keymap_notes.json"
                self._send(200, p.read_bytes() if p.exists() else b"{}")
            elif self.path == "/keymap":
                p = HERE / "keymap.json"
                self._send(200, p.read_bytes() if p.exists() else b"{}")
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0) or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._send(400, {"error": "bad json"})
            if self.path == "/key":
                unit.key(int(data["row"]), int(data["mask"]), bool(data["down"]))
            elif self.path == "/boot":
                unit.boot(data.get("mode", "normal"))
            elif self.path == "/keymap":
                (HERE / "keymap.json").write_text(json.dumps(data, indent=1))
            elif self.path == "/adc":
                if unit.m:                                   # {"col":idx,"ch":0..3,"value":0..1023}
                    unit.m.set_adc_in(int(data["col"]), int(data["ch"]), int(data["value"]))
            elif self.path == "/arp":                        # {"touched":bool,"slider":0..1023}
                if "touched" in data:
                    unit.touched = bool(data["touched"])
                if "slider" in data:
                    unit.slider = max(0, min(1023, int(data["slider"])))
                unit._apply_arp()
            elif self.path == "/turn":
                if unit.m:
                    unit.turn += int(data.get("clicks", 0))
            elif self.path == "/scale":
                if unit.m:
                    unit.m.tmu.scale = float(data.get("scale", 1))
            elif self.path == "/pause":
                unit.running = not unit.running if unit.m else False
            elif self.path == "/off":
                unit.shutdown()
            else:
                return self._send(404, {"error": "not found"})
            self._send(200, unit.state())
    return H


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--fw", default=str(HERE.parent / "factory-firmware"))
    a = ap.parse_args()
    unit = Unit(a.fw)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(unit))
    print(f"ESX-1 Emulator: http://127.0.0.1:{a.port}/   (Strg+C beendet)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        unit.shutdown()


if __name__ == "__main__":
    main()
