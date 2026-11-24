; Chorus / Flanger (FX 5, extRAM)
; IRAM 0x1538..0x15CC (149 words)

.org 0x1538
fx_choflg:
    r7l = *dp0++                               ; 1538: 4C821700
    r6l = *dp0++                               ; 1539: 4C821600
    dp1 = r7l                                  ; 153A: 3F820000
    *x:0x386c = r7l                            ; 153B: 4B90386C
    r0eh = *dp3 r0l = *dp7                     ; 153C: 4F13C8C8
    r1 = *dp0++                                ; 153D: 4F821100
    r1l = *dp0++                               ; 153E: 4C821100
    r0 = add r0, r1                            ; 153F: 88200000
    r0 = r0 or 0x1                             ; 1540: 5B000001
    *dp3 = r0h *dp7++ = r0l                    ; 1541: 4D10C8D0
    r0eh = *dp3++                              ; 1542: 4F02D000
    abs r3 <- r0 r5 = *dp0++                   ; 1543: 740E1500
    r5 = add r0, r5 r1 = *dp0++                ; 1544: 88B61100
    r5 = r5 or 0x1                             ; 1545: 5BB40001
    *dp3 = r5h *dp7++ = r5l                    ; 1546: 4D10CDD5
    r5eh = *dp3++                              ; 1547: 4F02D500
    abs r4 <- r5 r2 = *dp0                     ; 1548: 74B20A00
    r2 = suma r1, r3                           ; 1549: 94680000
    r2 = mas16 r3, r1 r5 = *dp0++              ; 154A: B72A1500
    r5 = suma r1, r4                           ; 154B: 94940000
    r5 = mas16 r4, r1 r7 = *dp0++              ; 154C: C7361700
    r0eh = *dp3 r0l = *dp7                     ; 154D: 4F13C8C8
    r3 = mul r0, r7                            ; 154E: 81EC0000
    r3 = msub r7, r2 r1 = *dp0++               ; 154F: F34E1100
    r3 = madd r1, r2                           ; 1550: 924C0000
    r3 = r3 sll 0x2                            ; 1551: 5F6C0002
    clip r3 <- r3                              ; 1552: 676C0000
    *dp3++ = r3h *dp7++ = r3l                  ; 1553: 4D10D3D3
    r0eh = *dp3 r0l = *dp7                     ; 1554: 4F13C8C8
    r4 = mul r0, r7                            ; 1555: 81F00000
    r4 = msub r7, r5                           ; 1556: F3B00000
    r4 = madd r1, r5                           ; 1557: 92B00000
    r4 = r4 sll 0x2                            ; 1558: 5F900002
    clip r4 <- r4 r5 = *dp0++                  ; 1559: 77921500
    *dp3++ = r4h *dp7++ = r4l                  ; 155A: 4D10D4D4
    r5l = *dp0++                               ; 155B: 4C821500
    inc r5 <- r5 r0 = *dp0--                   ; 155C: 72B61800
    r5 = r5 and 0x3ff                          ; 155D: 5AB403FF
    *dp0##2 = r5l                              ; 155E: 46900002
    r0l = *dp0++                               ; 155F: 4C821000
    r7 = add r5, r0                            ; 1560: D81C0000
    *x:0x3849 = r7l                            ; 1561: 4B903849
    *x:0x384a = r7h                            ; 1562: 4BA0384A
    r7l = 0x400                                ; 1563: 3B810400
    *x:0x384b = r7l                            ; 1564: 4B90384B
    r7l = 0x1                                  ; 1565: 3B810001
    *x:0x384c = r7l                            ; 1566: 4B90384C
    r7l = 0x50                                 ; 1567: 3B810050
    *x:0x3842 = r7l                            ; 1568: 4B903842
    clr r7 <- r0 r1 = *dp0++                   ; 1569: 711E1100
    r7 = suma r1, r3 r6 = *dp0++               ; 156A: 947E1600
    r6 = suma r1, r4                           ; 156B: 94980000
    r6 = mas16 r1, r4                          ; 156C: 97980000
    r7 = mas16 r1, r3 r1 = *dp0++              ; 156D: 977E1100
    r3 = add r6, r1                            ; 156E: E82C0000
    r1 = add r7, r1                            ; 156F: F8240000
    r1 = r1 sra 0x10                           ; 1570: 5D240010
    r1 = sub r5, r1                            ; 1571: D9240000
    r1 = r1 and 0x3ff                          ; 1572: 5A2403FF
    dec r2 <- r1                               ; 1573: 63280000
    r2 = r2 and 0x3ff                          ; 1574: 5A4803FF
    r1 = add r1, r0                            ; 1575: 98040000
    r2 = add r2, r0                            ; 1576: A8080000
    r0 = r0 add 0x400                          ; 1577: 58000400
    r3 = r3 sra 0x10                           ; 1578: 5D6C0010
    r3 = sub r5, r3                            ; 1579: D96C0000
    r3 = r3 and 0x3ff                          ; 157A: 5A6C03FF
    dec r4 <- r3                               ; 157B: 63700000
    r4 = r4 and 0x3ff                          ; 157C: 5A9003FF
    r3 = add r3, r0                            ; 157D: B80C0000
    r4 = add r4, r0                            ; 157E: C8100000
    r0l = 0x3f                                 ; 157F: 3801003F
    *x:0x38c1 = r0l                            ; 1580: 481038C1
    r0 = r1 srl 0xc                            ; 1581: 5E20000C
    r0 = r0 add 0x18                           ; 1582: 58000018
    r0 = r0 and 0x18                           ; 1583: 5A000018
    *x:0x3844 = r0l                            ; 1584: 48103844
    r0 = r1 and 0x7fff                         ; 1585: 5A207FFF
    r0 = r0 add 0x8000                         ; 1586: 58008000
    dp6 = r0l                                  ; 1587: 3C0C0000
    r0 = r2 srl 0xc                            ; 1588: 5E40000C
    r1 = *dp6                                  ; 1589: 4C710089
    r0 = r0 add 0x18                           ; 158A: 58000018
    r0 = r0 and 0x18                           ; 158B: 5A000018
    *x:0x3844 = r0l                            ; 158C: 48103844
    r0 = r2 and 0x7fff                         ; 158D: 5A407FFF
    r0 = r0 add 0x8000                         ; 158E: 58008000
    dp6 = r0l                                  ; 158F: 3C0C0000
    r0 = r3 srl 0xc                            ; 1590: 5E60000C
    r2 = *dp6                                  ; 1591: 4C71008A
    r0 = r0 add 0x18                           ; 1592: 58000018
    r0 = r0 and 0x18                           ; 1593: 5A000018
    *x:0x3844 = r0l                            ; 1594: 48103844
    r0 = r3 and 0x7fff                         ; 1595: 5A607FFF
    r0 = r0 add 0x8000                         ; 1596: 58008000
    dp6 = r0l                                  ; 1597: 3C0C0000
    r0 = r4 srl 0xc                            ; 1598: 5E80000C
    r3 = *dp6                                  ; 1599: 4C71008B
    r0 = r0 add 0x18                           ; 159A: 58000018
    r0 = r0 and 0x18                           ; 159B: 5A000018
    *x:0x3844 = r0l                            ; 159C: 48103844
    r0 = r4 and 0x7fff                         ; 159D: 5A807FFF
    r0 = r0 add 0x8000                         ; 159E: 58008000
    dp6 = r0l                                  ; 159F: 3C0C0000
    r0l = 0x0                                  ; 15A0: 38010000
    r4 = *dp6                                  ; 15A1: 4C71008C
    *x:0x38c1 = r0l                            ; 15A2: 481038C1
    r5 = *dp0++                                ; 15A3: 4F821500
    r5l = *dp0++                               ; 15A4: 4C821500
    r0 = r7 sll 0xf                            ; 15A5: 5FE0000F
    r0 = and r5, r0                            ; 15A6: DA000000
    r1 = msub r1, r0                           ; 15A7: 93040000
    r1 = madd r2, r0 r0 = *dp0++               ; 15A8: A2061000
    clip r1 <- r1 r7 = *dp4++                  ; 15A9: 77250017
    r1 = mul r1, r0 r2 = *dp4++                ; 15AA: 91050012
    r1 = mul r1, r0                            ; 15AB: 91040000
    r1 = mul r1, r0 r0 = *dp3                  ; 15AC: 9106C800
    r0 = mul r1, r0                            ; 15AD: 91000000
    r0 = add r0, r7                            ; 15AE: 88E00000
    clip r0 <- r0 r2 = *dp0++                  ; 15AF: 77021200
    r6 = r6 sll 0xf                            ; 15B0: 5FD8000F
    r0 = and r5, r6 *dp1++ = r0h               ; 15B1: DAC05000
    r6eh = *dp3 r6l = *dp7                     ; 15B2: 4F13CECE
    r6 = msub r6, r2 r5 = *dp0++               ; 15B3: E35A1500
    r6 = madd r5, r2 r2 = *dp0++               ; 15B4: D25A1200
    *dp3++ = r6h *dp7++ = r6l                  ; 15B5: 4D10D6D6
    r6eh = *dp3 r6l = *dp7                     ; 15B6: 4F13CECE
    r6 = msub r6, r2 r5 = *dp0++               ; 15B7: E35A1500
    r6 = madd r5, r2                           ; 15B8: D2580000
    *dp3-- = r6h *dp7-- = r6l                  ; 15B9: 4D10DEDE
    r7 = madd r1, r6                           ; 15BA: 92DC0000
    clip r7 <- r7                              ; 15BB: 67FC0000
    r3 = msub r3, r0 *dp4-- = r7h              ; 15BC: B30C001F
    r3 = madd r4, r0 r0 = *dp0++               ; 15BD: C20E1000
    clip r3 <- r3 r4 = *dp4++                  ; 15BE: 776D0014
    r3 = mul r3, r0 r7 = *dp4++                ; 15BF: B10D0017
    r3 = mul r3, r0                            ; 15C0: B10C0000
    r3 = mul r0, r3 r0 = *dp3++                ; 15C1: 816ED000
    r0 = mul r0, r3                            ; 15C2: 81600000
    r0 = add r0, r4                            ; 15C3: 88800000
    clip r0 <- r0 r2 = *dp3                    ; 15C4: 7702CA00
    r4 = madd r3, r2 *dp1 = r0h                ; 15C5: B2504800
    clip r4 <- r4                              ; 15C6: 67900000
    *dp4 = r4h                                 ; 15C7: 4C20000C
    r0l = 0x2                                  ; 15C8: 38010002
    *x:0x386d = r0l                            ; 15C9: 4810386D
    r0l = 0x30                                 ; 15CA: 38010030
    *x:0x386e = r0l                            ; 15CB: 4810386E
    ret                                        ; 15CC: 24000000
