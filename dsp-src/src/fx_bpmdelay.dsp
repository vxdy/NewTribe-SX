; BPM Delay (FX 1)
; IRAM 0x1344..0x1361 (30 words)

.org 0x1344
fx_bpmdelay:
    r1eh = *dp3 r1l = *dp7                     ; 1344: 4F13C9C9
    clr r7 <- r0 r0 = *dp0++                   ; 1345: 711E1000
    r1 = msub r1, r0 r2 = *dp0++               ; 1346: 93061200
    r1 = madd r2, r0 r0 = *dp0++               ; 1347: A2061000
    *dp3++ = r1h *dp7++ = r1l                  ; 1348: 4D10D1D1
    r2eh = *dp3 r2l = *dp7                     ; 1349: 4F13CACA
    r2 = msub r2, r0 r3 = *dp0++               ; 134A: A30A1300
    r2 = madd r3, r0 r4 = *dp4++               ; 134B: B2090014
    *dp3++ = r2h *dp7++ = r2l                  ; 134C: 4D10D2D2
    r5 = mul r4, r2 r4 = *dp4++                ; 134D: C1550014
    r6 = mul r4, r2                            ; 134E: C1580000
    r7l = *dp0++                               ; 134F: 4C821700
    r4 = r7 add 0x2400                         ; 1350: 58F02400
    dp1 = r4l                                  ; 1351: 3E020000
    clr r0 <- r0 r3 = *dp0++                   ; 1352: 71021300
    r2 = *dp1++                                ; 1353: 4F825200
    r2 = mul r2, r3                            ; 1354: A1680000
    r6 = msub r2, r1 r2 = *dp1++               ; 1355: A33A5200
    clip r6 <- r6                              ; 1356: 67D80000
    r2 = mul r2, r3                            ; 1357: A1680000
    r5 = msub r2, r1                           ; 1358: A3340000
    clip r5 <- r5                              ; 1359: 67B40000
    *dp4++ = r5h                               ; 135A: 4C200015
    *dp4++ = r6h                               ; 135B: 4C200016
    r0 = r7 add 0x2410                         ; 135C: 58E02410
    dp1 = r0l                                  ; 135D: 3C020000
    nop                                        ; 135E: 00000000
    *dp1++ = r5h                               ; 135F: 4D005500
    *dp1++ = r6h                               ; 1360: 4D005600
    ret                                        ; 1361: 24000000
