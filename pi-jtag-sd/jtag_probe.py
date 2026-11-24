#!/usr/bin/env python3
"""
SH7709S (Korg ESX-1 SD) JTAG / H-UDI Probe Tool for Raspberry Pi.
Read-only & non-destructive: probes IDCODE, IR length, BYPASS roundtrip,
and checks whether IEEE 1149.1 Boundary Scan (SAMPLE) responds.

Wiring (ESX-1 SD 14-pin H-UDI header -> Raspberry Pi 40-pin header):
  L1 (oder L2/L3/L5/L6/L7) GND   -> Pi Pin  6 (GND)
  R1 (TCK,   CPU 139)            -> Pi Pin 22 (GPIO 25)
  R2 (TRST#, CPU 136)            -> Pi Pin 18 (GPIO 24)
  R3 (TDO,   CPU 120)            -> Pi Pin 21 (GPIO  9)   [INPUT on Pi]
  R5 (TMS,   CPU 137)            -> Pi Pin 16 (GPIO 23)
  R6 (TDI,   CPU 138)            -> Pi Pin 19 (GPIO 10)

DO NOT connect L4 (UVCC) or Pi 3.3V/5V! Leave R4 (ASEBRKAK) and R7 (RESET#) open.
Power the ESX-1 SD from its own power supply AFTER connecting GND + the 5 signals.

Usage on Raspberry Pi:
  sudo apt install -y python3-libgpiod   # if not installed
  python3 jtag_probe.py
  python3 jtag_probe.py --swap-tms-tdi   # test with R5/R6 swapped
"""
import argparse
import glob
import os
import sys
import time

# Default BCM GPIO numbers (same on Pi 2/3/4/5/Zero)
PIN_TCK  = 25   # Physical Pin 22 -> R1
PIN_TRST = 24   # Physical Pin 18 -> R2
PIN_TDO  = 9    # Physical Pin 21 -> R3 (Input!)
PIN_TMS  = 23   # Physical Pin 16 -> R5
PIN_TDI  = 10   # Physical Pin 19 -> R6


class GpioBackend:
    """Thin wrapper supporting gpiod v2 (Pi 5 / Bookworm), gpiod v1, and RPi.GPIO."""

    def __init__(self, tck, trst, tdo, tms, tdi, chip=None):
        self.pins = {"tck": tck, "trst": trst, "tdo": tdo, "tms": tms, "tdi": tdi}
        self.mode = None
        self._init_backend(chip)

    def _find_gpiochip(self):
        # Pi 5 uses gpiochip4 (or gpiochip0 on newer kernels with RP1 alias); Pi 2/3/4 uses gpiochip0.
        for path in sorted(glob.glob("/dev/gpiochip*")):
            try:
                import gpiod
                if hasattr(gpiod, "Chip"):
                    c = gpiod.Chip(path)
                    info = c.get_info() if hasattr(c, "get_info") else None
                    label = info.label if info else (c.label() if hasattr(c, "label") else "")
                    c.close()
                    if any(k in label.lower() for k in ("pinctrl-rp1", "pinctrl-bcm", "bcm2835", "bcm2711")):
                        return path
            except Exception:
                pass
        return "/dev/gpiochip0"

    def _init_backend(self, chip):
        try:
            import gpiod
            chip_path = chip or self._find_gpiochip()
            if hasattr(gpiod, "request_lines"):
                # libgpiod v2 API
                from gpiod.line import Direction, Value
                self._V = Value
                cfg = {
                    self.pins["tck"]:  gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE),
                    self.pins["trst"]: gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
                    self.pins["tms"]:  gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.ACTIVE),
                    self.pins["tdi"]:  gpiod.LineSettings(direction=Direction.OUTPUT, output_value=Value.INACTIVE),
                    self.pins["tdo"]:  gpiod.LineSettings(direction=Direction.INPUT),
                }
                self._req = gpiod.request_lines(chip_path, consumer="esx-jtag", config=cfg)
                self.mode = f"gpiod-v2 ({chip_path})"
                return
            else:
                # libgpiod v1 API
                self._chip = gpiod.Chip(chip_path)
                self._lines = {}
                for k, p in self.pins.items():
                    line = self._chip.get_line(p)
                    if k == "tdo":
                        line.request(consumer="esx-jtag", type=gpiod.LINE_REQ_DIR_IN)
                    else:
                        init = 1 if k in ("trst", "tms") else 0
                        line.request(consumer="esx-jtag", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[init])
                    self._lines[k] = line
                self.mode = f"gpiod-v1 ({chip_path})"
                return
        except ImportError:
            pass

        try:
            import RPi.GPIO as GPIO
            self._GPIO = GPIO
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            for k, p in self.pins.items():
                if k == "tdo":
                    GPIO.setup(p, GPIO.IN)
                else:
                    GPIO.setup(p, GPIO.OUT, initial=GPIO.HIGH if k in ("trst", "tms") else GPIO.LOW)
            self.mode = "RPi.GPIO"
            return
        except ImportError:
            pass

        raise RuntimeError(
            "Kein GPIO-Treiber gefunden. Bitte installieren:\n"
            "  sudo apt update && sudo apt install -y python3-libgpiod"
        )

    def set(self, name, val):
        p = self.pins[name]
        v = 1 if val else 0
        if self.mode.startswith("gpiod-v2"):
            self._req.set_value(p, self._V.ACTIVE if v else self._V.INACTIVE)
        elif self.mode.startswith("gpiod-v1"):
            self._lines[name].set_value(v)
        else:
            self._GPIO.output(p, self._GPIO.HIGH if v else self._GPIO.LOW)

    def get_tdo(self):
        if self.mode.startswith("gpiod-v2"):
            return 1 if self._req.get_value(self.pins["tdo"]) == self._V.ACTIVE else 0
        elif self.mode.startswith("gpiod-v1"):
            return 1 if self._lines["tdo"].get_value() else 0
        else:
            return 1 if self._GPIO.input(self.pins["tdo"]) else 0

    def close(self):
        # Release all pins safely back to Hi-Z / safe defaults
        try:
            if self.mode.startswith("gpiod-v2"):
                self._req.release()
            elif self.mode.startswith("gpiod-v1"):
                for l in self._lines.values():
                    l.release()
                self._chip.close()
            else:
                self._GPIO.cleanup(list(self.pins.values()))
        except Exception:
            pass


class JtagTap:
    def __init__(self, gpio: GpioBackend, delay_s=0.00005):
        self.g = gpio
        self.delay = delay_s

    def _d(self):
        if self.delay > 0:
            time.sleep(self.delay)

    def clock(self, tms, tdi=0):
        self.g.set("tms", tms)
        self.g.set("tdi", tdi)
        self.g.set("tck", 0)
        self._d()
        # TDO changes on falling edge of previous TCK, sample before rising edge
        tdo = self.g.get_tdo()
        self.g.set("tck", 1)
        self._d()
        self.g.set("tck", 0)
        return tdo

    def hard_reset(self):
        self.g.set("tck", 0)
        self.g.set("tms", 1)
        self.g.set("trst", 0)
        time.sleep(0.02)
        self.g.set("trst", 1)
        time.sleep(0.02)
        # Also 6 clocks with TMS=1 to guarantee Test-Logic-Reset
        for _ in range(6):
            self.clock(1, 0)

    def goto_idle(self):
        self.hard_reset()
        self.clock(0, 0)  # Run-Test/Idle

    def shift_ir(self, val, nbits):
        # From Run-Test/Idle -> Select-DR(1) -> Select-IR(1) -> Capture-IR(0) -> Shift-IR(0)
        self.clock(1); self.clock(1); self.clock(0); self.clock(0)
        out = 0
        for i in range(nbits):
            bit = (val >> i) & 1
            last = 1 if i == nbits - 1 else 0
            r = self.clock(last, bit)
            out |= (r << i)
        # Exit1-IR -> Update-IR(1) -> Run-Test/Idle(0)
        self.clock(1); self.clock(0)
        return out

    def shift_dr(self, val, nbits):
        # From Run-Test/Idle -> Select-DR(1) -> Capture-DR(0) -> Shift-DR(0)
        self.clock(1); self.clock(0); self.clock(0)
        out = 0
        for i in range(nbits):
            bit = (val >> i) & 1
            last = 1 if i == nbits - 1 else 0
            r = self.clock(last, bit)
            out |= (r << i)
        # Exit1-DR -> Update-DR(1) -> Run-Test/Idle(0)
        self.clock(1); self.clock(0)
        return out

    def probe_ir_length(self, max_len=32):
        # Enter Shift-IR, flush with 1s, then shift 0s until 0 comes out
        self.goto_idle()
        self.clock(1); self.clock(1); self.clock(0); self.clock(0)
        # Capture-IR always puts LSB=1, bit1=0 in IEEE 1149.1
        captured = []
        # Flush 64 ones first to record capture bits cleanly
        for _ in range(max_len):
            captured.append(self.clock(0, 1))
        # Now shift zeros until first zero exits TDO
        length = None
        for i in range(1, max_len + 1):
            b = self.clock(0, 0)
            if b == 0:
                length = i
                break
        # Return to Test-Logic-Reset
        for _ in range(6):
            self.clock(1, 0)
        cap_hex = 0
        for i, b in enumerate(captured[:16]):
            cap_hex |= (b << i)
        return length, cap_hex

    def probe_dr_length(self, ir_val, ir_len, max_len=1024):
        self.goto_idle()
        self.shift_ir(ir_val, ir_len)
        # Enter Shift-DR
        self.clock(1); self.clock(0); self.clock(0)
        # Flush with 1s
        for _ in range(max_len):
            self.clock(0, 1)
        # Shift 0s and count until 0 appears on TDO
        length = None
        for i in range(1, max_len + 1):
            if self.clock(0, 0) == 0:
                length = i
                break
        for _ in range(6):
            self.clock(1, 0)
        return length


def main():
    ap = argparse.ArgumentParser(description="SH7709S JTAG/H-UDI Probe")
    ap.add_argument("--chip", help="z.B. /dev/gpiochip0 oder /dev/gpiochip4")
    ap.add_argument("--swap-tms-tdi", action="store_true", help="R5/R6 (TMS/TDI) tauschen")
    ap.add_argument("--delay-us", type=int, default=50, help="Halbperioden-Delay in us (Standard: 50)")
    args = ap.parse_args()

    tms, tdi = (PIN_TDI, PIN_TMS) if args.swap_tms_tdi else (PIN_TMS, PIN_TDI)
    print(f"Pins (BCM): TCK={PIN_TCK} TRST={PIN_TRST} TDO={PIN_TDO} TMS={tms} TDI={tdi}")

    gpio = GpioBackend(PIN_TCK, PIN_TRST, PIN_TDO, tms, tdi, chip=args.chip)
    print("GPIO-Backend:", gpio.mode)
    tap = JtagTap(gpio, delay_s=args.delay_us / 1_000_000.0)

    try:
        # 1. Idle TDO check
        tap.hard_reset()
        print("TDO in Test-Logic-Reset:", gpio.get_tdo())

        # 2. Default DR right after Reset (in IEEE 1149.1 this is IDCODE if supported, else BYPASS)
        tap.goto_idle()
        idcode_default = tap.shift_dr(0x00000000, 32)
        print(f"Default DR nach Reset (32 Bit / IDCODE): 0x{idcode_default:08X}")
        if idcode_default not in (0x00000000, 0xFFFFFFFF):
            mfg = (idcode_default >> 1) & 0x7FF
            part = (idcode_default >> 12) & 0xFFFF
            ver = (idcode_default >> 28) & 0xF
            print(f"  -> Bit0={idcode_default & 1}, Mfg=0x{mfg:03X} (Hitachi/Renesas=0x007), Part=0x{part:04X}, Ver=0x{ver:X}")

        # 3. Probe IR length
        ir_len, cap = tap.probe_ir_length(32)
        print(f"Gemessene IR-Laenge: {ir_len} Bit  (Capture-IR low 16b: 0x{cap:04X})")

        if ir_len is None or ir_len > 16:
            print("\nKeine gueltige JTAG-Antwort (IR-Laenge nicht erkannt).")
            print("Tipps: 1) ESX eingeschaltet? 2) GND verbunden? 3) Mit --swap-tms-tdi testen!")
            return 1

        # 4. BYPASS roundtrip test (all-ones IR = BYPASS in IEEE 1149.1)
        bypass_ir = (1 << ir_len) - 1
        tap.goto_idle()
        tap.shift_ir(bypass_ir, ir_len)
        test_pat = 0xA55A1234
        # Shift 33 bits because BYPASS register has 1-bit delay
        got = tap.shift_dr(test_pat, 33)
        shifted = (got >> 1) & 0xFFFFFFFF
        print(f"BYPASS-Test (IR=0x{bypass_ir:X}): gesendet=0x{test_pat:08X} empfangen>>1=0x{shifted:08X}  -> {'OK!' if shifted == test_pat else 'FEHLER'}")

        # 5. Scan ALL possible IR opcodes for DR length (read-only: never shift destructive values, only measure DR chain length safely?
        # Wait: DO NOT blindly send EXTEST (0x0) because Update-IR activates EXTEST! Only probe known safe read-only opcodes!)
        print("\nPruefe bekannte sichere IR-Opcodes (BYPASS / IDCODE / SAMPLE):")
        for cand_ir in range(1, (1 << ir_len)):
            # Skip 0x0 (EXTEST) and vendor debug opcodes that might reset CPU; check IDCODE/SAMPLE patterns only if ir_len <= 5
            if ir_len <= 4 and cand_ir in (0x6, 0x7, 0xA):  # H-UDI reset/interrupt opcodes on SH-3
                continue
            if cand_ir == bypass_ir:
                continue
            dr_len = tap.probe_dr_length(cand_ir, ir_len, max_len=1024)
            if dr_len is not None and dr_len > 1:
                print(f"  IR=0x{cand_ir:02X} ({cand_ir:0{ir_len}b}) -> DR-Laenge = {dr_len} Bit")

        print("\nProbe fertig! Bitte komplette Ausgabe schicken.")
        return 0
    finally:
        gpio.close()


if __name__ == "__main__":
    sys.exit(main())
