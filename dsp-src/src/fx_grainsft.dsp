; Grain Shifter (FX 4, extRAM)
; IRAM 0x165D..0x16EB (143 words)

.org 0x165D
fx_grainsft:
    r7l = *dp0++                               ; 165D: 4C821700
    r6l = *dp0++                               ; 165E: 4C821600
    dp1 = r7l                                  ; 165F: 3F820000
    *x:0x386c = r7l                            ; 1660: 4B90386C
    dp2 = r6l                                  ; 1661: 3F040000
    r1 = *dp0++                                ; 1662: 4F821100
    r1l = *dp0++                               ; 1663: 4C821100
    r0eh = *dp3 r0l = *dp7                     ; 1664: 4F13C8C8
    r7 = r1 sll 0x5                            ; 1665: 5F3C0005
    r0 = add r0, r1 r1 = *dp0++                ; 1666: 88221100
    r1l = *dp0++                               ; 1667: 4C821100
    clip r7 <- r7                              ; 1668: 67FC0000
    r7 = r7 sll 0x5                            ; 1669: 5FFC0005
    clip r7 <- r7 r3 = *dp0                    ; 166A: 77FE0B00
    if (r3 ==0) neg r0 <- r7                   ; 166B: 66E00013
    *dp0++ = r1h                               ; 166C: 4D001100
    clr r7 <- r0 r4 = *dp0++                   ; 166D: 711E1400
    *dp3 = r0h *dp7++ = r0l                    ; 166E: 4D10C8D0
    r0eh = *dp3++                              ; 166F: 4F02D000
    if (r0 <0) acc+ r7 <- r1                   ; 1670: 6C3C0038
    r0eh = *dp3 r0l = *dp7                     ; 1671: 4F13C8C8
    r0 = msub r0, r4 r2 = *dp4++               ; 1672: 83810012
    r0 = madd r7, r4 r3 = *dp4--               ; 1673: F281001B
    *dp3++ = r0h *dp7++ = r0l                  ; 1674: 4D10D0D0
    r2 = add r2, r3 r7 = *dp0++                ; 1675: A86A1700
    r2 = r2 sra 0x1                            ; 1676: 5D480001
    clr r6 <- r0 r5 = *dp0++                   ; 1677: 711A1500
    r5 = mul r7, r5 r4 = *dp0++                ; 1678: F1B61400
    r3eh = *dp3 r3l = *dp7                     ; 1679: 4F13CBCB
    r6 = suma r4, r5                           ; 167A: C4B80000
    r6 = mas16 r5, r4                          ; 167B: D7980000
    r3 = add r3, r6 r6 = *dp2++                ; 167C: B8CE9600
    clr r7 <- r0                               ; 167D: 611C0000
    r7 = suma r4, r3                           ; 167E: C47C0000
    r7 = mas16 r3, r4                          ; 167F: B79C0000
    r3 = sub r3, r7                            ; 1680: B9EC0000
    r7eh = *dp3 r7l = *dp7                     ; 1681: 4F13CFCF
    *dp3++ = r3h *dp7++ = r3l                  ; 1682: 4D10D3D3
    r4 = r7 sll 0xf                            ; 1683: 5FF0000F
    r4 = and r4, r1 r7 = *dp2++                ; 1684: CA329700
    r6 = msub r6, r4                           ; 1685: E3980000
    r6 = madd r7, r4                           ; 1686: F2980000
    clip r6 <- r6 r3 = *dp0                    ; 1687: 77DA0B00
    nop                                        ; 1688: 00000000
    nop                                        ; 1689: 00000000
    r5 = sub r1, r0                            ; 168A: 99140000
    r6 = mul r6, r5                            ; 168B: E1B80000
    r6 = madd r2, r0                           ; 168C: A2180000
    clip r6 <- r6 r3 = *dp2++                  ; 168D: 77DA9300
    r6 = mul r6, r5 *dp1++ = r6h               ; 168E: E1B85600
    r3 = msub r3, r4 r7 = *dp2                 ; 168F: B38E8F00
    r3 = madd r7, r4                           ; 1690: F28C0000
    clip r3 <- r3 r7 = *dp0++                  ; 1691: 776E1700
    nop                                        ; 1692: 00000000
    nop                                        ; 1693: 00000000
    r3 = mul r3, r0                            ; 1694: B10C0000
    r3 = madd r2, r5                           ; 1695: A2AC0000
    clip r3 <- r3                              ; 1696: 676C0000
    r6 = madd r3, r0 *dp1++ = r3h              ; 1697: B2185300
    clip r6 <- r6 r2 = *dp0++                  ; 1698: 77DA1200
    r0eh = *dp3 r0l = *dp7                     ; 1699: 4F13C8C8
    r0 = msub r0, r2 r3 = *dp0++               ; 169A: 83421300
    r0 = madd r3, r2                           ; 169B: B2400000
    *dp3-- = r0h *dp7-- = r0l                  ; 169C: 4D10D8D8
    r1 = sub r1, r0 r2 = *dp4++                ; 169D: 99050012
    r2 = mul r2, r1                            ; 169E: A1280000
    r2 = madd r6, r0                           ; 169F: E2080000
    clip r2 <- r2 r3 = *dp4++                  ; 16A0: 77490013
    r3 = mul r3, r1 *dp4++ = r2h               ; 16A1: B12C0012
    r3 = madd r6, r0 r5 = *dp0                 ; 16A2: E20E0D00
    clip r1 <- r3 r3 = *dp0++                  ; 16A3: 77661300
    r5l = *dp0++                               ; 16A4: 4C821500
    inc r5 <- r5 r0 = *dp0--                   ; 16A5: 72B61800
    r5 = r5 and 0xfff                          ; 16A6: 5AB40FFF
    *dp0##2 = r5l                              ; 16A7: 46900002
    r0l = *dp0++                               ; 16A8: 4C821000
    r7 = add r5, r0 *dp4++ = r1h               ; 16A9: D81C0011
    *x:0x3849 = r7l                            ; 16AA: 4B903849
    *x:0x384a = r7h                            ; 16AB: 4BA0384A
    r7l = 0x1000                               ; 16AC: 3B811000
    *x:0x384b = r7l                            ; 16AD: 4B90384B
    r7l = 0x1                                  ; 16AE: 3B810001
    *x:0x384c = r7l                            ; 16AF: 4B90384C
    r7l = 0x50                                 ; 16B0: 3B810050
    *x:0x3842 = r7l                            ; 16B1: 4B903842
    r3l = *dp3                                 ; 16B2: 4C82CB00
    r1 = sub r5, r3                            ; 16B3: D9640000
    r1 = r1 and 0xfff                          ; 16B4: 5A240FFF
    dec r2 <- r1                               ; 16B5: 63280000
    r2 = r2 and 0xfff                          ; 16B6: 5A480FFF
    r1 = add r1, r0                            ; 16B7: 98040000
    r2 = add r2, r0                            ; 16B8: A8080000
    r0 = r0 add 0x1000                         ; 16B9: 58001000
    r3 = sub r5, r3                            ; 16BA: D96C0000
    r3 = r3 and 0xfff                          ; 16BB: 5A6C0FFF
    dec r4 <- r3                               ; 16BC: 63700000
    r4 = r4 and 0xfff                          ; 16BD: 5A900FFF
    r3 = add r3, r0                            ; 16BE: B80C0000
    r4 = add r4, r0                            ; 16BF: C8100000
    r0l = 0x3f                                 ; 16C0: 3801003F
    *x:0x38c1 = r0l                            ; 16C1: 481038C1
    r0 = r1 srl 0xc                            ; 16C2: 5E20000C
    r0 = r0 add 0x18                           ; 16C3: 58000018
    r0 = r0 and 0x18                           ; 16C4: 5A000018
    *x:0x3844 = r0l                            ; 16C5: 48103844
    r0 = r1 and 0x7fff                         ; 16C6: 5A207FFF
    r0 = r0 add 0x8000                         ; 16C7: 58008000
    dp6 = r0l                                  ; 16C8: 3C0C0000
    r0 = r2 srl 0xc                            ; 16C9: 5E40000C
    r1 = *dp6                                  ; 16CA: 4C710089
    r0 = r0 add 0x18                           ; 16CB: 58000018
    r0 = r0 and 0x18                           ; 16CC: 5A000018
    *x:0x3844 = r0l                            ; 16CD: 48103844
    r0 = r2 and 0x7fff                         ; 16CE: 5A407FFF
    r0 = r0 add 0x8000                         ; 16CF: 58008000
    dp6 = r0l                                  ; 16D0: 3C0C0000
    r0 = r3 srl 0xc                            ; 16D1: 5E60000C
    r2 = *dp6                                  ; 16D2: 4C71008A
    r0 = r0 add 0x18                           ; 16D3: 58000018
    r0 = r0 and 0x18                           ; 16D4: 5A000018
    *x:0x3844 = r0l                            ; 16D5: 48103844
    r0 = r3 and 0x7fff                         ; 16D6: 5A607FFF
    r0 = r0 add 0x8000                         ; 16D7: 58008000
    dp6 = r0l                                  ; 16D8: 3C0C0000
    r0 = r4 srl 0xc                            ; 16D9: 5E80000C
    r3 = *dp6                                  ; 16DA: 4C71008B
    r0 = r0 add 0x18                           ; 16DB: 58000018
    r0 = r0 and 0x18                           ; 16DC: 5A000018
    *x:0x3844 = r0l                            ; 16DD: 48103844
    r0 = r4 and 0x7fff                         ; 16DE: 5A807FFF
    r0 = r0 add 0x8000                         ; 16DF: 58008000
    dp6 = r0l                                  ; 16E0: 3C0C0000
    r7l = 0x2                                  ; 16E1: 3B810002
    clr r0 <- r0 r4 = *dp6                     ; 16E2: 7101008C
    *x:0x38c1 = r0l                            ; 16E3: 481038C1
    *dp2-- = r4h                               ; 16E4: 4D009C00
    *dp2-- = r3h                               ; 16E5: 4D009B00
    *dp2-- = r2h                               ; 16E6: 4D009A00
    *dp2 = r1h                                 ; 16E7: 4D008900
    *x:0x386d = r7l                            ; 16E8: 4B90386D
    r0l = 0x30                                 ; 16E9: 38010030
    *x:0x386e = r0l                            ; 16EA: 4810386E
    ret                                        ; 16EB: 24000000
