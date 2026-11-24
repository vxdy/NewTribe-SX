; Ring Modulator (FX 7)
; IRAM 0x1446..0x1483 (62 words)

.org 0x1446
fx_ringmod:
    r0 = *dp0++                                ; 1446: 4F821000
    r7eh = *dp3 r7l = *dp7                     ; 1447: 4F13CFCF
    r7 = msub r7, r0 r2 = *dp0++               ; 1448: F31E1200
    r7 = madd r2, r0                           ; 1449: A21C0000
    *dp3++ = r7h *dp7++ = r7l                  ; 144A: 4D10D7D7
    r1eh = *dp3 r1l = *dp7                     ; 144B: 4F13C9C9
    r1 = sub r1, r7                            ; 144C: 99E40000
    *dp3 = r1h *dp7++ = r1l                    ; 144D: 4D10C9D1
    r1eh = *dp3++                              ; 144E: 4F02D100
    abs r3 <- r1 r4 = *dp0++                   ; 144F: 742E1400
    r4 = sub r4, r3                            ; 1450: C9700000
    r4 = r4 sll 0x1                            ; 1451: 5F900001
    clip r1 <- r4 r0 = *dp0++                  ; 1452: 77861000
    r0l = *dp0++                               ; 1453: 4C821000
    r1 = mul r4, r4 r3 = *dp0++                ; 1454: C1861300
    r3l = *dp0++                               ; 1455: 4C821300
    clr r2 <- r0                               ; 1456: 61080000
    r2 = suma r1, r3                           ; 1457: 94680000
    r2 = mas16 r1, r3 r3 = *dp0++              ; 1458: 976A1300
    r3l = *dp0++                               ; 1459: 4C821300
    r2 = add r2, r3                            ; 145A: A8680000
    clip r2 <- r2                              ; 145B: 67480000
    r2 = mul r2, r1 r3 = *dp0++                ; 145C: A12A1300
    r3l = *dp0++                               ; 145D: 4C821300
    r2 = add r2, r3                            ; 145E: A8680000
    clip r2 <- r2                              ; 145F: 67480000
    r2 = mul r2, r4                            ; 1460: A1880000
    r4 = add r2, r4                            ; 1461: A8900000
    clip r4 <- r4                              ; 1462: 67900000
    r6 = r7 sll 0x4                            ; 1463: 5FF80004
    clip r6 <- r6                              ; 1464: 67D80000
    r6 = r6 sll 0x4                            ; 1465: 5FD80004
    clip r6 <- r6                              ; 1466: 67D80000
    r7 = sub r0, r6                            ; 1467: 89DC0000
    r6 = mul r4, r6                            ; 1468: C1D80000
    r6 = add r6, r7                            ; 1469: E8F80000
    clip r6 <- r6                              ; 146A: 67D80000
    r4 = *dp0++                                ; 146B: 4F821400
    r3eh = *dp3 r3l = *dp7                     ; 146C: 4F13CBCB
    r3 = msub r3, r4 r5 = *dp0++               ; 146D: B38E1500
    r3 = madd r5, r4 r4 = *dp0++               ; 146E: D28E1400
    *dp3++ = r3h *dp7++ = r3l                  ; 146F: 4D10D3D3
    r5 = mul r3, r4                            ; 1470: B1940000
    r5 = r5 sll 0x3                            ; 1471: 5FB40003
    clip r5 <- r5                              ; 1472: 67B40000
    r0 = sub r0, r3                            ; 1473: 89600000
    r0 = mul r0, r4                            ; 1474: 81800000
    r0 = r0 sll 0x3                            ; 1475: 5F000003
    clip r0 <- r0                              ; 1476: 67000000
    r1 = *dp4++                                ; 1477: 4C710011
    r2 = *dp4++                                ; 1478: 4C710012
    r3 = mul r1, r6                            ; 1479: 91CC0000
    r4 = mul r2, r6                            ; 147A: A1D00000
    r3 = mul r3, r5                            ; 147B: B1AC0000
    r4 = mul r4, r5                            ; 147C: C1B00000
    r3 = madd r1, r0                           ; 147D: 920C0000
    r4 = madd r2, r0                           ; 147E: A2100000
    clip r3 <- r3                              ; 147F: 676C0000
    clip r4 <- r4                              ; 1480: 67900000
    *dp4++ = r3h                               ; 1481: 4C200013
    *dp4++ = r4h                               ; 1482: 4C200014
    ret                                        ; 1483: 24000000
