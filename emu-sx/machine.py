# SPDX-License-Identifier: GPL-2.0-only
"""The ESX-1 as the emulator builds it: SH7709, flash, SDRAM and the devices around them."""
from sh3 import SH3
from bus import Bus, Region
from sh7709 import RegFile, SCIF, Ports, TMU, ExcRegs
from lcd import HD44780
from norflash import NorFlash
from keys import KeyMatrix
from nand import Chip, NandBus

FLASH_SIZE = 0x400000


class Machine:
    def __init__(self, flash_image, sdram_mb=32, nand_id=0x73):
        self.bus = bus = Bus()
        self.flash = bus.add_region(Region(0, FLASH_SIZE, flash_image, writable=False, name="flash"))
        self.nor = NorFlash(self.flash)
        self.sdram = bus.add_region(Region(0x0C000000, sdram_mb << 20, name="sdram"))
        self.cpu = SH3(bus)
        self.ports = Ports()
        self.scif = SCIF()
        self.lcd = HD44780(self.ports)
        self.keys = KeyMatrix(self.ports, bus, 0x0C00A170)   # row table, copied from flash 0xC7F0 at start
        self.ports.inputs[0x0400012E] = lambda: self.ports.v.get(0x0400012E, 0) & ~0x10 | (0x10 if self.ph4 else 0)
        self.ph4 = 0
        bus.add_device(0x04000150, 0x04000170, self.scif)
        bus.add_device(0x04000100, 0x04000140, self.ports)
        self.onchip = RegFile(0xFFFFFE00, 0x100000000, "onchip")
        bus.add_device(0xFFFFFE00, 0x100000000, self.onchip)
        self.tmu = TMU(self.onchip)
        bus.add_device(self.tmu.lo, self.tmu.hi, self.tmu, first=True)
        self.cpu.irq = self.tmu.pending
        self.exc = ExcRegs(self.cpu)
        bus.add_device(0xFFFFFFD0, 0xFFFFFFDC, self.exc, first=True)
        bus.add_device(0x04000000, 0x04000004, self.exc, first=True)
        self.misc = RegFile(0x04000000, 0x04000200, "onchip2")
        bus.add_device(0x04000000, 0x04000100, self.misc)
        bus.add_device(0x04000170, 0x04000200, self.misc)
        self.nand_chips = {0: Chip(0xEC, nand_id, 16)}
        self.nand = NandBus(self.ports, self.nand_chips)
        bus.add_device(0x14000000, 0x14000001, self.nand)
        self.ext = RegFile(0x10000000, 0x1C000000, "external")
        bus.add_device(0x10000000, 0x1C000000, self.ext)

    DELAY_FN = 0x0C009B50      # busy-wait helper of the boot flash (copied to SDRAM at start): same effect as `rts`

    CHUNK = 256

    def run(self, n):
        """Run n instructions. Timers advance and interrupts are taken between chunks of CHUNK instructions; while the CPU
        sleeps, time jumps to the next timer event. With `fast_delays`, the boot flash's busy-wait helper is replaced by `rts`."""
        if self.fast_delays and not self._patched and self.bus.read16(self.DELAY_FN) == 0x7FFC:
            self.bus.write16(self.DELAY_FN, 0x000B)
            self.bus.write16(self.DELAY_FN + 2, 0x0009)
            self._patched = True
        cpu, tmu = self.cpu, self.tmu
        done = 0
        while done < n:
            if cpu.sleeping:
                step = tmu.next_event_instrs()
                step = max(1, int(step) + 1) if step is not None else n - done
                tmu.advance(step)
                done += step
            else:
                step = min(self.CHUNK, n - done)
                step = cpu.run(step)
                tmu.advance(step)
                done += step
            cpu.sleeping = cpu.sleeping and tmu.pending(cpu.sr & 0xF0) is None
            cpu.check_irq()
        return done

    fast_delays = False
    _patched = False
