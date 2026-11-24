; Pitch Shifter (FX 9, extRAM)
; IRAM 0x16EC..0x177C (145 words)

.org 0x16EC
fx_pitchsft:
    r7l = *dp0++                               ; 16EC: 4C821700
    r6l = *dp0++                               ; 16ED: 4C821600
    dp1 = r7l                                  ; 16EE: 3F820000
    *x:0x386c = r7l                            ; 16EF: 4B90386C
    dp2 = r6l                                  ; 16F0: 3F040000
    r7 = *dp0++                                ; 16F1: 4F821700
    r1 = *dp0++                                ; 16F2: 4F821100
    r7 = sub r7, r1 r0 = *dp0++                ; 16F3: F93E1000
    r7 = mul r7, r0 r0 = *dp0++                ; 16F4: F11E1000
    r0eh = *dp3 r0l = *dp7                     ; 16F5: 4F13C8C8
    r0 = add r7, r0 r1 = *dp0++                ; 16F6: F8021100
    r0 = r0 or 0x1                             ; 16F7: 5B000001
    r1l = *dp0++                               ; 16F8: 4C821100
    *dp3 = r0h *dp7++ = r0l                    ; 16F9: 4D10C8D0
    r0eh = *dp3++                              ; 16FA: 4F02D000
    r2 = add r0, r1 r4 = *dp0++                ; 16FB: 882A1400
    r2 = r2 or 0x1                             ; 16FC: 5B480001
    *dp3 = r2h *dp7++ = r2l                    ; 16FD: 4D10CAD2
    r2eh = *dp3++                              ; 16FE: 4F02D200
    clr r6 <- r0                               ; 16FF: 61180000
    r6 = suma r4, r0                           ; 1700: C4180000
    r6 = mas16 r0, r4                          ; 1701: 87980000
    r3 = sub r4, r6 r5 = *dp0++                ; 1702: C9CE1500
    r3 = add r3, r5                            ; 1703: B8AC0000
    clip r3 <- r3                              ; 1704: 676C0000
    r6eh = *dp3 r6l = *dp7                     ; 1705: 4F13CECE
    *dp3++ = r3h *dp7++ = r3l                  ; 1706: 4D10D3D3
    clr r7 <- r0                               ; 1707: 611C0000
    r7 = suma r4, r2                           ; 1708: C45C0000
    r7 = mas16 r2, r4                          ; 1709: A79C0000
    r3 = sub r4, r7                            ; 170A: C9EC0000
    r3 = add r3, r5                            ; 170B: B8AC0000
    clip r3 <- r3                              ; 170C: 676C0000
    r7eh = *dp3 r7l = *dp7                     ; 170D: 4F13CFCF
    *dp3++ = r3h *dp7++ = r3l                  ; 170E: 4D10D3D3
    abs r0 <- r0 r4 = *dp0++                   ; 170F: 74021400
    r3 = mul r0, r4                            ; 1710: 818C0000
    abs r2 <- r2                               ; 1711: 64480000
    r4 = mul r2, r4                            ; 1712: A1900000
    r2 = r6 sll 0xf                            ; 1713: 5FC8000F
    r0 = and r2, r1 r6 = *dp2++                ; 1714: AA229600
    r2 = *dp2++                                ; 1715: 4F829200
    r6 = msub r6, r0                           ; 1716: E3180000
    r6 = madd r2, r0                           ; 1717: A2180000
    clip r6 <- r6                              ; 1718: 67D80000
    r0 = mul r6, r4                            ; 1719: E1800000
    r2 = r7 sll 0xf                            ; 171A: 5FE8000F
    r4 = and r2, r1                            ; 171B: AA300000
    r6 = *dp2++                                ; 171C: 4F829600
    r2 = *dp2                                  ; 171D: 4F828A00
    r6 = msub r6, r4                           ; 171E: E3980000
    r6 = madd r2, r4                           ; 171F: A2980000
    clip r6 <- r6                              ; 1720: 67D80000
    r4 = mul r6, r3                            ; 1721: E1700000
    r0 = add r0, r4                            ; 1722: 88800000
    clip r6 <- r0 r2 = *dp0++                  ; 1723: 771A1200
    r0eh = *dp3 r0l = *dp7                     ; 1724: 4F13C8C8
    r0 = msub r0, r2 r3 = *dp0++               ; 1725: 83421300
    r0 = madd r3, r2 r2 = *dp4++               ; 1726: B2410012
    *dp3-- = r0h *dp7-- = r0l                  ; 1727: 4D10D8D8
    r1 = sub r1, r0 r3 = *dp4++                ; 1728: 99050013
    r5 = add r2, r3                            ; 1729: A8740000
    r5 = r5 sra 0x1                            ; 172A: 5DB40001
    r2 = mul r2, r0                            ; 172B: A1080000
    r2 = madd r6, r1 *dp1++ = r5h              ; 172C: E2285500
    clip r2 <- r2                              ; 172D: 67480000
    r3 = mul r3, r0 *dp4++ = r2h               ; 172E: B10C0012
    r3 = madd r6, r1                           ; 172F: E22C0000
    clip r3 <- r3 r5 = *dp0++                  ; 1730: 776E1500
    *dp4++ = r3h                               ; 1731: 4C200013
    r5l = *dp0++                               ; 1732: 4C821500
    inc r5 <- r5 r0 = *dp0--                   ; 1733: 72B61800
    r5 = r5 and 0xfff                          ; 1734: 5AB40FFF
    *dp0##2 = r5l                              ; 1735: 46900002
    r0l = *dp0++                               ; 1736: 4C821000
    r7 = add r5, r0                            ; 1737: D81C0000
    *x:0x3849 = r7l                            ; 1738: 4B903849
    *x:0x384a = r7h                            ; 1739: 4BA0384A
    r7l = 0x1000                               ; 173A: 3B811000
    *x:0x384b = r7l                            ; 173B: 4B90384B
    r7l = 0x1                                  ; 173C: 3B810001
    *x:0x384c = r7l                            ; 173D: 4B90384C
    r7l = 0x50                                 ; 173E: 3B810050
    *x:0x3842 = r7l                            ; 173F: 4B903842
    r4eh = *dp3-- r4l = *dp7--                 ; 1740: 4F13DCDC
    r3eh = *dp3-- r3l = *dp7--                 ; 1741: 4F13DBDB
    r3 = r3 sra 0x10                           ; 1742: 5D6C0010
    r1 = sub r5, r3                            ; 1743: D9640000
    r1 = r1 and 0xfff                          ; 1744: 5A240FFF
    dec r2 <- r1                               ; 1745: 63280000
    r2 = r2 and 0xfff                          ; 1746: 5A480FFF
    r1 = add r1, r0                            ; 1747: 98040000
    r2 = add r2, r0                            ; 1748: A8080000
    r4 = r4 sra 0x10                           ; 1749: 5D900010
    r3 = sub r5, r4                            ; 174A: D98C0000
    r3 = r3 and 0xfff                          ; 174B: 5A6C0FFF
    dec r4 <- r3                               ; 174C: 63700000
    r4 = r4 and 0xfff                          ; 174D: 5A900FFF
    r3 = add r3, r0                            ; 174E: B80C0000
    r4 = add r4, r0                            ; 174F: C8100000
    r0l = 0x3f                                 ; 1750: 3801003F
    *x:0x38c1 = r0l                            ; 1751: 481038C1
    r0 = r1 srl 0xc                            ; 1752: 5E20000C
    r0 = r0 add 0x18                           ; 1753: 58000018
    r0 = r0 and 0x18                           ; 1754: 5A000018
    *x:0x3844 = r0l                            ; 1755: 48103844
    r0 = r1 and 0x7fff                         ; 1756: 5A207FFF
    r0 = r0 add 0x8000                         ; 1757: 58008000
    dp6 = r0l                                  ; 1758: 3C0C0000
    r0 = r2 srl 0xc                            ; 1759: 5E40000C
    r1l = *dp6                                 ; 175A: 4C110089
    r0 = r0 add 0x18                           ; 175B: 58000018
    r0 = r0 and 0x18                           ; 175C: 5A000018
    *x:0x3844 = r0l                            ; 175D: 48103844
    r0 = r2 and 0x7fff                         ; 175E: 5A407FFF
    r0 = r0 add 0x8000                         ; 175F: 58008000
    dp6 = r0l                                  ; 1760: 3C0C0000
    r0 = r3 srl 0xc                            ; 1761: 5E60000C
    r2l = *dp6                                 ; 1762: 4C11008A
    r0 = r0 add 0x18                           ; 1763: 58000018
    r0 = r0 and 0x18                           ; 1764: 5A000018
    *x:0x3844 = r0l                            ; 1765: 48103844
    r0 = r3 and 0x7fff                         ; 1766: 5A607FFF
    r0 = r0 add 0x8000                         ; 1767: 58008000
    dp6 = r0l                                  ; 1768: 3C0C0000
    r0 = r4 srl 0xc                            ; 1769: 5E80000C
    r3l = *dp6                                 ; 176A: 4C11008B
    r0 = r0 add 0x18                           ; 176B: 58000018
    r0 = r0 and 0x18                           ; 176C: 5A000018
    *x:0x3844 = r0l                            ; 176D: 48103844
    r0 = r4 and 0x7fff                         ; 176E: 5A807FFF
    r0 = r0 add 0x8000                         ; 176F: 58008000
    dp6 = r0l                                  ; 1770: 3C0C0000
    r0l = 0x0                                  ; 1771: 38010000
    r4l = *dp6                                 ; 1772: 4C11008C
    *x:0x38c1 = r0l                            ; 1773: 481038C1
    *dp2-- = r4l                               ; 1774: 4C809C00
    *dp2-- = r3l                               ; 1775: 4C809B00
    *dp2-- = r2l                               ; 1776: 4C809A00
    *dp2 = r1l                                 ; 1777: 4C808900
    r0l = 0x1                                  ; 1778: 38010001
    *x:0x386d = r0l                            ; 1779: 4810386D
    r0l = 0x30                                 ; 177A: 38010030
    *x:0x386e = r0l                            ; 177B: 4810386E
    ret                                        ; 177C: 24000000
