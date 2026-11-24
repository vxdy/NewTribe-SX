/*
 * esx_nor_recover.c - SH7709S H-UDI JTAG Boundary-Scan NOR Boot Flash (IC15)
 *                     Recovery Tool for Korg ESX-1 SD on Raspberry Pi 4 (/dev/gpiomem)
 *
 * Target chip (verified from BFS 01.03.01 driver @ 0x0C002CB0..0x0C002F48):
 *   ST / Numonyx M29W160EB (16 Mbit / 2 MiB, Bottom Boot Block, 16-bit on /CS0)
 *   Manufacturer ID: 0x0020, Device ID: 0x2249
 *   Sectors 0..9  (0x00000..0x6FFFF, 448 KiB): BFS Bootloader (word sum == 0x00000000)
 *   Sector  10    (0x70000..0x7FFFF,  64 KiB): TUBECALIBDATA (factory tube calibration)
 *
 * SAFETY:
 *   - Read-only modes (--probe, --verify, --backup-calib) NEVER assert /WE0 or /WE1
 *     (except Autoselect ID probe in --probe which uses standard read-ID command 0x90/0xF0).
 *   - /CS5 (NAND), PTE1 (/CE1), PTE6 (NAND window) are HARD-LOCKED inactive at all times.
 *   - --flash requires explicit --i-understand-risk and validates the input image
 *     (512 KiB raw NOR dump, KORG + BFS header @ 0x6FFE0, Product ID 0xF1,
 *     32-bit BE word sum of 0x00000..0x6FFFF == 0x00000000) BEFORE erasing anything.
 *   - By default ONLY sectors 0..9 (0x00000..0x6FFFF) are erased/programmed so
 *     TUBECALIBDATA at 0x70000 is preserved untouched (override with --include-calib).
 *   - Releases all Raspberry Pi GPIOs to Hi-Z inputs on exit or Ctrl+C.
 *
 * Build on Raspberry Pi 4:
 *   gcc -O2 -Wall -Wextra -o esx_nor_recover esx_nor_recover.c
 *
 * Usage:
 *   ./esx_nor_recover --probe
 *   ./esx_nor_recover --backup-calib tubecalib_64k.bin
 *   ./esx_nor_recover --verify esx1sd_bfs_512k.bin
 *   ./esx_nor_recover --flash esx1sd_bfs_512k.bin --i-understand-risk [--unlock-bypass] [--include-calib] [--delay N]
 */
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

/* BCM GPIO pins (matching sd-dump/README.md and docs/ESX1SD_DEBRICKING_PI.md) */
#define PIN_TCK   25
#define PIN_TRST  24
#define PIN_TDO    9
#define PIN_TMS   23
#define PIN_TDI   10

#define BSR_LEN   339
#define IR_EXTEST 0x0FFF
#define IR_SAMPLE 0x4FFF
#define IR_BYPASS 0xFFFF

/* SH7709S / SH7729 BSR bit indices */
#define BIT_BS    198
#define BIT_RD    197
#define BIT_WE0   196
#define BIT_WE1   195
#define BIT_WE2   194
#define BIT_WE3   193
#define BIT_RDWR  192
#define BIT_CS0   190
#define BIT_CS2   189
#define BIT_CS3   188
#define BIT_CS4   187
#define BIT_CS5   186
#define BIT_CS6   185
#define BIT_PTE1   99
#define BIT_PTE2  100
#define BIT_PTE3  101
#define BIT_PTE6  102

/* M29W160EB 16-bit Bottom Boot Block sector map for first 512 KiB */
typedef struct {
    int      index;
    uint32_t addr;
    uint32_t size;
    const char *label;
} nor_sector_t;

static const nor_sector_t SECTORS[11] = {
    {  0, 0x00000, 0x04000, "BFS Boot 0 (16 KiB)" },
    {  1, 0x04000, 0x02000, "BFS Boot 1 ( 8 KiB)" },
    {  2, 0x06000, 0x02000, "BFS Boot 2 ( 8 KiB)" },
    {  3, 0x08000, 0x08000, "BFS Boot 3 (32 KiB)" },
    {  4, 0x10000, 0x10000, "BFS Main 4 (64 KiB)" },
    {  5, 0x20000, 0x10000, "BFS Main 5 (64 KiB)" },
    {  6, 0x30000, 0x10000, "BFS Main 6 (64 KiB)" },
    {  7, 0x40000, 0x10000, "BFS Main 7 (64 KiB)" },
    {  8, 0x50000, 0x10000, "BFS Main 8 (64 KiB)" },
    {  9, 0x60000, 0x10000, "BFS Main 9 (64 KiB, Header @ 0x6FFE0)" },
    { 10, 0x70000, 0x10000, "TUBECALIBDATA (64 KiB)" },
};

static volatile uint32_t *gpio_regs = NULL;
static int g_delay_loops = 20;
static volatile sig_atomic_t g_stop = 0;

static void on_sig(int sig) {
    (void)sig;
    g_stop = 1;
}

static inline void tiny_delay(void) {
    for (volatile int i = 0; i < g_delay_loops; i++) {
        __asm__ volatile("" ::: "memory");
    }
}

static inline void gpio_set(int pin, int val) {
    if (val) gpio_regs[7] = (1u << pin);
    else     gpio_regs[10] = (1u << pin);
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
    jtag_clock(0, 0);
}

static void jtag_shift_ir16(uint16_t ir) {
    jtag_clock(1, 0); jtag_clock(1, 0); jtag_clock(0, 0); jtag_clock(0, 0);
    for (int i = 0; i < 16; i++) {
        jtag_clock(i == 15 ? 1 : 0, (ir >> i) & 1);
    }
    jtag_clock(1, 0); jtag_clock(0, 0);
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

static uint8_t bsr_tx[BSR_LEN];

static void bsr_init_safe(void) {
    memset(bsr_tx, 1, BSR_LEN); /* All OE=1 (Hi-Z), all active-low controls=1 */
    /* Drive A0..A22 */
    for (int i = 0; i < 23; i++) {
        bsr_tx[182 - i] = 0;
        bsr_tx[224 - i] = 0;
    }
    /* Enable control outputs (BS, RD, WE0..3, RDWR, CS0, CS2..6, PTE1/2/3/6) */
    const int oe[] = {156, 155, 154, 153, 152, 151, 150, 148, 147, 146, 145, 144, 143, 80, 81, 82, 85};
    for (size_t i = 0; i < sizeof(oe)/sizeof(oe[0]); i++) bsr_tx[oe[i]] = 0;

    bsr_tx[BIT_BS]   = 1;
    bsr_tx[BIT_RD]   = 1;
    bsr_tx[BIT_WE0]  = 1;
    bsr_tx[BIT_WE1]  = 1;
    bsr_tx[BIT_WE2]  = 1;
    bsr_tx[BIT_WE3]  = 1;
    bsr_tx[BIT_RDWR] = 1;
    bsr_tx[BIT_CS0]  = 1;
    bsr_tx[BIT_CS2]  = 1;
    bsr_tx[BIT_CS3]  = 1;
    bsr_tx[BIT_CS4]  = 1;
    bsr_tx[BIT_CS5]  = 1; /* NAND CS5 HARD-LOCKED HIGH */
    bsr_tx[BIT_CS6]  = 1;
    bsr_tx[BIT_PTE1] = 1; /* NAND /CE1 HARD-LOCKED HIGH */
    bsr_tx[BIT_PTE2] = 0; /* LCD E low */
    bsr_tx[BIT_PTE3] = 1; /* /CE0 HIGH */
    bsr_tx[BIT_PTE6] = 0; /* NAND window OFF */
}

static inline void bsr_set_addr(uint32_t byte_addr) {
    for (int i = 0; i < 23; i++) {
        bsr_tx[224 - i] = (byte_addr >> i) & 1;
    }
}

static inline void bsr_set_d16(int drive, uint16_t val) {
    /* D0..D15 OE: bits 235..250 (0=drive, 1=Hi-Z), OUT: bits 267..282 */
    for (int i = 0; i < 16; i++) {
        bsr_tx[235 + i] = drive ? 0 : 1;
        bsr_tx[267 + i] = (val >> i) & 1;
    }
    /* Keep D16..D31 Hi-Z */
    for (int i = 16; i < 32; i++) bsr_tx[235 + i] = 1;
}

static inline uint16_t bsr_shift_d16(void) {
    /* HARD SAFETY INVARIANT: internal NAND MUST stay isolated! */
    bsr_tx[BIT_CS5]  = 1;
    bsr_tx[BIT_PTE1] = 1;
    bsr_tx[BIT_PTE6] = 0;

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
        fprintf(stderr, "ERROR: Expected SH7709S IDCODE 0x0000100F, got 0x%08X\n", id);
        return -1;
    }
    jtag_reset_idle();
    jtag_shift_ir16(IR_BYPASS);
    uint64_t got = jtag_shift_dr(0xA55A1234ULL, 33);
    if (((got >> 1) & 0xFFFFFFFFULL) != 0xA55A1234ULL) {
        fprintf(stderr, "ERROR: JTAG BYPASS check failed (got 0x%08X)\n", (uint32_t)(got >> 1));
        return -1;
    }
    /* SAMPLE/PRELOAD safe idle state BEFORE EXTEST */
    jtag_reset_idle();
    jtag_shift_ir16(IR_SAMPLE);
    bsr_init_safe();
    bsr_shift_d16();
    jtag_shift_ir16(IR_EXTEST);
    return 0;
}

/* Single 16-bit NOR read at byte address (must be even) */
static uint16_t nor_read16(uint32_t byte_addr) {
    bsr_set_d16(0, 0xFFFF);
    bsr_set_addr(byte_addr);
    bsr_tx[BIT_WE0]  = 1;
    bsr_tx[BIT_WE1]  = 1;
    bsr_tx[BIT_RDWR] = 1;
    bsr_tx[BIT_CS0]  = 0;
    bsr_tx[BIT_RD]   = 0;
    bsr_shift_d16(); /* drive address + /CS0 + /RD */

    bsr_tx[BIT_CS0]  = 1;
    bsr_tx[BIT_RD]   = 1;
    return bsr_shift_d16(); /* sample D0..D15 while deasserting /CS0 + /RD */
}

/* Pipelined fast block read (big-endian bytes) */
static void nor_read_block(uint32_t start_byte, uint8_t *buf, uint32_t nbytes) {
    uint32_t nwords = nbytes / 2;
    bsr_set_d16(0, 0xFFFF);
    bsr_tx[BIT_WE0]  = 1;
    bsr_tx[BIT_WE1]  = 1;
    bsr_tx[BIT_RDWR] = 1;
    bsr_set_addr(start_byte);
    bsr_tx[BIT_CS0]  = 0;
    bsr_tx[BIT_RD]   = 0;
    bsr_shift_d16();
    for (uint32_t w = 0; w < nwords; w++) {
        int last = (w == nwords - 1);
        bsr_set_addr(start_byte + (w + 1) * 2);
        bsr_tx[BIT_CS0] = last ? 1 : 0;
        bsr_tx[BIT_RD]  = last ? 1 : 0;
        uint16_t val = bsr_shift_d16();
        buf[w * 2]     = (uint8_t)(val >> 8);
        buf[w * 2 + 1] = (uint8_t)(val & 0xFF);
    }
}

/* Single 16-bit NOR write cycle at byte address (matches SH7709S 16-bit mov.w on CS0) */
static void nor_write16(uint32_t byte_addr, uint16_t val) {
    /* Step 1: setup address, data, RDWR=0, /RD=1, /CS0=0, /WE0=/WE1=1 */
    bsr_set_addr(byte_addr);
    bsr_set_d16(1, val);
    bsr_tx[BIT_RD]   = 1;
    bsr_tx[BIT_RDWR] = 0;
    bsr_tx[BIT_CS0]  = 0;
    bsr_tx[BIT_WE0]  = 1;
    bsr_tx[BIT_WE1]  = 1;
    bsr_shift_d16();

    /* Step 2: assert /WE0 + /WE1 LOW (latch address on falling edge) */
    bsr_tx[BIT_WE0]  = 0;
    bsr_tx[BIT_WE1]  = 0;
    bsr_shift_d16();

    /* Step 3: deassert /WE0 + /WE1 HIGH (latch data on rising edge) */
    bsr_tx[BIT_WE0]  = 1;
    bsr_tx[BIT_WE1]  = 1;
    bsr_shift_d16();

    /* Step 4: deassert /CS0, RDWR=1, D0..D15 Hi-Z */
    bsr_tx[BIT_CS0]  = 1;
    bsr_tx[BIT_RDWR] = 1;
    bsr_set_d16(0, 0xFFFF);
    bsr_shift_d16();
}

/* Standard M29W160EB reset to Read-Array mode (matches BFS 0x0C002D56) */
static void nor_reset(void) {
    nor_write16(0x0AAA, 0x00AA);
    nor_write16(0x0554, 0x0055);
    nor_write16(0x0AAA, 0x00F0);
    nor_write16(0x0000, 0x00F0);
    usleep(100);
}

/* Autoselect Read ID (matches BFS 0x0C002D7E) */
static void nor_read_id(uint16_t *mfg, uint16_t *dev) {
    nor_reset();
    nor_write16(0x0AAA, 0x00AA);
    nor_write16(0x0554, 0x0055);
    nor_write16(0x0AAA, 0x0090);
    *mfg = nor_read16(0x0000);
    *dev = nor_read16(0x0002);
    nor_reset();
}

/* DQ7 Data Polling with DQ5 timeout (matches BFS 0x0C002D16) */
static int nor_poll_dq7(uint32_t byte_addr, uint16_t expected_word, int max_ms) {
    uint16_t want = expected_word & 0x0080;
    struct timespec t0, now;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (;;) {
        uint16_t st = nor_read16(byte_addr);
        if ((st & 0x0080) == want) return 0;
        if (st & 0x0020) {
            /* DQ5 exceeded timing limits - re-read DQ7 once per JEDEC spec */
            st = nor_read16(byte_addr);
            if ((st & 0x0080) == want) return 0;
            nor_reset();
            return -1;
        }
        clock_gettime(CLOCK_MONOTONIC, &now);
        long ms = (now.tv_sec - t0.tv_sec) * 1000L + (now.tv_nsec - t0.tv_nsec) / 1000000L;
        if (ms > max_ms) {
            nor_reset();
            return -2;
        }
    }
}

/* Sector Erase (matches BFS 0x0C002E50) */
static int nor_erase_sector(uint32_t sector_addr) {
    nor_write16(0x0AAA, 0x00AA);
    nor_write16(0x0554, 0x0055);
    nor_write16(0x0AAA, 0x0080);
    nor_write16(0x0AAA, 0x00AA);
    nor_write16(0x0554, 0x0055);
    nor_write16(sector_addr, 0x0030);
    /* Typical M29W160EB sector erase is 0.5-1.5 s, max 6 s */
    return nor_poll_dq7(sector_addr, 0xFFFF, 10000);
}

/* Standard 4-cycle Word Program */
static int nor_program_word_std(uint32_t byte_addr, uint16_t word) {
    nor_write16(0x0AAA, 0x00AA);
    nor_write16(0x0554, 0x0055);
    nor_write16(0x0AAA, 0x00A0);
    nor_write16(byte_addr, word);
    return nor_poll_dq7(byte_addr, word, 50);
}

/* M29W160EB Unlock Bypass Program (matches BFS 0x0C002DC2 - 2x faster over JTAG) */
static void nor_unlock_bypass_enter(void) {
    nor_write16(0x0AAA, 0x00AA);
    nor_write16(0x0554, 0x0055);
    nor_write16(0x0AAA, 0x0020);
}

static int nor_program_word_bypass(uint32_t byte_addr, uint16_t word) {
    nor_write16(0x0000, 0x00A0);
    nor_write16(byte_addr, word);
    return nor_poll_dq7(byte_addr, word, 50);
}

static void nor_unlock_bypass_exit(void) {
    nor_write16(0x0000, 0x0090);
    nor_write16(0x0000, 0x0000);
    nor_reset();
}

static uint32_t be32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}

static uint32_t word_sum_be(const uint8_t *buf, uint32_t nbytes) {
    uint32_t s = 0;
    for (uint32_t i = 0; i < nbytes; i += 4) s += be32(buf + i);
    return s;
}

static int validate_bfs_image(const uint8_t *img, size_t len) {
    if (len != 0x80000) {
        fprintf(stderr, "ERROR: Image must be exactly 524288 bytes (raw NOR dump esx1sd_bfs_512k.bin), got %zu\n", len);
        return -1;
    }
    const uint8_t *hdr = img + 0x6FFE0;
    if (memcmp(hdr, "KORG", 4) != 0 || memcmp(hdr + 8, "BFS ", 4) != 0) {
        fprintf(stderr, "ERROR: Missing 'KORG'/'BFS ' header at 0x6FFE0! (Do NOT pass a rotated .BFS update container.)\n");
        return -1;
    }
    uint32_t pid = be32(hdr + 4);
    if (pid != 0x000000F1) {
        fprintf(stderr, "ERROR: Expected ESX-1 SD Product ID 0x000000F1, got 0x%08X\n", pid);
        return -1;
    }
    uint32_t ws = word_sum_be(img, 0x70000);
    if (ws != 0) {
        fprintf(stderr, "ERROR: 32-bit BE word sum of 0x00000..0x6FFFF is 0x%08X (must be 0x00000000)\n", ws);
        return -1;
    }
    printf("Image OK: '%.4s' ProductID=0x%02X '%.12s', word sum (0x00000..0x6FFFF) = 0x00000000\n",
           (const char *)hdr, pid, (const char *)(hdr + 8));
    if (memcmp(img + 0x70000, "TUBECALIBDATA", 13) == 0) {
        printf("Image also contains TUBECALIBDATA at 0x70000.\n");
    }
    return 0;
}

static void usage(const char *p) {
    fprintf(stderr,
        "Usage:\n"
        "  %s [--delay N] --probe\n"
        "  %s [--delay N] --backup-calib <out_64k.bin>\n"
        "  %s [--delay N] --verify <esx1sd_bfs_512k.bin> [--include-calib]\n"
        "  %s [--delay N] --flash <esx1sd_bfs_512k.bin> --i-understand-risk [--unlock-bypass] [--include-calib] [--force-id]\n",
        p, p, p, p);
}

int main(int argc, char **argv) {
    const char *mode = NULL;
    const char *path = NULL;
    int confirm = 0, include_calib = 0, unlock_bypass = 0, force_id = 0;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--delay") == 0 && i + 1 < argc) {
            g_delay_loops = atoi(argv[++i]);
        } else if (strcmp(argv[i], "--probe") == 0) {
            mode = "probe";
        } else if (strcmp(argv[i], "--backup-calib") == 0 && i + 1 < argc) {
            mode = "backup-calib"; path = argv[++i];
        } else if (strcmp(argv[i], "--verify") == 0 && i + 1 < argc) {
            mode = "verify"; path = argv[++i];
        } else if (strcmp(argv[i], "--flash") == 0 && i + 1 < argc) {
            mode = "flash"; path = argv[++i];
        } else if (strcmp(argv[i], "--i-understand-risk") == 0) {
            confirm = 1;
        } else if (strcmp(argv[i], "--include-calib") == 0) {
            include_calib = 1;
        } else if (strcmp(argv[i], "--unlock-bypass") == 0) {
            unlock_bypass = 1;
        } else if (strcmp(argv[i], "--force-id") == 0) {
            force_id = 1;
        } else {
            usage(argv[0]);
            return 1;
        }
    }
    if (!mode) { usage(argv[0]); return 1; }

    /* Pre-validate file before touching GPIO in --verify / --flash */
    uint8_t *img = NULL;
    if (strcmp(mode, "verify") == 0 || strcmp(mode, "flash") == 0) {
        if (strcmp(mode, "flash") == 0 && !confirm) {
            fprintf(stderr, "REFUSED: --flash requires explicit --i-understand-risk flag.\n");
            return 1;
        }
        FILE *f = fopen(path, "rb");
        if (!f) { perror(path); return 1; }
        fseek(f, 0, SEEK_END);
        long sz = ftell(f);
        fseek(f, 0, SEEK_SET);
        img = malloc(sz > 0 ? (size_t)sz : 1);
        if (!img || fread(img, 1, (size_t)sz, f) != (size_t)sz) {
            fprintf(stderr, "ERROR reading %s\n", path);
            fclose(f); free(img); return 1;
        }
        fclose(f);
        if (validate_bfs_image(img, (size_t)sz) != 0) {
            free(img); return 1;
        }
    }

    signal(SIGINT, on_sig);
    signal(SIGTERM, on_sig);

    if (gpio_init() != 0) { free(img); return 1; }
    if (enter_safe_extest() != 0) { gpio_cleanup(); free(img); return 1; }

    int rc = 0;

    if (strcmp(mode, "probe") == 0) {
        uint16_t mfg = 0, dev = 0;
        nor_read_id(&mfg, &dev);
        printf("SH7709S IDCODE = 0x0000100F, BYPASS = OK\n");
        printf("NOR Flash Autoselect ID: Manufacturer=0x%04X, Device=0x%04X %s\n",
               mfg, dev, (mfg == 0x0020 && dev == 0x2249) ? "(ST M29W160EB - MATCH!)" : "(UNEXPECTED)");
        uint8_t hdr[32], cal[32];
        nor_read_block(0x6FFE0, hdr, 32);
        nor_read_block(0x70000, cal, 32);
        printf("Header @ 0x6FFE0: '%.4s' ID=0x%08X '%.12s'\n",
               (const char *)hdr, be32(hdr + 4), (const char *)(hdr + 8));
        printf("Calib  @ 0x70000: '%.13s'\n", (const char *)cal);
    } else if (strcmp(mode, "backup-calib") == 0) {
        uint8_t *cal = malloc(0x10000);
        if (!cal) { perror("malloc"); rc = 1; goto out; }
        nor_reset();
        nor_read_block(0x70000, cal, 0x10000);
        FILE *f = fopen(path, "wb");
        if (!f) { perror(path); free(cal); rc = 1; goto out; }
        fwrite(cal, 1, 0x10000, f);
        fclose(f);
        printf("Saved 65536 bytes (Sector 10, 0x70000..0x7FFFF) to %s (tag='%.13s')\n",
               path, (const char *)cal);
        free(cal);
    } else if (strcmp(mode, "verify") == 0) {
        nor_reset();
        uint32_t limit = include_calib ? 0x80000 : 0x70000;
        uint8_t *cur = malloc(limit);
        if (!cur) { perror("malloc"); rc = 1; goto out; }
        for (uint32_t off = 0; off < limit; off += 0x4000) {
            nor_read_block(off, cur + off, 0x4000);
            printf("\rVerifying 0x%05X / 0x%05X...", off + 0x4000, limit);
            fflush(stdout);
        }
        printf("\n");
        uint32_t diffs = 0, first = 0;
        for (uint32_t i = 0; i < limit; i++) {
            if (cur[i] != img[i]) {
                if (diffs == 0) first = i;
                diffs++;
            }
        }
        if (diffs == 0) {
            printf("VERIFY PASS: 0x00000..0x%05X (%u bytes) 100%% IDENTICAL!\n", limit - 1, limit);
        } else {
            printf("VERIFY FAIL: %u differing bytes (first at 0x%05X: flash=0x%02X vs file=0x%02X)\n",
                   diffs, first, cur[first], img[first]);
            rc = 1;
        }
        free(cur);
    } else if (strcmp(mode, "flash") == 0) {
        uint16_t mfg = 0, dev = 0;
        nor_read_id(&mfg, &dev);
        printf("NOR Flash ID: Manufacturer=0x%04X, Device=0x%04X\n", mfg, dev);
        if (!(mfg == 0x0020 && dev == 0x2249) && !force_id) {
            fprintf(stderr, "ERROR: Expected M29W160EB (0x0020:0x2249). Aborting before erase! (Use --force-id to override.)\n");
            rc = 1;
            goto out;
        }

        int num_sectors = include_calib ? 11 : 10;
        printf("Flashing %d sectors (0x00000..0x%05X) in %s mode. DO NOT POWER OFF ESX-1 SD!\n",
               num_sectors, include_calib ? 0x7FFFF : 0x6FFFF,
               unlock_bypass ? "Unlock-Bypass (fast)" : "Standard 4-cycle");
        if (!include_calib) {
            printf("Sector 10 (0x70000 TUBECALIBDATA) will NOT be touched.\n");
        }

        uint8_t *vbuf = malloc(0x10000);
        if (!vbuf) { perror("malloc"); rc = 1; goto out; }

        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);

        for (int s = 0; s < num_sectors && !g_stop; s++) {
            const nor_sector_t *sec = &SECTORS[s];
            printf("\n[Sector %2d/%d] 0x%05X (%5u B) %s:\n",
                   sec->index, num_sectors - 1, sec->addr, sec->size, sec->label);

            /* 1. Erase sector */
            printf("  Erasing... ");
            fflush(stdout);
            int er = nor_erase_sector(sec->addr);
            if (er != 0) {
                fprintf(stderr, "ERASE FAILED (err=%d) at 0x%05X!\n", er, sec->addr);
                rc = 1;
                break;
            }
            printf("OK\n");

            /* 2. Program non-0xFFFF words */
            uint32_t nwords = sec->size / 2;
            uint32_t programmed = 0;
            if (unlock_bypass) nor_unlock_bypass_enter();

            for (uint32_t w = 0; w < nwords && !g_stop; w++) {
                uint32_t addr = sec->addr + w * 2;
                uint16_t word = ((uint16_t)img[addr] << 8) | img[addr + 1];
                if (word == 0xFFFF) continue;
                int pr = unlock_bypass
                    ? nor_program_word_bypass(addr, word)
                    : nor_program_word_std(addr, word);
                if (pr != 0) {
                    fprintf(stderr, "\n  PROGRAM FAILED (err=%d) at 0x%05X (word=0x%04X)!\n", pr, addr, word);
                    rc = 1;
                    break;
                }
                programmed++;
                if ((w & 0x3FF) == 0 || w == nwords - 1) {
                    clock_gettime(CLOCK_MONOTONIC, &t1);
                    double dt = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) * 1e-9;
                    printf("\r  Programming %u / %u words (%.1f%%, elapsed %.0fs)...",
                           w + 1, nwords, 100.0 * (w + 1) / nwords, dt);
                    fflush(stdout);
                }
            }
            if (unlock_bypass) nor_unlock_bypass_exit();
            else nor_reset();

            if (rc != 0 || g_stop) break;
            printf("\n  Programmed %u non-FF words. Verifying... ", programmed);
            fflush(stdout);

            /* 3. Verify sector immediately */
            nor_read_block(sec->addr, vbuf, sec->size);
            if (memcmp(vbuf, img + sec->addr, sec->size) != 0) {
                uint32_t bad = 0;
                while (bad < sec->size && vbuf[bad] == img[sec->addr + bad]) bad++;
                fprintf(stderr, "VERIFY MISMATCH at 0x%05X (got 0x%02X, want 0x%02X)!\n",
                        sec->addr + bad, vbuf[bad], img[sec->addr + bad]);
                rc = 1;
                break;
            }
            printf("VERIFIED OK!\n");
        }

        free(vbuf);
        if (g_stop) {
            fprintf(stderr, "\nABORTED by signal! NOR Flash may be incomplete — do NOT reboot until re-flashed!\n");
            rc = 1;
        } else if (rc == 0) {
            clock_gettime(CLOCK_MONOTONIC, &t1);
            double dt = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) * 1e-9;
            printf("\nALL %d SECTORS FLASHED & VERIFIED 100%% OK in %.1f s!\n", num_sectors, dt);
            printf("You can now power off the ESX-1 SD, disconnect JTAG, and boot normally.\n");
        }
    }

out:
    nor_reset();
    jtag_reset_idle();
    for (int i = 0; i < 6; i++) jtag_clock(1, 0);
    gpio_cleanup();
    free(img);
    return rc;
}
