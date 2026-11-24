; Decimator (FX 12)
; IRAM 0x177D..0x17B9 (61 words)

.org 0x177D
fx_deci:
    r0 = *dp0++                                ; 177D: 4F821000
    r5 = *dp0++                                ; 177E: 4F821500
    r0 = mul r0, r5                            ; 177F: 81A00000
    r6 = *dp4++                                ; 1780: 4C710016
    r7 = *dp4++                                ; 1781: 4C710017
    acc+ r4 <- r6                              ; 1782: 6CD00000
    abs r1 <- r6                               ; 1783: 64C40000
    abs r2 <- r7                               ; 1784: 64E80000
    r3 = sub r2, r1                            ; 1785: A92C0000
    if (r3 >0) acc+ r4 <- r7                   ; 1786: 6CF00023
    r1eh = *dp3 r1l = *dp7                     ; 1787: 4F13C9C9
    r2 = *dp0++                                ; 1788: 4F821200
    r2 = mul r2, r1                            ; 1789: A1280000
    r4 = r4 or 0x1                             ; 178A: 5B900001
    abs r4 <- r4                               ; 178B: 64900000
    r1 = sub r2, r4                            ; 178C: A9840000
    if (r1 <0) acc+ r2 <- r4                   ; 178D: 6C880039
    *dp3++ = r2h *dp7++ = r2l                  ; 178E: 4D10D2D2
    r1eh = *dp3 r1l = *dp7                     ; 178F: 4F13C9C9
    r3 = *dp0++                                ; 1790: 4F821300
    r1 = msub r1, r3                           ; 1791: 93640000
    r1 = madd r2, r3                           ; 1792: A2640000
    *dp3++ = r1h *dp7++ = r1l                  ; 1793: 4D10D1D1
    r2eh = *dp3 r2l = *dp7                     ; 1794: 4F13CACA
    clr r3 <- r0                               ; 1795: 610C0000
    neg r0 <- r0                               ; 1796: 66000000
    if (r2 ==0) acc+ r3 <- r0                  ; 1797: 6C0C0012
    r0 = *dp0++                                ; 1798: 4F821000
    r4 = *dp0++                                ; 1799: 4F821400
    r5 = add r5, r3 r3 = *dp0++                ; 179A: D8761300
    r3l = *dp0++                               ; 179B: 4C821300
    r5 = sub r1, r5                            ; 179C: 99B40000
    clip r5 <- r5                              ; 179D: 67B40000
    if (r5 >0) acc+ r0 <- r4                   ; 179E: 6C800025
    clr r4 <- r0                               ; 179F: 61100000
    if (r5 >0) acc+ r4 <- r3                   ; 17A0: 6C700025
    *dp3++ = r4h *dp7++ = r4l                  ; 17A1: 4D10D4D4
    r2eh = *dp3 r2l = *dp7                     ; 17A2: 4F13CACA
    r1eh = *dp3 r1l = *dp7                     ; 17A3: 4F13C9C9
    r1 = madd r0, r4                           ; 17A4: 82840000
    r1 = msub r0, r2                           ; 17A5: 83440000
    *dp3++ = r1h *dp7++ = r1l                  ; 17A6: 4D10D1D1
    r6 = mul r6, r1                            ; 17A7: E1380000
    r7 = mul r7, r1                            ; 17A8: F13C0000
    r0 = *dp0++                                ; 17A9: 4F821000
    r6 = and r6, r0                            ; 17AA: EA180000
    r7 = and r7, r0                            ; 17AB: FA1C0000
    r0eh = *dp3                                ; 17AC: 4F02C800
    r1 = *dp0++                                ; 17AD: 4F821100
    r2 = add r0, r1                            ; 17AE: 88280000
    *dp3 = r2h *dp7++ = r2l                    ; 17AF: 4D10CAD2
    r2eh = *dp3++                              ; 17B0: 4F02D200
    r2 = r2 or 0x1                             ; 17B1: 5B480001
    r4 = *dp3 r5 = *dp7                        ; 17B2: 4FF3CCCD
    r0 = sub r2, r0                            ; 17B3: A9000000
    if (r0 <0) acc+ r4 <- r6                   ; 17B4: 6CD00038
    if (r0 <0) acc+ r5 <- r7                   ; 17B5: 6CF40038
    *dp3++ = r4h *dp7++ = r5h                  ; 17B6: 4D20D4D5
    *dp4++ = r4h                               ; 17B7: 4C200014
    *dp4++ = r5h                               ; 17B8: 4C200015
    ret                                        ; 17B9: 24000000
