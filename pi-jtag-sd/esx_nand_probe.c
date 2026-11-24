/*
 * esx_nand_probe.c - Diagnostic read-only NAND ID probe over SH7709S JTAG EXTEST
 * Only issues 0xFF (RESET) and 0x90 (READ ID). /CS0 (NOR) is hard-locked HIGH.
 */
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define PIN_TCK   25
#define PIN_TRST  24
#define PIN_TDO    9
#define PIN_TMS   23
#define PIN_TDI   10
#define BSR_LEN   339
#define IR_EXTEST 0x0FFF
#define IR_SAMPLE 0x4FFF
#define IR_BYPASS 0xFFFF

static volatile uint32_t *gpio_regs = NULL;
static int g_delay = 25;

static inline void tiny_delay(void) {
    for (volatile int i = 0; i < g_delay; i++) __asm__ volatile("" ::: "memory");
}
static inline void gpio_set(int pin, int val) {
    if (val) gpio_regs[7] = (1u << pin); else gpio_regs[10] = (1u << pin);
}
static void gpio_mode(int pin, int is_out) {
    int reg = pin / 10, shift = (pin % 10) * 3;
    uint32_t v = gpio_regs[reg]; v &= ~(7u << shift); if (is_out) v |= (1u << shift); gpio_regs[reg] = v;
}
static int gpio_init(void) {
    int fd = open("/dev/gpiomem", O_RDWR | O_SYNC);
    if (fd < 0) { perror("gpiomem"); return -1; }
    void *m = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (m == MAP_FAILED) { perror("mmap"); return -1; }
    gpio_regs = (volatile uint32_t *)m;
    gpio_mode(PIN_TDO, 0);
    gpio_set(PIN_TCK, 0); gpio_set(PIN_TRST, 1); gpio_set(PIN_TMS, 1); gpio_set(PIN_TDI, 0);
    gpio_mode(PIN_TCK, 1); gpio_mode(PIN_TRST, 1); gpio_mode(PIN_TMS, 1); gpio_mode(PIN_TDI, 1);
    return 0;
}
static void gpio_cleanup(void) {
    if (!gpio_regs) return;
    gpio_mode(PIN_TCK, 0); gpio_mode(PIN_TRST, 0); gpio_mode(PIN_TMS, 0); gpio_mode(PIN_TDI, 0); gpio_mode(PIN_TDO, 0);
}
static inline int jtag_clock(int tms, int tdi) {
    uint32_t sm = 0, cm = (1u << PIN_TCK);
    if (tms) sm |= (1u << PIN_TMS); else cm |= (1u << PIN_TMS);
    if (tdi) sm |= (1u << PIN_TDI); else cm |= (1u << PIN_TDI);
    if (sm) gpio_regs[7] = sm;
    gpio_regs[10] = cm;
    tiny_delay();
    int tdo = (gpio_regs[13] >> PIN_TDO) & 1;
    gpio_regs[7] = (1u << PIN_TCK);
    tiny_delay();
    gpio_regs[10] = (1u << PIN_TCK);
    return tdo;
}
static void jtag_reset_idle(void) {
    gpio_set(PIN_TRST, 1);
    for (int i = 0; i < 6; i++) jtag_clock(1, 0);
    jtag_clock(0, 0);
}
static void jtag_shift_ir16(uint16_t ir) {
    jtag_clock(1, 0); jtag_clock(1, 0); jtag_clock(0, 0); jtag_clock(0, 0);
    for (int i = 0; i < 16; i++) jtag_clock(i == 15 ? 1 : 0, (ir >> i) & 1);
    jtag_clock(1, 0); jtag_clock(0, 0);
}
static uint64_t jtag_shift_dr(uint64_t val, int nbits) {
    jtag_clock(1, 0); jtag_clock(0, 0); jtag_clock(0, 0);
    uint64_t out = 0;
    for (int i = 0; i < nbits; i++) out |= ((uint64_t)jtag_clock(i == nbits - 1 ? 1 : 0, (int)((val >> i) & 1)) << i);
    jtag_clock(1, 0); jtag_clock(0, 0);
    return out;
}

static uint8_t bsr_tx[BSR_LEN];
static uint32_t last_d32 = 0;
static int last_rb = 1;

static void bsr_shift(void) {
    jtag_clock(1, 0); jtag_clock(0, 0); jtag_clock(0, 0);
    uint32_t d = 0;
    for (int i = 0; i < BSR_LEN; i++) {
        int r = jtag_clock(i == BSR_LEN - 1 ? 1 : 0, bsr_tx[i]);
        if (i == 116) last_rb = r;
        if (i >= 307 && i <= 338) d |= ((uint32_t)r << (i - 307));
    }
    jtag_clock(1, 0); jtag_clock(0, 0);
    last_d32 = d;
}

static void init_idle(void) {
    memset(bsr_tx, 1, BSR_LEN);
    /* Drive A0..A25 = 0 */
    for (int i = 0; i < 26; i++) { bsr_tx[182 - i] = 0; bsr_tx[224 - i] = 0; }
    /* Enable control pins + PTE1,2,3,6 + DACK0/1(84,85) */
    const int oe[] = {156,155,154,153,152,151,150, 148,147,146,145,144,143,142,141, 80,81,82,83,84,85};
    for (size_t i = 0; i < sizeof(oe)/sizeof(oe[0]); i++) bsr_tx[oe[i]] = 0;
    bsr_tx[198] = 1; /* BS */
    bsr_tx[197] = 1; /* /RD */
    bsr_tx[196] = 1; /* /WE0 */
    bsr_tx[195] = 1; /* /WE1 */
    bsr_tx[194] = 1; /* /WE2 */
    bsr_tx[193] = 1; /* /WE3 */
    bsr_tx[192] = 1; /* RDWR */
    bsr_tx[190] = 1; /* /CS0 (NOR LOCKED HIGH!) */
    bsr_tx[189] = 1; /* /CS2 */
    bsr_tx[188] = 1; /* /CS3 */
    bsr_tx[187] = 1; /* /CS4 */
    bsr_tx[186] = 1; /* /CS5 */
    bsr_tx[185] = 1; /* /CS6 */
    bsr_tx[99]  = 1; /* PTE1 /CE1 */
    bsr_tx[100] = 0; /* PTE2 LCD_E */
    bsr_tx[101] = 1; /* PTE3 /CE0 */
    bsr_tx[184] = 0; /* PTE4 CLE */
    bsr_tx[183] = 0; /* PTE5 ALE */
    bsr_tx[102] = 0; /* PTE6 WIN */
    bsr_tx[103] = 1; /* DACK1 (PTE7?) */
    bsr_tx[104] = 1; /* DACK0 */
}

static void set_d32_out(int drive, uint8_t b) {
    /* Replicate byte on all 4 byte lanes just in case (safe when writing read-only 0x90/0x00!) */
    for (int i = 0; i < 32; i++) {
        bsr_tx[235 + i] = drive ? 0 : 1;
        bsr_tx[267 + i] = (b >> (i & 7)) & 1;
    }
}

static void probe_combo(int pte6, int pte7, int bs_low, int cs_bit, int we_all) {
    /* Setup idle */
    init_idle();
    bsr_tx[103] = pte7;
    bsr_tx[102] = pte6;
    bsr_tx[99]  = 0; /* /CE1 active */
    bsr_tx[101] = 1; /* /CE0 inactive */
    bsr_shift();

    /* Send 0x90 (CLE=1) with clean 3-phase timing */
    bsr_tx[184] = 1; bsr_tx[183] = 0; /* CLE=1, ALE=0 */
    set_d32_out(1, 0x90);
    bsr_tx[192] = 0; /* RDWR=0 */
    bsr_shift(); /* phase 1: setup */
    bsr_tx[cs_bit] = 0;
    if (bs_low) bsr_tx[198] = 0;
    bsr_tx[196] = 0; /* /WE0 */
    if (we_all) { bsr_tx[195] = 0; bsr_tx[194] = 0; bsr_tx[193] = 0; }
    bsr_shift(); /* phase 2: strobe LOW */
    bsr_tx[196] = 1; bsr_tx[195] = 1; bsr_tx[194] = 1; bsr_tx[193] = 1;
    bsr_tx[cs_bit] = 1; bsr_tx[198] = 1;
    bsr_shift(); /* phase 3: strobe HIGH (latches 0x90!) */

    /* Send addr 0x00 (ALE=1) with clean 3-phase timing */
    bsr_tx[184] = 0; bsr_tx[183] = 1; /* CLE=0, ALE=1 */
    set_d32_out(1, 0x00);
    bsr_shift();
    bsr_tx[cs_bit] = 0;
    if (bs_low) bsr_tx[198] = 0;
    bsr_tx[196] = 0;
    if (we_all) { bsr_tx[195] = 0; bsr_tx[194] = 0; bsr_tx[193] = 0; }
    bsr_shift();
    bsr_tx[196] = 1; bsr_tx[195] = 1; bsr_tx[194] = 1; bsr_tx[193] = 1;
    bsr_tx[cs_bit] = 1; bsr_tx[198] = 1;
    bsr_shift();

    /* Switch to READ (CLE=0, ALE=0, D=Hi-Z, RDWR=1) */
    bsr_tx[184] = 0; bsr_tx[183] = 0;
    set_d32_out(0, 0xFF);
    bsr_tx[192] = 1;
    bsr_shift();

    uint32_t r[4];
    for (int k = 0; k < 4; k++) {
        bsr_tx[cs_bit] = 0;
        if (bs_low) bsr_tx[198] = 0;
        bsr_tx[197] = 0; /* /RD=0 */
        bsr_shift();
        bsr_tx[197] = 1;
        bsr_tx[cs_bit] = 1;
        bsr_tx[198] = 1;
        bsr_shift();
        r[k] = last_d32;
    }
    /* Deselect */
    init_idle();
    bsr_shift();

    if ((r[0] & 0xFF) != 0xFF || (r[1] & 0xFF) != 0xFF || (r[0] != 0xFFFFFFFF)) {
        printf("HIT! cs=%d pte6=%d pte7=%d bs=%d we_all=%d -> D32: %08X %08X %08X %08X (RB=%d)\n",
               cs_bit, pte6, pte7, bs_low, we_all, r[0], r[1], r[2], r[3], last_rb);
    } else {
        printf("  miss cs=%d pte6=%d pte7=%d bs=%d we_all=%d -> %08X (RB=%d)\n",
               cs_bit, pte6, pte7, bs_low, we_all, r[0], last_rb);
    }
}

int main(void) {
    if (gpio_init() != 0) return 1;
    jtag_reset_idle();
    uint32_t id = (uint32_t)jtag_shift_dr(0, 32);
    printf("IDCODE=0x%08X\n", id);
    if (id != 0x0000100F) { gpio_cleanup(); return 1; }

    jtag_reset_idle();
    jtag_shift_ir16(IR_SAMPLE);
    init_idle();
    bsr_shift();
    jtag_shift_ir16(IR_EXTEST);

    /* Test CS5 (186) with all combinations of pte6, pte7, bs_low, we_all */
    for (int pte6 = 1; pte6 >= 0; pte6--)
        for (int pte7 = 0; pte7 <= 1; pte7++)
            for (int bs = 0; bs <= 1; bs++)
                for (int we = 0; we <= 1; we++)
                    probe_combo(pte6, pte7, bs, 186, we);

    jtag_reset_idle();
    for (int i = 0; i < 6; i++) jtag_clock(1, 0);
    gpio_cleanup();
    return 0;
}
