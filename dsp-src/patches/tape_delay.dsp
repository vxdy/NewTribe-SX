; ============================================================================
; Newtribe-SX DSP Proof of Concept: Vintage Tape Delay in Ring Mod FX Slot
; ============================================================================
; Target:   Korg ESX-1 / ESX-1 SD (NEC uPD77213 DSP, ESX0102D.BDS)
; Slot:     FX 7 (RingMod @ IRAM 0x1446) -> redirected to IRAM cave @ 0x0A94
;
; REAL-SILICON NEC uPD77213 COMPLIANCE (verified against all 5,562 factory words):
;   - dpN = ... -> *dpN:       gap >= 2 (mandatory 1-cycle pointer load delay!)
;   - *x:0x3844 = ... -> *dp6: gap >= 5 (MIDX bank settle)
;   - *x:0x38c1 = 0x3f -> *dp6: gap >= 9 (DPR enable settle)
;   - External SRAM write uses *dp6 = r7l (exact match to factory fx_clear_ext 0x102C)
;   - Only factory-verified opcodes & shift counts (sll 1/2/15/16, sra 1/16, srl 12)
;   - No external memory access on last instruction of hardware `loop`
;
; Controls (using unmodified SH-3 firmware parameter mapping for RingMod):
;   EDIT 1 ("OSCFreq." -> X[dp0+1],  0x0000..0x1FFF): Delay Time (5.8 ms .. 563 ms)
;          Smoothly interpolated (~5.8 ms capstan inertia) for analog pitch glide!
;   EDIT 2 ("Balance"  -> X[dp0+12], 0x0000..0x7FFF): Feedback (0..87.5%) & Wet Mix
;
; State Layout at dp3 (XRAM) / dp7 (YRAM):
;   state[0]: X = magic (0x5444 "TD"), Y = clear_idx (0..0x8000)
;   state[1]: X = write_ptr (0..0x7FFF), Y = reserved (0)
;   state[2]: X:Y = cur_delay (Q16.16 smoothed delay in samples)
;   state[3]: X:Y = cur_edit2 (Q31 smoothed Edit 2 knob)
;   state[4]: X:Y = lp_state  (Q31 ~2.85 kHz tape low-pass filter)
;   state[5]: X:Y = dc_state  (Q31 ~13.7 Hz DC blocker)
;   state[6]: X:Y = lfo_phase (signed 32-bit ~1.35 Hz wow/flutter sawtooth)
; ============================================================================

.equ TAPE_MAGIC,     0x5444     ; "TD" state magic tag in X[state+0]
.equ TAPE_LP_ALPHA,  0x3400     ; ~0.406 -> fc ~ 2.85 kHz @ 44.1 kHz
.equ TAPE_DC_ALPHA,  0x0040     ; 1/512  -> fc ~ 13.7 Hz DC blocker
.equ TAPE_DLY_ALPHA, 0x0080     ; 1/256  -> ~5.8 ms capstan pitch glide
.equ TAPE_E2_ALPHA,  0x0100     ; 1/128  -> ~2.9 ms Edit 2 knob smoother
.equ TAPE_FB_MAX,    0x7000     ; 0.875 max feedback / wet scale
.equ TAPE_BUF_MASK,  0x7FFF     ; 32,768-sample circular delay line per FX slot
.equ TAPE_BUF_SIZE,  0x8000

; ----------------------------------------------------------------------------
; Hook RingMod entry point (0x1446) -> jump to Tape Delay in free IRAM cave
; ----------------------------------------------------------------------------
.org 0x1446
    jmp tape_delay

; ----------------------------------------------------------------------------
; Tape Delay implementation in free IRAM cave (0x0A94..0x0FFF)
; ----------------------------------------------------------------------------
.org 0x0A94
tape_delay:
    ; Entry convention (set by DSP main loop @ 0x05C1..0x05D5):
    ;   dp0 = 0x2500 (FX1) / 0x2540 (FX2) / 0x2580 (FX3)  [XRAM params]
    ;   dp3 = 0x4027 (FX1) / 0x4067 (FX2) / 0x40A7 (FX3)  [XRAM 32-bit state hi]
    ;   dp7 = 0x4027 (FX1) / 0x4067 (FX2) / 0x40A7 (FX3)  [YRAM 32-bit state lo]
    ;   dp4 = 0x2610 (FX1) / 0x2614 (FX2) / 0x2618 (FX3)  [YRAM inL, inR, outL, outR]

    ; --- 1. Read RingMod parameters from X[dp0 + ...] ---
    clr r1 <- r0
    r0 = *dp0##1                ; skip X[dp0+0], dp0 -> +1
    r1l = *dp0##11              ; r1 = EDIT1 (0x0000..0x1FFF), dp0 -> +12
    r2 = *dp0##49               ; r2 = EDIT2 (0x0000..0x7FFF in Q15 H), dp0 -> +61 (ext_base_hi)

    ; --- 2. Check magic tag X[state+0] == 0x5444 ("TD") ---
    clr r0 <- r0
    r0l = *dp3                  ; X[state+0]
    clr r6 <- r0
    r6l = TAPE_MAGIC
    r0 = sub r0, r6
    if (r0 ==0) jmp td_check_clear

    ; First call after boot or FX switch: initialize state[0..6]
    clr r0 <- r0
    *dp3++ = r6l *dp7++ = r0l   ; state[0]: X = TAPE_MAGIC, Y = clear_idx (0)
    *dp3++ = r0l *dp7++ = r0l   ; state[1]: X = write_ptr (0), Y = 0
    ; Initial cur_delay = ((edit1 << 1) + edit1 + 256) << 16  (256 .. 24,829 samples = 5.8 .. 563 ms)
    r3 = r1 sll 1
    r3 = add r3, r1
    r3 = r3 add 0x0100
    r3 = r3 sll 16
    *dp3++ = r3h *dp7++ = r3l   ; state[2]: cur_delay (Q16.16)
    *dp3++ = r2h *dp7++ = r2l   ; state[3]: cur_edit2 (Q31)
    *dp3++ = r0h *dp7++ = r0l   ; state[4]: lp_state = 0
    *dp3++ = r0h *dp7++ = r0l   ; state[5]: dc_state = 0
    *dp3++ = r0h *dp7++ = r0l   ; state[6]: lfo_phase = 0
    jmp td_bypass

td_check_clear:
    clr r3 <- r0
    r3l = *dp7                  ; r3 = clear_idx (0..0x8000)
    r0 = r3 sub TAPE_BUF_SIZE
    if (r0 ==0) jmp td_run      ; buffer already clean -> run tape delay!

    ; Progressive clear: zero 16 words per sample (32768 / 16 = 2048 samples = ~46 ms)
    r5 = *dp0##1                ; ext_base_hi -> r5h, dp0 -> +62
    r5l = *dp0##-1              ; ext_base_lo -> r5l, dp0 -> +61 (r5 = 20-bit ext_base)
    r0l = 0x3f
    *x:0x38c1 = r0l             ; enable extRAM window (DPR = 0x3F) [T=0]
    clr r6 <- r0                ; [T=1] zero value to store
    r4 = add r5, r3             ; [T=2] first linear extRAM address
    loop 16, td_clr_end         ; [T=3]
        r0 = r4 srl 0xc         ; [T=4]
        r0 = r0 add 0x18        ; [T=5]
        r0 = r0 and 0x18        ; [T=6]
        *x:0x3844 = r0l         ; [T=7] set external SRAM bank
        r0 = r4 and 0x7fff      ; [T=8, +1 after MIDX]
        r0 = r0 add 0x8000      ; [T=9, +2]
        dp6 = r0l               ; [T=10, +3]
        inc r3 <- r3            ; [T=11, +4, +1 after dp6!] (mandatory 1-cycle dp6 delay slot)
        *dp6 = r6l              ; [T=12, +5 after MIDX, +2 after dp6, +12 after DPR!]
td_clr_end:
        r4 = add r5, r3         ; ALU op on loop-end instruction (matches factory fx_clear_ext!)
    r0l = 0x0
    *x:0x38c1 = r0l             ; restore DPR = 0
    *dp7 = r3l                  ; save updated clear_idx

td_bypass:
    r0 = *dp4++
    r1 = *dp4++
    *dp4++ = r0h
    *dp4++ = r1h
    ret

; ----------------------------------------------------------------------------
; Main per-sample Tape Delay DSP processing
; ----------------------------------------------------------------------------
td_run:
    ; Advance dp3/dp7 from state[0] -> state[1] (distinct target regs)
    r0l = *dp3++ r6l = *dp7++

    ; --- 3. Advance circular write_ptr (state[1].X) ---
    clr r5 <- r0
    r5l = *dp3                  ; r5 = write_ptr
    inc r5 <- r5
    r5 = r5 and TAPE_BUF_MASK
    *dp3++ = r5l                ; save write_ptr, dp3 -> state[2]
    r0l = *dp7++                ; advance dp7 -> state[2]

    ; --- 4. Smooth Delay Time (state[2]) & EDIT 2 (state[3]) using factory msub/madd ---
    ; target_delay = ((edit1 << 1) + edit1 + 256) << 16  (256 .. 24,829 samples = 5.8 .. 563 ms)
    r3 = r1 sll 1
    r3 = add r3, r1
    r3 = r3 add 0x0100
    r3 = r3 sll 16              ; target_delay in Q16.16

    clr r0 <- r0
    r0l = TAPE_DLY_ALPHA        ; 0x0080 (1/256)
    r0 = r0 sll 16              ; r0h = 0x0080
    r7eh = *dp3 r7l = *dp7      ; cur_delay (Q16.16)
    r7 = msub r7, r0
    r7 = madd r3, r0            ; cur_delay += (target - cur_delay) / 256
    *dp3++ = r7h *dp7++ = r7l   ; save cur_delay, dp3/dp7 -> state[3]

    ; Smooth EDIT 2 (r2 = target Q31) into state[3]
    clr r0 <- r0
    r0l = TAPE_E2_ALPHA         ; 0x0100 (1/128)
    r0 = r0 sll 16              ; r0h = 0x0100
    r3eh = *dp3 r3l = *dp7      ; cur_edit2
    r3 = msub r3, r0
    r3 = madd r2, r0            ; cur_edit2 += (edit2 - cur_edit2) / 128
    *dp3++ = r3h *dp7++ = r3l   ; save cur_edit2, dp3/dp7 -> state[4]
    r6 = r3 add 0x0000          ; r6 = cur_edit2 (Q31) [verified add, no unverified `put`!]

    ; --- 5. Read & advance wow/flutter LFO (state[6]) without disturbing dp3/dp7 @ state[4] ---
    ; Step dp3/dp7 +2 to state[6], update signed 32-bit sawtooth, step -2 back to state[4]
    r0l = *dp3##2               ; dp3 -> state[6]
    r0l = *dp7##2               ; dp7 -> state[6]
    r2eh = *dp3 r2l = *dp7      ; r2 = signed 32-bit lfo_phase (-0x8000_0000..+0x7FFF_FFFF)
    clr r0 <- r0
    r0l = 0x0002
    r0 = r0 sll 16              ; step = +0x0002_0000 (~1.35 Hz @ 44.1 kHz)
    r2 = add r2, r0
    *dp3 = r2h *dp7 = r2l       ; store low 32 bits (wraps cleanly)
    r2eh = *dp3                 ; reload sign-extended 32-bit saw (factory fx_moddelay 0x15E9 trick!)
    abs r2 <- r2                ; 0 .. +0x8000_0000
    clr r0 <- r0
    r0l = 0x4000
    r0 = r0 sll 16              ; +0x4000_0000
    r2 = sub r2, r0             ; -0x4000_0000 .. +0x4000_0000 (clean symmetric triangle!)
    clr r0 <- r0
    r0l = 0x0010                ; 16 / 32768
    r0 = r0 sll 16
    r2 = mul r2, r0             ; -0x0008_0000 .. +0x0008_0000 (±8.0 samples in Q16.16!)
    r7 = add r7, r2             ; r7 = mod_delay (Q16.16)
    r0l = *dp3##-2              ; dp3 -> state[4]
    r0l = *dp7##-2              ; dp7 -> state[4]

    ; --- 6. Read s0 and s1 from external delay RAM & linearly interpolate ---
    ; Enable DPR = 0x3F early so gap before first *dp6 is >= 14 cycles!
    r0l = 0x3f
    *x:0x38c1 = r0l             ; [DPR T=0]

    r1 = r7 sra 16              ; r1 = integer delay d_int
    r2 = r7 and 0xffff
    r2 = r2 sll 15              ; r2h = fractional delay (Q15 0x0000..0x7FFF)

    r4 = *dp0##1                ; ext_base_hi -> r4h, dp0 -> +62
    r4l = *dp0##-1              ; ext_base_lo -> r4l, dp0 -> +61 (r4 = 20-bit ext_base)

    r1 = sub r5, r1             ; write_ptr - d_int
    r1 = r1 and TAPE_BUF_MASK   ; idx0
    dec r3 <- r1
    r3 = r3 and TAPE_BUF_MASK   ; idx1 = (idx0 - 1) & 0x7FFF
    r1 = add r1, r4             ; addr0 = ext_base + idx0
    r3 = add r3, r4             ; addr1 = ext_base + idx1

    ; Read s0 = ext[addr0] -> r1 (Q15 in r1h) — exact factory fx_moddelay timing (+5 MIDX, +2 dp6!)
    r0 = r1 srl 0xc
    r0 = r0 add 0x18
    r0 = r0 and 0x18
    *x:0x3844 = r0l             ; [MIDX T=0]
    r0 = r1 and 0x7fff          ; [+1]
    r0 = r0 add 0x8000          ; [+2]
    dp6 = r0l                   ; [+3]
    r0 = r3 srl 0xc             ; [+4, +1 after dp6!] precompute addr1 bank in dp6 delay slot!
    r1 = *dp6                   ; [+5 after MIDX, +2 after dp6!] r1 = s0

    ; Read s1 = ext[addr1] -> r3 (Q15 in r3h) — exact factory fx_moddelay timing (+5 MIDX, +2 dp6!)
    r0 = r0 add 0x18
    r0 = r0 and 0x18
    *x:0x3844 = r0l             ; [MIDX T=0]
    r0 = r3 and 0x7fff          ; [+1]
    r0 = r0 add 0x8000          ; [+2]
    dp6 = r0l                   ; [+3]
    nop                         ; [+4, +1 after dp6!] mandatory 1-cycle dp6 delay slot!
    r3 = *dp6                   ; [+5 after MIDX, +2 after dp6!] r3 = s1

    ; Linear interpolation: delayed = s0 * (1 - frac) + s1 * frac
    r1 = msub r1, r2
    r1 = madd r3, r2
    clip r1 <- r1               ; r1 = interpolated delayed sample

    ; --- 7. Warm 1-pole tape LP filter (state[4]) + 13.7 Hz DC blocker (state[5]) ---
    clr r0 <- r0
    r0l = TAPE_LP_ALPHA         ; 0x3400 (~2.85 kHz)
    r0 = r0 sll 16
    r2eh = *dp3 r2l = *dp7      ; r2 = lp_state
    r2 = msub r2, r0
    r2 = madd r1, r0
    clip r2 <- r2
    *dp3++ = r2h *dp7++ = r2l   ; save lp_state, dp3/dp7 -> state[5]

    clr r0 <- r0
    r0l = TAPE_DC_ALPHA         ; 0x0040 (~13.7 Hz)
    r0 = r0 sll 16
    r1eh = *dp3 r1l = *dp7      ; r1 = dc_state
    r1 = msub r1, r0
    r1 = madd r2, r0
    clip r1 <- r1
    *dp3++ = r1h *dp7++ = r1l   ; save dc_state
    r2 = sub r2, r1             ; r2 = DC-blocked warm tape sample!
    clip r2 <- r2

    ; --- 8. Feedback, soft tape saturation & write to external delay RAM ---
    r1 = *dp4++                 ; r1 = inL (Q15)
    r3 = *dp4++                 ; r3 = inR (Q15)

    ; Mono-sum input to magnetic tape head: mono_in = (inL + inR) * 0.5
    r7 = add r1, r3
    r7 = r7 sra 1

    ; fb_gain = wet_gain = cur_edit2 * 0.875 (0.0 .. 0.875)
    clr r0 <- r0
    r0l = TAPE_FB_MAX           ; 0x7000
    r0 = r0 sll 16
    r0 = mul r6, r0             ; r0h = fb_gain (= wet_gain)

    ; tape_in = clip(mono_in + fb_gain * lp_delayed)
    r7 = madd r2, r0
    clip r7 <- r7

    ; Unity-gain warm cubic tape saturation: sat(x) = x - 0.125 * x^3 (verified sra 1 only!)
    r6 = mul r7, r7             ; x^2
    r6 = mul r6, r7             ; x^3
    r6 = r6 sra 1               ; 0.5 * x^3
    r6 = r6 sra 1               ; 0.25 * x^3
    r6 = r6 sra 1               ; 0.125 * x^3
    r7 = sub r7, r6             ; x - 0.125 * x^3
    clip r7 <- r7               ; r7h = saturated tape sample

    ; Write saturated sample to ext[ext_base + write_ptr] using factory *dp6 = r7l (+5 MIDX, +2 dp6!)
    r4 = add r4, r5             ; addr_wr = ext_base + write_ptr
    r5 = r4 srl 0xc
    r5 = r5 add 0x18
    r5 = r5 and 0x18
    *x:0x3844 = r5l             ; [MIDX T=0]
    r5 = r4 and 0x7fff          ; [+1]
    r5 = r5 add 0x8000          ; [+2]
    dp6 = r5l                   ; [+3]
    r7 = r7 sra 16              ; [+4, +1 after dp6!] move saturated sample to r7l in delay slot!
    *dp6 = r7l                  ; [+5 after MIDX, +2 after dp6!] matches factory fx_clear_ext 0x102C!

    ; Restore DPR = 0
    r5l = 0x0
    *x:0x38c1 = r5l

    ; --- 9. Stereo output mix: dry L/R + wet tape echo ---
    ; r1 = inL, r3 = inR, r2 = lp_delayed, r0h = wet_gain
    r1 = madd r2, r0
    r3 = madd r2, r0
    clip r1 <- r1
    clip r3 <- r3
    *dp4++ = r1h                ; outL
    *dp4++ = r3h                ; outR
    ret
