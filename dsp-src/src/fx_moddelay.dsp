; Modulation Delay (FX 3, extRAM)
; IRAM 0x15CD..0x165C (144 words)

.org 0x15CD
fx_moddelay:
    clr r7 <- r0 r2 = *dp0++                   ; 15CD: 711E1200
    r7l = *dp0++                               ; 15CE: 4C821700
    r4 = r7 add 0x2400                         ; 15CF: 58F02400
    dp1 = r4l                                  ; 15D0: 3E020000
    r3 = r7 add 0x2410                         ; 15D1: 58EC2410
    dp2 = r3l                                  ; 15D2: 3D840000
    r1eh = *dp3 r1l = *dp7                     ; 15D3: 4F13C9C9
    r1 = msub r1, r2 r0 = *dp0                 ; 15D4: 93460800
    r1 = madd r0, r2 r0 = *dp1++               ; 15D5: 82465000
    *dp3++ = r1h *dp7++ = r1l                  ; 15D6: 4D10D1D1
    r3 = mul r1, r0                            ; 15D7: 910C0000
    r1eh = *dp3 r1l = *dp7                     ; 15D8: 4F13C9C9
    r1 = msub r1, r2 r0 = *dp0++               ; 15D9: 93461000
    r1 = madd r0, r2 r0 = *dp1                 ; 15DA: 82464800
    *dp3++ = r1h *dp7++ = r1l                  ; 15DB: 4D10D1D1
    r1 = mul r1, r0                            ; 15DC: 91040000
    *dp2++ = r1h                               ; 15DD: 4D009100
    r7l = *dp0++                               ; 15DE: 4C821700
    r6l = *dp0++                               ; 15DF: 4C821600
    dp1 = r7l                                  ; 15E0: 3F820000
    *x:0x386c = r7l                            ; 15E1: 4B90386C
    *dp1++ = r3h                               ; 15E2: 4D005300
    *dp1++ = r1h                               ; 15E3: 4D005100
    r0eh = *dp3 r0l = *dp7                     ; 15E4: 4F13C8C8
    clr r2 <- r0 r1 = *dp0++                   ; 15E5: 710A1100
    r1l = *dp0##4                              ; 15E6: 44910004
    r0 = add r0, r1                            ; 15E7: 88200000
    *dp3 = r0h *dp7++ = r0l                    ; 15E8: 4D10C8D0
    r0eh = *dp3++                              ; 15E9: 4F02D000
    r0 = r0 or 0x1                             ; 15EA: 5B000001
    abs r3 <- r0                               ; 15EB: 640C0000
    r5l = *dp0                                 ; 15EC: 4C820D00
    inc r5 <- r5                               ; 15ED: 62B40000
    r5 = r5 and 0x3ff                          ; 15EE: 5AB403FF
    *dp0++ = r5l                               ; 15EF: 4C801500
    acc+ r4 <- r3 r0 = *dp0++                  ; 15F0: 7C721000
    r4 = r4 sra 0x1                            ; 15F1: 5D900001
    r0l = *dp0++                               ; 15F2: 4C821000
    r7 = add r5, r0                            ; 15F3: D81C0000
    *x:0x3849 = r7l                            ; 15F4: 4B903849
    *x:0x384a = r7h                            ; 15F5: 4BA0384A
    r7l = 0x400                                ; 15F6: 3B810400
    *x:0x384b = r7l                            ; 15F7: 4B90384B
    r7l = 0x1                                  ; 15F8: 3B810001
    *x:0x384c = r7l                            ; 15F9: 4B90384C
    r7l = 0x50                                 ; 15FA: 3B810050
    *x:0x3842 = r7l                            ; 15FB: 4B903842
    clr r7 <- r0 r1 = *dp0++                   ; 15FC: 711E1100
    clr r6 <- r0                               ; 15FD: 61180000
    r6 = suma r1, r3                           ; 15FE: 94780000
    r6 = mas16 r1, r3                          ; 15FF: 97780000
    r7 = suma r1, r4                           ; 1600: 949C0000
    r7 = mas16 r1, r4 r1 = *dp0++              ; 1601: 979E1100
    r3 = add r1, r7 r1 = *dp0++                ; 1602: 98EE1100
    r1 = add r6, r1                            ; 1603: E8240000
    r1 = r1 sra 0x10                           ; 1604: 5D240010
    r1 = sub r5, r1                            ; 1605: D9240000
    r1 = r1 and 0x3ff                          ; 1606: 5A2403FF
    dec r2 <- r1                               ; 1607: 63280000
    r2 = r2 and 0x3ff                          ; 1608: 5A4803FF
    r1 = add r1, r0                            ; 1609: 98040000
    r2 = add r2, r0                            ; 160A: A8080000
    r0 = r0 add 0x400                          ; 160B: 58000400
    r3 = r3 sra 0x10                           ; 160C: 5D6C0010
    r3 = sub r5, r3                            ; 160D: D96C0000
    r3 = r3 and 0x3ff                          ; 160E: 5A6C03FF
    dec r4 <- r3                               ; 160F: 63700000
    r4 = r4 and 0x3ff                          ; 1610: 5A9003FF
    r3 = add r3, r0                            ; 1611: B80C0000
    r4 = add r4, r0                            ; 1612: C8100000
    r0l = 0x3f                                 ; 1613: 3801003F
    *x:0x38c1 = r0l                            ; 1614: 481038C1
    r0 = r1 srl 0xc                            ; 1615: 5E20000C
    r0 = r0 add 0x18                           ; 1616: 58000018
    r0 = r0 and 0x18                           ; 1617: 5A000018
    *x:0x3844 = r0l                            ; 1618: 48103844
    r0 = r1 and 0x7fff                         ; 1619: 5A207FFF
    r0 = r0 add 0x8000                         ; 161A: 58008000
    dp6 = r0l                                  ; 161B: 3C0C0000
    r0 = r2 srl 0xc                            ; 161C: 5E40000C
    r1 = *dp6                                  ; 161D: 4C710089
    r0 = r0 add 0x18                           ; 161E: 58000018
    r0 = r0 and 0x18                           ; 161F: 5A000018
    *x:0x3844 = r0l                            ; 1620: 48103844
    r0 = r2 and 0x7fff                         ; 1621: 5A407FFF
    r0 = r0 add 0x8000                         ; 1622: 58008000
    dp6 = r0l                                  ; 1623: 3C0C0000
    r0 = r3 srl 0xc                            ; 1624: 5E60000C
    r2 = *dp6                                  ; 1625: 4C71008A
    r0 = r0 add 0x18                           ; 1626: 58000018
    r0 = r0 and 0x18                           ; 1627: 5A000018
    *x:0x3844 = r0l                            ; 1628: 48103844
    r0 = r3 and 0x7fff                         ; 1629: 5A607FFF
    r0 = r0 add 0x8000                         ; 162A: 58008000
    dp6 = r0l                                  ; 162B: 3C0C0000
    r0 = r4 srl 0xc                            ; 162C: 5E80000C
    r3 = *dp6                                  ; 162D: 4C71008B
    r0 = r0 add 0x18                           ; 162E: 58000018
    r0 = r0 and 0x18                           ; 162F: 5A000018
    *x:0x3844 = r0l                            ; 1630: 48103844
    r0 = r4 and 0x7fff                         ; 1631: 5A807FFF
    r0 = r0 add 0x8000                         ; 1632: 58008000
    dp6 = r0l                                  ; 1633: 3C0C0000
    r0l = 0x0                                  ; 1634: 38010000
    r5 = *dp0++ r4 = *dp6                      ; 1635: 4FF3158C
    *x:0x38c1 = r0l                            ; 1636: 481038C1
    r5l = *dp0++                               ; 1637: 4C821500
    r0 = r6 sll 0xf                            ; 1638: 5FC0000F
    r0 = and r5, r0                            ; 1639: DA000000
    r1 = msub r1, r0                           ; 163A: 93040000
    r1 = madd r2, r0 r0 = *dp3                 ; 163B: A206C800
    clip r1 <- r1 r2 = *dp4++                  ; 163C: 77250012
    r2 = madd r1, r0                           ; 163D: 92080000
    clip r2 <- r2                              ; 163E: 67480000
    r0 = r7 sll 0xf                            ; 163F: 5FE0000F
    r0 = and r5, r0                            ; 1640: DA000000
    r3 = msub r3, r0                           ; 1641: B30C0000
    r3 = madd r4, r0 r5 = *dp3                 ; 1642: C20ECD00
    clip r0 <- r3 r4 = *dp4++                  ; 1643: 77610014
    r4 = madd r5, r0                           ; 1644: D2100000
    clip r4 <- r4 r2 = *dp0++ *dp4++ = r2h     ; 1645: 77921212
    *dp4##-3 = r4h                             ; 1646: 4628FFFD
    r3eh = *dp3 r3l = *dp7                     ; 1647: 4F13CBCB
    r3 = msub r3, r2 r4 = *dp0++               ; 1648: B34E1400
    r3 = madd r4, r2 r2 = *dp0++               ; 1649: C24E1200
    *dp3++ = r3h *dp7++ = r3l                  ; 164A: 4D10D3D3
    r3eh = *dp3 r3l = *dp7                     ; 164B: 4F13CBCB
    r3 = msub r3, r2 r4 = *dp0++               ; 164C: B34E1400
    r3 = madd r4, r2 r2 = *dp0++               ; 164D: C24E1200
    *dp3++ = r3h *dp7++ = r3l                  ; 164E: 4D10D3D3
    r5 = mul r0, r2 r4 = *dp4++                ; 164F: 81550014
    r5 = mul r5, r2                            ; 1650: D1540000
    r6 = mul r1, r2 r7 = *dp4++                ; 1651: 91590017
    r6 = mul r6, r2                            ; 1652: E1580000
    r4 = add r4, r7                            ; 1653: C8F00000
    r4 = madd r6, r3                           ; 1654: E2700000
    r4 = r4 sra 0x1                            ; 1655: 5D900001
    clip r7 <- r4                              ; 1656: 679C0000
    *dp2++ = r7h                               ; 1657: 4D009700
    r0l = 0x2                                  ; 1658: 38010002
    *x:0x386d = r0l                            ; 1659: 4810386D
    r0l = 0x30                                 ; 165A: 38010030
    *x:0x386e = r0l                            ; 165B: 4810386E
    ret                                        ; 165C: 24000000
