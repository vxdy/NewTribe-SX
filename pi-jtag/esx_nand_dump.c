/*
 * esx_nand_dump.c - Safe read-only Hynix AD F1 00 1D (2048+64B) NAND dumper
 *                   over SH7709S H-UDI JTAG EXTEST on Raspberry Pi 4.
 *
 * HARDWARE SAFETY:
 *   - STRICT READ-ONLY command whitelist: ONLY 0xFF, 0x90, 0x00, 0x30, 0x05, 0xE0, 0x70.
 *   - /CS0 (NOR Boot Flash, BSR bit 190) is HARD-LOCKED HIGH (1) at all times.
 *   - SAMPLE/PRELOAD safe idle state before entering EXTEST.
 *   - Releases all Pi GPIOs to Hi-Z inputs on exit.
 *
 * Build on Pi: gcc -O3 -Wall -o esx_nand_dump esx_nand_dump.c
 */
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
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

/* BSR bit indices for SH7709S / SH7729 */
#define BIT_BS    198
#define BIT_RD    197
#define BIT_WE0   196
#define BIT_WE1   195
#define BIT_WE2   194
#define BIT_WE3   193
#define BIT_RDWR  192
#define BIT_CS0   190
#define BIT_CS5   186
#define BIT_CLE   184  /* PTE4 / CE2A */
#define BIT_ALE   183  /* PTE5 / CE2B */
#define BIT_PTE1   99  /* /CE1 (internal NAND) */
#define BIT_PTE2  100  /* LCD E */
#define BIT_PTE3  101  /* /CE0 */
#define BIT_PTE6  102  /* NAND window */
#define BIT_PTE7  103  /* DACK1 */
#define BIT_RB    116  /* PTF3 / IRLS3 (1=ready, 0=busy) */

#define PAGE_SIZE  2048
#define OOB_SIZE   64
#define PAGES_PER_BLK 64
#define TOTAL_BLOCKS  1024

static volatile uint32_t *gpio_regs = NULL;
static int g_delay = 12;
static int g_we_mask = 0x02; /* WE1 (bit 195) verified on ESX-1 SD */
static int g_bs_low  = 0;    /* BS not needed on ESX-1 SD */
static volatile sig_atomic_t g_stop = 0;

static void on_sig(int sig) { (void)sig; g_stop = 1; }

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
static uint8_t last_d8 = 0xFF;
static int last_rb = 1;

static void bsr_shift(void) {
    /* HARD SAFETY INVARIANT: /CS0 (NOR) MUST NEVER GO LOW! */
    bsr_tx[BIT_CS0] = 1;

    jtag_clock(1, 0); jtag_clock(0, 0); jtag_clock(0, 0);
    uint8_t d = 0;
    for (int i = 0; i < BSR_LEN; i++) {
        int r = jtag_clock(i == BSR_LEN - 1 ? 1 : 0, bsr_tx[i]);
        if (i == BIT_RB) last_rb = r;
        if (i >= 307 && i <= 314) d |= (uint8_t)(r << (i - 307));
    }
    jtag_clock(1, 0); jtag_clock(0, 0);
    last_d8 = d;
}

static void init_idle(void) {
    memset(bsr_tx, 1, BSR_LEN);
    /* Drive A0..A25 = 0 */
    for (int i = 0; i < 26; i++) { bsr_tx[182 - i] = 0; bsr_tx[224 - i] = 0; }
    /* Enable control outputs */
    const int oe[] = {156,155,154,153,152,151,150, 148,147,146,145,144,143,142,141, 80,81,82,83,84,85};
    for (size_t i = 0; i < sizeof(oe)/sizeof(oe[0]); i++) bsr_tx[oe[i]] = 0;
    bsr_tx[BIT_BS]   = 1;
    bsr_tx[BIT_RD]   = 1;
    bsr_tx[BIT_WE0]  = 1;
    bsr_tx[BIT_WE1]  = 1;
    bsr_tx[BIT_WE2]  = 1;
    bsr_tx[BIT_WE3]  = 1;
    bsr_tx[BIT_RDWR] = 1;
    bsr_tx[BIT_CS0]  = 1; /* NOR LOCKED HIGH */
    bsr_tx[189] = 1; bsr_tx[188] = 1; bsr_tx[187] = 1;
    bsr_tx[BIT_CS5]  = 1;
    bsr_tx[185] = 1;
    bsr_tx[BIT_PTE1] = 1; /* /CE1 inactive */
    bsr_tx[BIT_PTE2] = 0; /* LCD E low */
    bsr_tx[BIT_PTE3] = 1; /* /CE0 inactive */
    bsr_tx[BIT_CLE]  = 0;
    bsr_tx[BIT_ALE]  = 0;
    bsr_tx[BIT_PTE6] = 0; /* NAND window off */
    bsr_tx[BIT_PTE7] = 1;
    bsr_tx[104]      = 1;
}

static void set_d8_out(int drive, uint8_t b) {
    /* Only drive D0..D7 (bits 235..242 OE, 267..274 OUT); keep D8..D31 Hi-Z */
    for (int i = 0; i < 8; i++) {
        bsr_tx[235 + i] = drive ? 0 : 1;
        bsr_tx[267 + i] = (b >> i) & 1;
    }
    for (int i = 8; i < 32; i++) bsr_tx[235 + i] = 1;
}

static void nand_select(void) {
    bsr_tx[BIT_PTE6] = 1;
    bsr_tx[BIT_PTE1] = 0; /* /CE1 active */
    bsr_tx[BIT_PTE3] = 1; /* /CE0 inactive */
    bsr_tx[BIT_CLE]  = 0;
    bsr_tx[BIT_ALE]  = 0;
    bsr_tx[BIT_CS5]  = 1;
    bsr_tx[BIT_RD]   = 1;
    bsr_tx[BIT_WE0]  = 1; bsr_tx[BIT_WE1] = 1; bsr_tx[BIT_WE2] = 1; bsr_tx[BIT_WE3] = 1;
    bsr_tx[BIT_BS]   = 1;
    bsr_tx[BIT_RDWR] = 1;
    set_d8_out(0, 0xFF);
    bsr_shift();
}

static void nand_deselect(void) {
    init_idle();
    bsr_shift();
}

static void nand_write_strobe(uint8_t val, int cle, int ale) {
    bsr_tx[BIT_CLE]  = cle;
    bsr_tx[BIT_ALE]  = ale;
    bsr_tx[BIT_RDWR] = 0;
    set_d8_out(1, val);
    bsr_shift(); /* phase 1: setup CLE/ALE/D */

    bsr_tx[BIT_CS5] = 0;
    if (g_bs_low) bsr_tx[BIT_BS] = 0;
    if (g_we_mask & 1) bsr_tx[BIT_WE0] = 0;
    if (g_we_mask & 2) bsr_tx[BIT_WE1] = 0;
    if (g_we_mask & 4) bsr_tx[BIT_WE2] = 0;
    if (g_we_mask & 8) bsr_tx[BIT_WE3] = 0;
    bsr_shift(); /* phase 2: /WE LOW */

    bsr_tx[BIT_WE0] = 1; bsr_tx[BIT_WE1] = 1; bsr_tx[BIT_WE2] = 1; bsr_tx[BIT_WE3] = 1;
    bsr_tx[BIT_CS5] = 1;
    bsr_tx[BIT_BS]  = 1;
    bsr_shift(); /* phase 3: /WE HIGH -> latch! */
}

static void nand_cmd(uint8_t cmd) {
    /* STRICT READ-ONLY WHITELIST! */
    switch (cmd) {
        case 0xFF: /* RESET */
        case 0x90: /* READ ID */
        case 0x00: /* READ 1 */
        case 0x30: /* READ 2 (large page) */
        case 0x05: /* RANDOM DATA OUT 1 */
        case 0xE0: /* RANDOM DATA OUT 2 */
        case 0x70: /* READ STATUS */
            break;
        default:
            fprintf(stderr, "FATAL SAFETY VIOLATION: blocked non-readonly NAND cmd 0x%02X\n", cmd);
            nand_deselect();
            gpio_cleanup();
            abort();
    }
    nand_write_strobe(cmd, 1, 0);
}

static void nand_addr(uint8_t a) {
    nand_write_strobe(a, 0, 1);
}

static void nand_read_mode(void) {
    bsr_tx[BIT_CLE]  = 0;
    bsr_tx[BIT_ALE]  = 0;
    bsr_tx[BIT_RDWR] = 1;
    set_d8_out(0, 0xFF);
    bsr_shift();
}

static int nand_wait_ready(int max_polls) {
    for (int i = 0; i < max_polls; i++) {
        bsr_shift();
        if (last_rb) return 0;
    }
    return -1;
}

static void nand_read_bytes(uint8_t *buf, int n) {
    /* Assume already in read mode (CLE=0, ALE=0, RDWR=1, D=Hi-Z) */
    for (int i = 0; i < n; i++) {
        bsr_tx[BIT_CS5] = 0;
        if (g_bs_low) bsr_tx[BIT_BS] = 0;
        bsr_tx[BIT_RD] = 0;
        bsr_shift(); /* Update-DR drives /RD=0; NAND outputs byte i in ~20ns */

        bsr_tx[BIT_RD]  = 1;
        bsr_tx[BIT_CS5] = 1;
        bsr_tx[BIT_BS]  = 1;
        bsr_shift(); /* Capture-DR samples byte i while /RD=0, then Update-DR raises /RD=1 */
        buf[i] = last_d8;
    }
}

static void nand_reset(void) {
    nand_select();
    nand_cmd(0xFF);
    nand_read_mode();
    usleep(1000);
    nand_wait_ready(200);
    nand_deselect();
}

static void nand_read_id(uint8_t id[4]) {
    nand_select();
    nand_cmd(0x90);
    nand_addr(0x00);
    nand_read_mode();
    nand_read_bytes(id, 4);
    nand_deselect();
}

static int nand_read_page_slice(uint32_t row, uint16_t col, uint8_t *buf, int len) {
    nand_select();
    nand_cmd(0x00);
    nand_addr((uint8_t)(col & 0xFF));
    nand_addr((uint8_t)((col >> 8) & 0xFF));
    nand_addr((uint8_t)(row & 0xFF));
    nand_addr((uint8_t)((row >> 8) & 0xFF));
    nand_cmd(0x30);
    nand_read_mode();
    if (nand_wait_ready(500) != 0) {
        nand_deselect();
        return -1;
    }
    nand_read_bytes(buf, len);
    nand_deselect();
    return 0;
}

static void hexdump(const uint8_t *b, int n, uint32_t base) {
    for (int i = 0; i < n; i += 16) {
        printf("  %04X:", base + i);
        for (int j = 0; j < 16 && i + j < n; j++) printf(" %02X", b[i + j]);
        printf("  ");
        for (int j = 0; j < 16 && i + j < n; j++) {
            uint8_t c = b[i + j];
            putchar((c >= 32 && c < 127) ? c : '.');
        }
        putchar('\n');
    }
}

static void do_probe(void) {
    printf("=== Strobe isolation test (with 0xFF reset before each) ===\n");
    for (int bs = 0; bs <= 1; bs++) {
        for (int w = 0; w < 4; w++) {
            g_bs_low = 1; g_we_mask = 0x0F;
            nand_reset();
            g_bs_low = bs; g_we_mask = (1 << w);
            uint8_t id[4] = {0};
            nand_read_id(id);
            printf("  BS=%d WE%d -> %02X %02X %02X %02X %s\n",
                   bs, w, id[0], id[1], id[2], id[3],
                   (id[0] == 0xAD && id[1] == 0xF1) ? "<-- HIT!" : "");
        }
    }
    /* Restore safe working defaults */
    g_bs_low = 1; g_we_mask = 0x0F;
    nand_reset();

    uint8_t id[4] = {0};
    nand_read_id(id);
    printf("\nNAND ID: %02X %02X %02X %02X\n", id[0], id[1], id[2], id[3]);

    printf("\n=== Block 0, Page 0: first 64 bytes (col 0x0000) ===\n");
    uint8_t buf[64];
    if (nand_read_page_slice(0, 0, buf, 64) == 0) hexdump(buf, 64, 0);
    else printf("TIMEOUT!\n");

    printf("\n=== Block 0, Page 0: 64-byte OOB (col 0x0800) ===\n");
    if (nand_read_page_slice(0, 2048, buf, 64) == 0) hexdump(buf, 64, 0x0800);
    else printf("TIMEOUT!\n");

    printf("\n=== Block 1, Page 0: 64-byte OOB (col 0x0800) ===\n");
    if (nand_read_page_slice(64, 2048, buf, 64) == 0) hexdump(buf, 64, 0x0800);
    else printf("TIMEOUT!\n");

    printf("\n=== Block 15, Page 63: last 64 bytes of 2 MiB (col 0x07C0) ===\n");
    if (nand_read_page_slice(15 * 64 + 63, 0x07C0, buf, 64) == 0) hexdump(buf, 64, 0x07C0);
    else printf("TIMEOUT!\n");
}

/*
 * ESX-1 SD Large-Page NAND Layout (verified from BFS 01.03.01 @ 0x0C009D00 & live NAND):
 *   Column 0x0000..0x003F (64 bytes):   OOB / Spare area (4 x 16-byte SmartMedia chunks)
 *   Column 0x0040..0x083F (2048 bytes): Main page data!
 */
#define COL_OOB   0x0000
#define COL_MAIN  0x0040

static void do_scan_oob(const char *out_path) {
    FILE *f = out_path ? fopen(out_path, "wb") : NULL;
    uint8_t oob[OOB_SIZE];
    int non_ff = 0, bad = 0;
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    for (int blk = 0; blk < TOTAL_BLOCKS && !g_stop; blk++) {
        uint32_t row = (uint32_t)blk * PAGES_PER_BLK;
        if (nand_read_page_slice(row, COL_OOB, oob, OOB_SIZE) != 0) {
            fprintf(stderr, "Block %d OOB read timeout!\n", blk);
            memset(oob, 0xEE, OOB_SIZE);
        }
        if (f) fwrite(oob, 1, OOB_SIZE, f);
        if (oob[5] != 0xFF) bad++;
        int all_ff = 1;
        for (int i = 0; i < OOB_SIZE; i++) if (oob[i] != 0xFF) { all_ff = 0; break; }
        if (!all_ff) {
            non_ff++;
            uint16_t lba1 = ((uint16_t)oob[6] << 8) | oob[7];
            uint16_t lba2 = ((uint16_t)oob[11] << 8) | oob[12];
            if (blk < 64 || non_ff <= 80) {
                printf("BLK %4d: LBA1=%04X LBA2=%04X | ", blk, lba1, lba2);
                for (int i = 0; i < 16; i++) printf("%02X ", oob[i]);
                printf("\n");
            }
        }
    }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double dt = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) * 1e-9;
    if (f) fclose(f);
    printf("Scanned %d blocks in %.2fs: non-FF OOB=%d, bad(oob[5]!=FF)=%d\n",
           TOTAL_BLOCKS, dt, non_ff, bad);
}

static void do_speed_test(void) {
    /* Reference read of Block 2 Page 0 (SH-3 code) at delay=20 */
    uint8_t ref[PAGE_SIZE], cur[PAGE_SIZE];
    g_delay = 20;
    nand_read_page_slice(2 * PAGES_PER_BLK, COL_MAIN, ref, PAGE_SIZE);
    printf("Speed test on Block 2 Page 0 (2048B main data, first 16B: %02X %02X %02X %02X %02X %02X %02X %02X):\n",
           ref[0], ref[1], ref[2], ref[3], ref[4], ref[5], ref[6], ref[7]);

    const int delays[] = {15, 10, 6, 4, 2, 1, 0};
    for (size_t i = 0; i < sizeof(delays)/sizeof(delays[0]); i++) {
        g_delay = delays[i];
        struct timespec t0, t1;
        clock_gettime(CLOCK_MONOTONIC, &t0);
        int ok = 1;
        for (int rep = 0; rep < 4; rep++) {
            nand_read_page_slice(2 * PAGES_PER_BLK, COL_MAIN, cur, PAGE_SIZE);
            if (memcmp(ref, cur, PAGE_SIZE) != 0) { ok = 0; break; }
        }
        clock_gettime(CLOCK_MONOTONIC, &t1);
        double dt = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) * 1e-9;
        printf("  delay=%2d: %s  (%.2f KiB/s, 2MiB est=%.0fs)\n",
               g_delay, ok ? "PASS (4x identical)" : "FAIL (mismatch!)",
               (4 * 2.0) / dt, 2048.0 / ((4 * 2.0) / dt));
    }
}

static void do_dump_blocks(const char *list_spec, const char *out_path, int with_oob) {
    int blocks[TOTAL_BLOCKS];
    int nblocks = 0;

    /* Parse comma-separated numbers or start-end ranges */
    char *copy = strdup(list_spec);
    for (char *tok = strtok(copy, ","); tok; tok = strtok(NULL, ",")) {
        char *dash = strchr(tok, '-');
        if (dash) {
            int a = atoi(tok), b = atoi(dash + 1);
            for (int x = a; x <= b && nblocks < TOTAL_BLOCKS; x++) blocks[nblocks++] = x;
        } else {
            if (nblocks < TOTAL_BLOCKS) blocks[nblocks++] = atoi(tok);
        }
    }
    free(copy);

    FILE *f = fopen(out_path, "wb");
    if (!f) { perror(out_path); return; }

    uint16_t start_col = with_oob ? COL_OOB : COL_MAIN;
    int read_len = with_oob ? (PAGE_SIZE + OOB_SIZE) : PAGE_SIZE;
    uint8_t page_buf[PAGE_SIZE + OOB_SIZE];
    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);

    size_t total_bytes = (size_t)nblocks * PAGES_PER_BLK * read_len;
    size_t done_bytes = 0;
    printf("Dumping %d blocks (%zu bytes, col=0x%04X, delay=%d, with_oob=%d) -> %s\n",
           nblocks, total_bytes, start_col, g_delay, with_oob, out_path);

    for (int bi = 0; bi < nblocks && !g_stop; bi++) {
        int blk = blocks[bi];
        for (int pg = 0; pg < PAGES_PER_BLK && !g_stop; pg++) {
            uint32_t row = (uint32_t)blk * PAGES_PER_BLK + (uint32_t)pg;
            if (nand_read_page_slice(row, start_col, page_buf, read_len) != 0) {
                fprintf(stderr, "TIMEOUT at blk %d pg %d! Retrying...\n", blk, pg);
                nand_reset();
                if (nand_read_page_slice(row, start_col, page_buf, read_len) != 0) {
                    fprintf(stderr, "FATAL TIMEOUT at blk %d pg %d!\n", blk, pg);
                    fclose(f);
                    return;
                }
            }
            fwrite(page_buf, 1, read_len, f);
            done_bytes += read_len;
        }
        clock_gettime(CLOCK_MONOTONIC, &t1);
        double dt = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) * 1e-9;
        printf("  [%2d/%2d] blk %4d done  (%.1f%%, %.2f KiB/s, %.1fs)\n",
               bi + 1, nblocks, blk, 100.0 * done_bytes / total_bytes,
               (done_bytes / 1024.0) / (dt > 0.001 ? dt : 0.001), dt);
        fflush(stdout);
    }
    fclose(f);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    double dt = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) * 1e-9;
    printf("DONE: %zu bytes in %.2fs (%.2f KiB/s)\n", done_bytes, dt, (done_bytes / 1024.0) / dt);
}

int main(int argc, char **argv) {
    signal(SIGINT, on_sig);
    signal(SIGTERM, on_sig);

    const char *mode = NULL;
    const char *spec = NULL;
    const char *out_path = NULL;
    int with_oob = 0;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--delay") && i + 1 < argc) g_delay = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--we") && i + 1 < argc) g_we_mask = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--bs") && i + 1 < argc) g_bs_low = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--with-oob")) with_oob = 1;
        else if (!strcmp(argv[i], "--probe")) mode = "probe";
        else if (!strcmp(argv[i], "--speed-test")) mode = "speed";
        else if (!strcmp(argv[i], "--scan-oob")) {
            mode = "scan";
            if (i + 1 < argc && argv[i + 1][0] != '-') out_path = argv[++i];
        } else if (!strcmp(argv[i], "--dump-blocks") && i + 2 < argc) {
            mode = "dump";
            spec = argv[++i];
            out_path = argv[++i];
        }
    }

    if (!mode) {
        fprintf(stderr,
            "Usage:\n"
            "  %s --probe [--delay N]\n"
            "  %s --scan-oob [oob_all.bin] [--delay N] [--we MASK] [--bs 0|1]\n"
            "  %s --dump-blocks 0-15 out.bin [--with-oob] [--delay N] [--we MASK] [--bs 0|1]\n",
            argv[0], argv[0], argv[0]);
        return 1;
    }

    if (gpio_init() != 0) return 1;
    jtag_reset_idle();
    uint32_t id = (uint32_t)jtag_shift_dr(0, 32);
    printf("JTAG IDCODE=0x%08X (delay=%d, we_mask=0x%X, bs_low=%d)\n", id, g_delay, g_we_mask, g_bs_low);
    if (id != 0x0000100F) {
        fprintf(stderr, "Unexpected IDCODE!\n");
        gpio_cleanup();
        return 1;
    }

    /* Safe entry to EXTEST via SAMPLE/PRELOAD */
    jtag_reset_idle();
    jtag_shift_ir16(IR_SAMPLE);
    init_idle();
    bsr_shift();
    jtag_shift_ir16(IR_EXTEST);

    if (!strcmp(mode, "probe")) do_probe();
    else if (!strcmp(mode, "speed")) {
        nand_reset();
        do_speed_test();
    } else if (!strcmp(mode, "scan")) {
        nand_reset();
        uint8_t nid[4]; nand_read_id(nid);
        printf("NAND ID: %02X %02X %02X %02X\n", nid[0], nid[1], nid[2], nid[3]);
        if (nid[0] != 0xAD || nid[1] != 0xF1) {
            fprintf(stderr, "Unexpected NAND ID!\n");
        } else {
            do_scan_oob(out_path);
        }
    } else if (!strcmp(mode, "dump")) {
        nand_reset();
        uint8_t nid[4]; nand_read_id(nid);
        printf("NAND ID: %02X %02X %02X %02X\n", nid[0], nid[1], nid[2], nid[3]);
        if (nid[0] != 0xAD || nid[1] != 0xF1) {
            fprintf(stderr, "Unexpected NAND ID!\n");
        } else {
            do_dump_blocks(spec, out_path, with_oob);
        }
    }

    /* Safe exit */
    nand_deselect();
    jtag_reset_idle();
    for (int i = 0; i < 6; i++) jtag_clock(1, 0);
    gpio_cleanup();
    return 0;
}
