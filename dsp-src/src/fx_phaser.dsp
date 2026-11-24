; Phaser (FX 6)
; IRAM 0x1484..0x1537 (180 words)

.org 0x1484
fx_phaser:
    r0eh = *dp3 r0l = *dp7                     ; 1484: 4F13C8C8
    r1 = *dp0++                                ; 1485: 4F821100
    r1l = *dp0++                               ; 1486: 4C821100
    r0 = add r0, r1                            ; 1487: 88200000
    *dp3 = r0h *dp7++ = r0l                    ; 1488: 4D10C8D0
    r0eh = *dp3++                              ; 1489: 4F02D000
    r0 = r0 or 0x1                             ; 148A: 5B000001
    abs r1 <- r0 r5 = *dp0++                   ; 148B: 74061500
    r5 = add r0, r5                            ; 148C: 88B40000
    *dp3 = r5h *dp7++ = r5l                    ; 148D: 4D10CDD5
    r5eh = *dp3++                              ; 148E: 4F02D500
    abs r5 <- r5                               ; 148F: 64B40000
    r2 = r1 sll 0x1                            ; 1490: 5F280001
    clip r2 <- r2                              ; 1491: 67480000
    r2 = mul r2, r1 r1 = *dp0++                ; 1492: A12A1100
    r0eh = *dp3 r0l = *dp7                     ; 1493: 4F13C8C8
    r3 = mul r0, r1                            ; 1494: 812C0000
    r3 = msub r1, r2 r1 = *dp0++               ; 1495: 934E1100
    r3 = madd r1, r2 r2 = *dp0++               ; 1496: 924E1200
    r3 = r3 sll 0x2                            ; 1497: 5F6C0002
    clip r3 <- r3                              ; 1498: 676C0000
    *dp3++ = r3h *dp7++ = r3l                  ; 1499: 4D10D3D3
    clr r6 <- r0                               ; 149A: 61180000
    r6 = suma r2, r3                           ; 149B: A4780000
    r6 = mas16 r3, r2                          ; 149C: B7580000
    neg r2 <- r6                               ; 149D: 66C80000
    r1 = *dp0##-3                              ; 149E: 44F1FFFD
    r2 = madd r1, r1                           ; 149F: 92280000
    clip r6 <- r2                              ; 14A0: 67580000
    r2 = r5 sll 0x1                            ; 14A1: 5FA80001
    clip r2 <- r2                              ; 14A2: 67480000
    r2 = mul r2, r5 r1 = *dp0++                ; 14A3: A1AA1100
    r0eh = *dp3 r0l = *dp7                     ; 14A4: 4F13C8C8
    r3 = mul r0, r1                            ; 14A5: 812C0000
    r3 = msub r1, r2 r1 = *dp0++               ; 14A6: 934E1100
    r3 = madd r1, r2 r2 = *dp0++               ; 14A7: 924E1200
    r3 = r3 sll 0x2                            ; 14A8: 5F6C0002
    clip r3 <- r3                              ; 14A9: 676C0000
    *dp3++ = r3h *dp7++ = r3l                  ; 14AA: 4D10D3D3
    clr r5 <- r0                               ; 14AB: 61140000
    r5 = suma r2, r3                           ; 14AC: A4740000
    r5 = mas16 r3, r2                          ; 14AD: B7540000
    neg r2 <- r5 r1 = *dp0++                   ; 14AE: 76AA1100
    r2 = madd r1, r1                           ; 14AF: 92280000
    clip r3 <- r2 r1 = *dp0++                  ; 14B0: 774E1100
    r5eh = *dp3 r5l = *dp7                     ; 14B1: 4F13CDCD
    r5 = msub r5, r1 r2 = *dp0++               ; 14B2: D3361200
    r5 = madd r2, r1                           ; 14B3: A2340000
    r4 = *dp4                                  ; 14B4: 4C71000C
    *dp3++ = r5h *dp7++ = r5l                  ; 14B5: 4D10D5D5
    *dp0++ = r5h                               ; 14B6: 4D001500
    *dp0++ = r5l                               ; 14B7: 4C801500
    r1l = dp0                                  ; 14B8: 3C810000
    dp1 = r1l                                  ; 14B9: 3C820000
    clr r7 <- r0 r1 = *dp0++                   ; 14BA: 711E1100
    r1l = *dp0++                               ; 14BB: 4C821100
    r7 = suma r5, r1                           ; 14BC: D43C0000
    r7 = suma r1, r5                           ; 14BD: 94BC0000
    r7 = mas16 r1, r5 r1 = *dp0++              ; 14BE: 97BE1100
    r0 = *dp0                                  ; 14BF: 4F820800
    r7 = mul r7, r0                            ; 14C0: F11C0000
    r7 = add r7, r4                            ; 14C1: F89C0000
    clip r7 <- r7 r4 = *dp0--                  ; 14C2: 77FE1C00
    r0eh = *dp3 r0l = *dp7                     ; 14C3: 4F13C8C8
    r0 = mul r0, r4                            ; 14C4: 81800000
    r0 = mul r0, r4                            ; 14C5: 81800000
    *dp3++ = r7h *dp7++ = r7l                  ; 14C6: 4D10D7D7
    r1 = suma r6, r7                           ; 14C7: E4E40000
    r1 = mas16 r7, r6                          ; 14C8: F7C40000
    r0 = sub r0, r1 r2 = *dp0                  ; 14C9: 89220A00
    r1eh = *dp3 r1l = *dp7                     ; 14CA: 4F13C9C9
    r1 = mul r1, r4                            ; 14CB: 91840000
    r1 = mul r1, r4                            ; 14CC: 91840000
    r2 = mul r1, r6                            ; 14CD: 91C80000
    r0 = add r0, r2                            ; 14CE: 88400000
    clip r0 <- r0 r2 = *dp0                    ; 14CF: 77020A00
    *dp3++ = r0h *dp7++ = r0l                  ; 14D0: 4D10D0D0
    r2 = suma r6, r0                           ; 14D1: E4080000
    r2 = mas16 r0, r6                          ; 14D2: 87C80000
    r1 = sub r1, r2 r2 = *dp0                  ; 14D3: 99460A00
    r0eh = *dp3 r0l = *dp7                     ; 14D4: 4F13C8C8
    r0 = mul r0, r4                            ; 14D5: 81800000
    r0 = mul r0, r4                            ; 14D6: 81800000
    r2 = mul r0, r6                            ; 14D7: 81C80000
    r1 = add r1, r2                            ; 14D8: 98440000
    clip r1 <- r1 r2 = *dp0                    ; 14D9: 77260A00
    r1 = mul r1, r4                            ; 14DA: 91840000
    r1 = mul r1, r4                            ; 14DB: 91840000
    r1 = mul r1, r4                            ; 14DC: 91840000
    r1 = mul r1, r4                            ; 14DD: 91840000
    *dp3++ = r1h *dp7++ = r1l                  ; 14DE: 4D10D1D1
    r2 = suma r6, r1 *dp1++ = r1h              ; 14DF: E4285100
    *dp1 = r1l                                 ; 14E0: 4C804900
    r2 = mas16 r1, r6                          ; 14E1: 97C80000
    r0 = sub r0, r2 r2 = *dp0                  ; 14E2: 89420A00
    r1eh = *dp3 r1l = *dp7                     ; 14E3: 4F13C9C9
    r1 = mul r1, r4                            ; 14E4: 91840000
    r1 = mul r1, r4                            ; 14E5: 91840000
    r2 = mul r1, r6                            ; 14E6: 91C80000
    r0 = add r0, r2                            ; 14E7: 88400000
    clip r0 <- r0 r2 = *dp0                    ; 14E8: 77020A00
    *dp3++ = r0h *dp7++ = r0l                  ; 14E9: 4D10D0D0
    r2 = suma r6, r0                           ; 14EA: E4080000
    r2 = mas16 r0, r6                          ; 14EB: 87C80000
    r1 = sub r1, r2 r2 = *dp0++                ; 14EC: 99461200
    r0eh = *dp3 r0l = *dp7                     ; 14ED: 4F13C8C8
    r0 = mul r0, r4 r4 = *dp0++                ; 14EE: 81821400
    r0 = mul r0, r4                            ; 14EF: 81800000
    r2 = mul r0, r6 r4 = *dp4++                ; 14F0: 81C90014
    r1 = add r1, r2                            ; 14F1: 98440000
    clip r1 <- r1 r2 = *dp0++                  ; 14F2: 77261200
    *dp3++ = r1h *dp7++ = r1l                  ; 14F3: 4D10D1D1
    r4 = mul r4, r2 r2 = *dp0++                ; 14F4: C1521200
    r4 = madd r0, r2 r0 = *dp4++               ; 14F5: 82510010
    clip r4 <- r4                              ; 14F6: 67900000
    r1l = dp0                                  ; 14F7: 3C810000
    dp1 = r1l                                  ; 14F8: 3C820000
    clr r7 <- r0 r1 = *dp0++ *dp4-- = r4h      ; 14F9: 711E111C
    r1l = *dp0##-5                             ; 14FA: 4491FFFB
    r7 = suma r5, r1                           ; 14FB: D43C0000
    r7 = suma r1, r5                           ; 14FC: 94BC0000
    r7 = mas16 r1, r5 r1 = *dp0++              ; 14FD: 97BE1100
    r4 = *dp0--                                ; 14FE: 4F821C00
    r7 = mul r7, r4                            ; 14FF: F19C0000
    r7 = add r7, r0                            ; 1500: F81C0000
    clip r7 <- r7                              ; 1501: 67FC0000
    r0eh = *dp3 r0l = *dp7                     ; 1502: 4F13C8C8
    r0 = mul r0, r4                            ; 1503: 81800000
    r0 = mul r0, r4                            ; 1504: 81800000
    *dp3++ = r7h *dp7++ = r7l                  ; 1505: 4D10D7D7
    r1 = suma r3, r7                           ; 1506: B4E40000
    r1 = mas16 r7, r3                          ; 1507: F7640000
    r0 = sub r0, r1 r2 = *dp0                  ; 1508: 89220A00
    r1eh = *dp3 r1l = *dp7                     ; 1509: 4F13C9C9
    r1 = mul r1, r4                            ; 150A: 91840000
    r1 = mul r1, r4                            ; 150B: 91840000
    r2 = mul r1, r3                            ; 150C: 91680000
    r0 = add r0, r2                            ; 150D: 88400000
    clip r0 <- r0 r2 = *dp0                    ; 150E: 77020A00
    *dp3++ = r0h *dp7++ = r0l                  ; 150F: 4D10D0D0
    r2 = suma r3, r0                           ; 1510: B4080000
    r2 = mas16 r0, r3                          ; 1511: 87680000
    r1 = sub r1, r2 r2 = *dp0                  ; 1512: 99460A00
    r0eh = *dp3 r0l = *dp7                     ; 1513: 4F13C8C8
    r0 = mul r0, r4                            ; 1514: 81800000
    r0 = mul r0, r4                            ; 1515: 81800000
    r2 = mul r0, r3                            ; 1516: 81680000
    r1 = add r1, r2                            ; 1517: 98440000
    clip r1 <- r1 r2 = *dp0                    ; 1518: 77260A00
    r1 = mul r1, r4                            ; 1519: 91840000
    r1 = mul r1, r4                            ; 151A: 91840000
    r1 = mul r1, r4                            ; 151B: 91840000
    r1 = mul r1, r4                            ; 151C: 91840000
    *dp3++ = r1h *dp7++ = r1l                  ; 151D: 4D10D1D1
    r2 = suma r3, r1 *dp1++ = r1h              ; 151E: B4285100
    *dp1 = r1l                                 ; 151F: 4C804900
    r2 = mas16 r1, r3                          ; 1520: 97680000
    r0 = sub r0, r2 r2 = *dp0                  ; 1521: 89420A00
    r1eh = *dp3 r1l = *dp7                     ; 1522: 4F13C9C9
    r1 = mul r1, r4                            ; 1523: 91840000
    r1 = mul r1, r4                            ; 1524: 91840000
    r2 = mul r1, r3                            ; 1525: 91680000
    r0 = add r0, r2                            ; 1526: 88400000
    clip r0 <- r0 r2 = *dp0                    ; 1527: 77020A00
    *dp3++ = r0h *dp7++ = r0l                  ; 1528: 4D10D0D0
    r2 = suma r3, r0                           ; 1529: B4080000
    r2 = mas16 r0, r3                          ; 152A: 87680000
    r1 = sub r1, r2 r2 = *dp0++                ; 152B: 99461200
    r0eh = *dp3 r0l = *dp7                     ; 152C: 4F13C8C8
    r0 = mul r0, r4                            ; 152D: 81800000
    r0 = mul r0, r4                            ; 152E: 81800000
    r2 = mul r0, r3 r4 = *dp4++                ; 152F: 81690014
    r1 = add r1, r2 r2 = *dp0++                ; 1530: 98461200
    clip r1 <- r1 r2 = *dp0++                  ; 1531: 77261200
    *dp3++ = r1h *dp7++ = r1l                  ; 1532: 4D10D1D1
    r4 = mul r4, r2 r2 = *dp0++                ; 1533: C1521200
    r4 = madd r0, r2 r2 = *dp4++               ; 1534: 82510012
    clip r4 <- r4                              ; 1535: 67900000
    *dp4 = r4h                                 ; 1536: 4C20000C
    ret                                        ; 1537: 24000000
