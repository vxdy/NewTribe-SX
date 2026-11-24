# SPDX-License-Identifier: GPL-2.0-only
"""Panel key matrix: PJ (0x04000130) bits 7..4 select a row, PG (0x0400012C) is read back with a 0 bit per pressed key."""

PJ, PG = 0x04000130, 0x0400012C


class KeyMatrix:
    def __init__(self, ports, bus, table_addr):
        self.ports, self.bus, self.table = ports, bus, table_addr
        self.fixed = {(6, 1)}                # (row 6, mask 1) reads as pressed on a real unit; without it the boot flash takes a service path
        self.pressed = set()                 # {(row_index, mask)}
        ports.inputs[PG] = self.read_pg

    def row_code(self, idx):
        return self.bus.read8(self.table + idx) & 0x0F

    def read_pg(self):
        sel = (self.ports.v.get(PJ, 0) >> 4) & 0x0F
        v = 0xFF
        for row, mask in self.pressed | self.fixed:
            if self.row_code(row) == sel:
                v &= ~mask & 0xFF
        return v
