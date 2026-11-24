/*
 * esx_nor_dump.c - Read-only SH7709S JTAG Boundary-Scan NOR Flash dumper for Raspberry Pi 4 (/dev/gpiomem)
 *
 * SAFETY:
 *   - Always PRELOADs safe idle vector (WE0..3=1, RDWR=1, CS0..6=1, D0..31=Hi-Z) BEFORE entering EXTEST.
 *   - WE0, WE1, WE2, WE3 and RDWR are hard-locked to HIGH (1) in every scan cycle.
 *   - D0..D31 output enables are hard-locked to Hi-Z (1) in every scan cycle.
 *   - Pure read-only: impossible to issue a flash write or erase cycle.
 *
 * Build on Raspberry Pi 4:
 *   gcc -O2 -Wall -o esx_nor_dump esx_nor_dump.c
 *
 * Usage:
 *   ./esx_nor_dump --probe                 # Check IDCODE, BYPASS, flash size/aliasing, header search
 *   ./esx_nor_dump --dump out.bin <bytes>  # Dump <bytes> (e.g. 524288 or 1048576) in big-endian 16-bit words
 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

/* BCM GPIO pins (matching jtag_probe.py) */
#define PIN_TCK   25
#define PIN_TRST  24
#define PIN_TDO    9
#define PIN_TMS   23
#define PIN_TDI   10

#define BSR_LEN   339
#define IR_EXTEST 0x0FFF
#define IR_SAMPLE 0x4FFF
#define IR_IDCODE 0xEFFF
#define IR_BYPASS 0xFFFF

static volatile uint32_t *gpio_regs = NULL;
static int g_delay_loops = 45; /* ~1.5-2.5 MHz TCK on Pi 4 */

static inline void tiny_delay(void) {
    for (volatile int i = 0; i < g_delay_loops; i++) {
        __asm__ volatile("" ::: "memory");
    }
}

static inline void gpio_set(int pin, int val) {
    if (val)
        gpio_regs[7] = (1u << pin);   /* GPSET0 @ 0x1C */
    else
        gpio_regs[10] = (1u << pin);  /* GPCLR0 @ 0x28 */
}

static inline int gpio_get(int pin) {
    return (gpio_regs[13] >> pin) & 1; /* GPLEV0 @ 0x34 */
}

static void gpio_mode(int pin, int is_out) {
    int reg = pin / 10;
    int shift = (pin % 10) * 3;
    uint32_t v = gpio_regs[reg];
    v &= ~(7u << shift);
    if (is_out) v |= (1u << shift);
    gpio_regs[reg] = v;
}

static int gpio_init(void) {
    int fd = open("/dev/gpiomem", O_RDWR | O_SYNC);
    if (fd < 0) {
        perror("open(/dev/gpiomem)");
        return -1;
    }
    void *m = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    close(fd);
    if (m == MAP_FAILED) {
        perror("mmap(/dev/gpiomem)");
        return -1;
    }
    gpio_regs = (volatile uint32_t *)m;
    gpio_mode(PIN_TDO, 0);
    gpio_set(PIN_TCK, 0);
    gpio_set(PIN_TRST, 1);
    gpio_set(PIN_TMS, 1);
    gpio_set(PIN_TDI, 0);
    gpio_mode(PIN_TCK, 1);
    gpio_mode(PIN_TRST, 1);
    gpio_mode(PIN_TMS, 1);
    gpio_mode(PIN_TDI, 1);
    return 0;
}

static void gpio_cleanup(void) {
    if (!gpio_regs) return;
    /* Release pins back to inputs (safe Hi-Z) */
    gpio_mode(PIN_TCK, 0);
    gpio_mode(PIN_TRST, 0);
    gpio_mode(PIN_TMS, 0);
    gpio_mode(PIN_TDI, 0);
    gpio_mode(PIN_TDO, 0);
}

static inline int jtag_clock(int tms, int tdi) {
    uint32_t set_mask = 0, clr_mask = (1u << PIN_TCK);
    if (tms) set_mask |= (1u << PIN_TMS); else clr_mask |= (1u << PIN_TMS);
    if (tdi) set_mask |= (1u << PIN_TDI); else clr_mask |= (1u << PIN_TDI);
    if (set_mask) gpio_regs[7] = set_mask;
    gpio_regs[10] = clr_mask;
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
    jtag_clock(0, 0); /* Run-Test/Idle */
}

static uint32_t jtag_shift_ir16(uint16_t ir) {
    jtag_clock(1, 0); jtag_clock(1, 0); jtag_clock(0, 0); jtag_clock(0, 0);
    uint32_t out = 0;
    for (int i = 0; i < 16; i++) {
        int r = jtag_clock(i == 15 ? 1 : 0, (ir >> i) & 1);
        out |= ((uint32_t)r << i);
    }
    jtag_clock(1, 0); jtag_clock(0, 0);
    return out;
}

static uint64_t jtag_shift_dr(uint64_t val, int nbits) {
    jtag_clock(1, 0); jtag_clock(0, 0); jtag_clock(0, 0);
    uint64_t out = 0;
    for (int i = 0; i < nbits; i++) {
        int r = jtag_clock(i == nbits - 1 ? 1 : 0, (int)((val >> i) & 1));
        out |= ((uint64_t)r << i);
    }
    jtag_clock(1, 0); jtag_clock(0, 0);
    return out;
}

/* Pre-built 339-bit BSR template for ultra-fast NOR reads */
static uint8_t bsr_tx[BSR_LEN];

static void bsr_init_safe(void) {
    memset(bsr_tx, 1, BSR_LEN); /* All controls = 1 (Hi-Z), all active-low signals = 1 */
    /* Enable A0..A22 output drivers (control bits 182..160 -> 0) */
    for (int i = 0; i < 23; i++) {
        bsr_tx[182 - i] = 0;
        bsr_tx[224 - i] = 0;
    }
    /* Enable control pin drivers (BS, RD, WE0..3, RDWR, CS0, CS2..6) */
    const int ctrl_oe[] = {156, 155, 154, 153, 152, 151, 150, 148, 147, 146, 145, 144, 143};
    for (size_t i = 0; i < sizeof(ctrl_oe)/sizeof(ctrl_oe[0]); i++) {
        bsr_tx[ctrl_oe[i]] = 0;
    }
    /* Hard-lock WE0..3=1, RDWR=1, BS=1, CS2..6=1, CS0=1, RD=1 */
    bsr_tx[198] = 1; /* BS */
    bsr_tx[197] = 1; /* /RD */
    bsr_tx[196] = 1; /* /WE0 LOCKED HIGH */
    bsr_tx[195] = 1; /* /WE1 LOCKED HIGH */
    bsr_tx[194] = 1; /* /WE2 LOCKED HIGH */
    bsr_tx[193] = 1; /* /WE3 LOCKED HIGH */
    bsr_tx[192] = 1; /* RD/WR = READ */
    bsr_tx[190] = 1; /* /CS0 */
    bsr_tx[189] = 1; /* /CS2 */
    bsr_tx[188] = 1; /* /CS3 */
    bsr_tx[187] = 1; /* /CS4 */
    bsr_tx[186] = 1; /* /CS5 */
    bsr_tx[185] = 1; /* /CS6 */
}

static inline void bsr_set_nor_addr(uint32_t byte_addr, int active) {
    /* A0..A22 at bits 224..202 */
    for (int i = 0; i < 23; i++) {
        bsr_tx[224 - i] = (byte_addr >> i) & 1;
    }
    bsr_tx[190] = active ? 0 : 1; /* /CS0 */
    bsr_tx[197] = active ? 0 : 1; /* /RD */
}

/* Shift full 339-bit BSR and extract D0..D15 (bits 307..322) directly on the fly */
static inline uint16_t bsr_shift_read_d16(void) {
    jtag_clock(1, 0); jtag_clock(0, 0); jtag_clock(0, 0);
    uint16_t d16 = 0;
    for (int i = 0; i < BSR_LEN; i++) {
        int r = jtag_clock(i == BSR_LEN - 1 ? 1 : 0, bsr_tx[i]);
        if (i >= 307 && i <= 322) {
            d16 |= (uint16_t)(r << (i - 307));
        }
    }
    jtag_clock(1, 0); jtag_clock(0, 0);
    return d16;
}

static int enter_safe_extest(void) {
    jtag_reset_idle();
    uint32_t id = (uint32_t)jtag_shift_dr(0, 32);
    if (id != 0x0000100F) {
        fprintf(stderr, "ERROR: Expected IDCODE 0x0000100F, got 0x%08X\n", id);
        return -1;
    }
    jtag_reset_idle();
    jtag_shift_ir16(IR_BYPASS);
    uint64_t got = jtag_shift_dr(0xA55A1234ULL, 33);
    if (((got >> 1) & 0xFFFFFFFFULL) != 0xA55A1234ULL) {
        fprintf(stderr, "ERROR: BYPASS check failed (got 0x%08X)\n", (uint32_t)(got >> 1));
        return -1;
    }
    /* PRELOAD safe idle vector FIRST */
    jtag_reset_idle();
    jtag_shift_ir16(IR_SAMPLE);
    bsr_init_safe();
    bsr_set_nor_addr(0, 0);
    bsr_shift_read_d16();
    /* Now switch to EXTEST */
    jtag_shift_ir16(IR_EXTEST);
    return 0;
}

static void read_nor_block(uint32_t start_byte, uint8_t *buf, uint32_t nbytes) {
    uint32_t nwords = nbytes / 2;
    bsr_set_nor_addr(start_byte, 1);
    bsr_shift_read_d16(); /* latch first address onto bus */
    for (uint32_t w = 0; w < nwords; w++) {
        int last = (w == nwords - 1);
        bsr_set_nor_addr(start_byte + (w + 1) * 2, last ? 0 : 1);
        uint16_t val = bsr_shift_read_d16();
        /* SH-3 Big-Endian: D15..D8 is even byte, D7..D0 is odd byte */
        buf[w * 2]     = (uint8_t)(val >> 8);
        buf[w * 2 + 1] = (uint8_t)(val & 0xFF);
    }
}

static void hexdump(uint32_t base, const uint8_t *b, int n) {
    for (int i = 0; i < n; i += 16) {
        printf("  0x%06X: ", base + i);
        for (int j = 0; j < 16 && i + j < n; j++) printf("%02X ", b[i + j]);
        printf(" |");
        for (int j = 0; j < 16 && i + j < n; j++) {
            uint8_t c = b[i + j];
            printf("%c", (c >= 32 && c < 127) ? c : '.');
        }
        printf("|\n");
    }
}

int main(int argc, char **argv) {
    int argi = 1;
    if (argc >= 3 && strcmp(argv[1], "--delay") == 0) {
        g_delay_loops = atoi(argv[2]);
        argi = 3;
    }
    if (argi >= argc) {
        fprintf(stderr, "Usage: %s [--delay N] --probe | --dump <out.bin> <size_bytes>\n", argv[0]);
        return 1;
    }
    if (gpio_init() != 0) return 1;

    if (enter_safe_extest() != 0) {
        gpio_cleanup();
        return 1;
    }

    if (strcmp(argv[argi], "--probe") == 0) {
        printf("IDCODE 0x0000100F + BYPASS OK! Probing NOR Flash (16-bit CS0)...\n");
        const uint32_t addrs[] = {
            0x000000, 0x07BFE0, 0x07FFE0,
            0x080000, 0x0FBFE0, 0x0FFFE0,
            0x100000, 0x1FBFE0, 0x1FFFE0,
            0x200000, 0x3FFFE0
        };
        uint8_t tmp[32];
        for (size_t i = 0; i < sizeof(addrs)/sizeof(addrs[0]); i++) {
            read_nor_block(addrs[i], tmp, 32);
            printf("\n@ 0x%06X:\n", addrs[i]);
            hexdump(addrs[i], tmp, 32);
        }
    } else if (strcmp(argv[argi], "--dump") == 0 && argi + 2 < argc) {
        const char *path = argv[argi + 1];
        uint32_t total = (uint32_t)strtoul(argv[argi + 2], NULL, 0);
        uint8_t *buf = malloc(total);
        if (!buf) { perror("malloc"); gpio_cleanup(); return 1; }
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        const uint32_t chunk = 16384;
        for (uint32_t off = 0; off < total; off += chunk) {
            uint32_t n = (total - off < chunk) ? (total - off) : chunk;
            read_nor_block(off, buf + off, n);
            clock_gettime(CLOCK_MONOTONIC, &t1);
            double dt = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) * 1e-9;
            printf("\rDumped %u / %u bytes (%.1f%%, %.1f KiB/s)...",
                   off + n, total, 100.0 * (off + n) / total, (off + n) / 1024.0 / (dt > 0.001 ? dt : 0.001));
            fflush(stdout);
        }
        printf("\n");
        FILE *f = fopen(path, "wb");
        if (!f) { perror("fopen"); free(buf); gpio_cleanup(); return 1; }
        fwrite(buf, 1, total, f);
        fclose(f);
        free(buf);
        printf("Saved %u bytes to %s\n", total, path);
    }

    /* Return TAP to Test-Logic-Reset cleanly */
    jtag_reset_idle();
    for (int i = 0; i < 6; i++) jtag_clock(1, 0);
    gpio_cleanup();
    return 0;
}
