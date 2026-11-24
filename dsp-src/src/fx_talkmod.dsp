; Talking Modulator (FX 8)
; IRAM 0x1296..0x1343 (174 words)

.org 0x1296
fx_talkmod:
    clr r0 <- r0                               ; 1296: 61000000
    r0l = dp0                                  ; 1297: 3C010000
    r0 = r0 add 0xd                            ; 1298: 5800000D
    dn1 = 0x4                                  ; 1299: 38120004
    dp1 = r0l                                  ; 129A: 3C020000
    r1 = *dp4++                                ; 129B: 4C710011
    clr r3 <- r0 r2 = *dp4++                   ; 129C: 710D0012
    r1 = add r1, r2                            ; 129D: 98440000
    r1 = r1 sra 0x1                            ; 129E: 5D240001
    clip r1 <- r1 r2 = *dp3                    ; 129F: 7726CA00
    acc+ r7 <- r1 r4 = *dp0++                  ; 12A0: 7C3E1400
    *dp3++ = r1h *dp7++ = r1l                  ; 12A1: 4D10D1D1
    r6 = mul r1, r4 r5 = *dp0++                ; 12A2: 919A1500
    r6 = msub r2, r4 r4 = *dp0++               ; 12A3: A39A1400
    r2eh = *dp3 r2l = *dp7                     ; 12A4: 4F13CACA
    r3 = suma r4, r2                           ; 12A5: C44C0000
    r3 = mas16 r2, r4 r2 = *dp0++              ; 12A6: A78E1200
    r2 = suma r4, r3                           ; 12A7: C4680000
    r2 = mas16 r3, r4                          ; 12A8: B7880000
    r3 = suma r5, r2                           ; 12A9: D44C0000
    r3 = mas16 r2, r5 r1 = *dp0++              ; 12AA: A7AE1100
    r3 = add r3, r6 r6 = *dp0++                ; 12AB: B8CE1600
    clip r4 <- r3 r3 = *dp0++                  ; 12AC: 77721300
    *dp3++ = r4h *dp7++ = r4l                  ; 12AD: 4D10D4D4
    r3 = mul r3, r6                            ; 12AE: B1CC0000
    r3 = r3 sll 0x1                            ; 12AF: 5F6C0001
    r0eh = *dp3 r0l = *dp7                     ; 12B0: 4F13C8C8
    r0 = msub r0, r1                           ; 12B1: 83200000
    r0 = madd r3, r1 r3 = *dp0++               ; 12B2: B2221300
    *dp3++ = r0h *dp7++ = r0l                  ; 12B3: 4D10D0D0
    *dp1## = r0h                               ; 12B4: 4D006000
    r3 = mul r3, r6                            ; 12B5: B1CC0000
    r3 = r3 sll 0x1                            ; 12B6: 5F6C0001
    r0eh = *dp3 r0l = *dp7                     ; 12B7: 4F13C8C8
    r0 = msub r0, r1                           ; 12B8: 83200000
    r0 = madd r3, r1 r3 = *dp0++               ; 12B9: B2221300
    *dp3++ = r0h *dp7++ = r0l                  ; 12BA: 4D10D0D0
    *dp1## = r0h                               ; 12BB: 4D006000
    r3 = mul r3, r6                            ; 12BC: B1CC0000
    r3 = r3 sll 0x1                            ; 12BD: 5F6C0001
    r0eh = *dp3 r0l = *dp7                     ; 12BE: 4F13C8C8
    r0 = msub r0, r1                           ; 12BF: 83200000
    r0 = madd r3, r1 r3 = *dp0++               ; 12C0: B2221300
    *dp3++ = r0h *dp7++ = r0l                  ; 12C1: 4D10D0D0
    *dp1## = r0h                               ; 12C2: 4D006000
    r3 = mul r3, r6                            ; 12C3: B1CC0000
    r3 = r3 sll 0x1                            ; 12C4: 5F6C0001
    r0eh = *dp3 r0l = *dp7                     ; 12C5: 4F13C8C8
    r0 = msub r0, r1                           ; 12C6: 83200000
    r0 = madd r3, r1                           ; 12C7: B2200000
    *dp3++ = r0h *dp7++ = r0l                  ; 12C8: 4D10D0D0
    *dp1## = r0h                               ; 12C9: 4D006000
    clr r3 <- r0 r0 = *dp0++                   ; 12CA: 710E1000
    r7 = r7 sra 0x1                            ; 12CB: 5DFC0001
    r1eh = *dp3++ r1l = *dp7++                 ; 12CC: 4F13D1D1
    r2eh = *dp3-- r2l = *dp7--                 ; 12CD: 4F13DADA
    r3 = suma r0, r1                           ; 12CE: 842C0000
    r3 = mas16 r1, r0 r1 = *dp0                ; 12CF: 970E0900
    r1 = suma r0, r3                           ; 12D0: 84640000
    r1 = mas16 r3, r0 r3 = *dp0                ; 12D1: B7060B00
    r3 = suma r0, r2                           ; 12D2: 844C0000
    r3 = mas16 r2, r0 r2 = *dp0++              ; 12D3: A70E1200
    r2 = suma r0, r3                           ; 12D4: 84680000
    r2 = mas16 r3, r0                          ; 12D5: B7080000
    clr r3 <- r0 r4 = *dp0++                   ; 12D6: 710E1400
    r3 = suma r4, r1                           ; 12D7: C42C0000
    r3 = mas16 r1, r4                          ; 12D8: 978C0000
    r3 = sub r7, r3                            ; 12D9: F96C0000
    r3 = sub r3, r2                            ; 12DA: B94C0000
    clip r5 <- r3                              ; 12DB: 67740000
    clr r3 <- r0 r4 = *dp0++                   ; 12DC: 710E1400
    r3 = suma r4, r5                           ; 12DD: C4AC0000
    r3 = mas16 r5, r4                          ; 12DE: D78C0000
    r3 = add r3, r1                            ; 12DF: B82C0000
    clip r5 <- r3 r1 = *dp0++                  ; 12E0: 77761100
    *dp3++ = r5h *dp7++ = r5l                  ; 12E1: 4D10D5D5
    r6 = mul r1, r5                            ; 12E2: 91B80000
    clr r3 <- r0                               ; 12E3: 610C0000
    r3 = suma r4, r5                           ; 12E4: C4AC0000
    r3 = mas16 r5, r4                          ; 12E5: D78C0000
    r3 = add r3, r2                            ; 12E6: B84C0000
    clip r2 <- r3 r3 = *dp0                    ; 12E7: 776A0B00
    *dp3++ = r2h *dp7++ = r2l                  ; 12E8: 4D10D2D2
    r1eh = *dp3++ r1l = *dp7++                 ; 12E9: 4F13D1D1
    r2eh = *dp3-- r2l = *dp7--                 ; 12EA: 4F13DADA
    r3 = suma r0, r1                           ; 12EB: 842C0000
    r3 = mas16 r1, r0 r1 = *dp0                ; 12EC: 970E0900
    r1 = suma r0, r3                           ; 12ED: 84640000
    r1 = mas16 r3, r0 r3 = *dp0                ; 12EE: B7060B00
    r3 = suma r0, r2                           ; 12EF: 844C0000
    r3 = mas16 r2, r0 r2 = *dp0++              ; 12F0: A70E1200
    r2 = suma r0, r3                           ; 12F1: 84680000
    r2 = mas16 r3, r0                          ; 12F2: B7080000
    clr r3 <- r0 r4 = *dp0++                   ; 12F3: 710E1400
    r3 = suma r4, r1                           ; 12F4: C42C0000
    r3 = mas16 r1, r4                          ; 12F5: 978C0000
    r3 = sub r7, r3                            ; 12F6: F96C0000
    r3 = sub r3, r2                            ; 12F7: B94C0000
    clip r5 <- r3                              ; 12F8: 67740000
    clr r3 <- r0 r4 = *dp0++                   ; 12F9: 710E1400
    r3 = suma r4, r5                           ; 12FA: C4AC0000
    r3 = mas16 r5, r4                          ; 12FB: D78C0000
    r3 = add r3, r1                            ; 12FC: B82C0000
    clip r5 <- r3 r1 = *dp0++                  ; 12FD: 77761100
    *dp3++ = r5h *dp7++ = r5l                  ; 12FE: 4D10D5D5
    r6 = madd r1, r5                           ; 12FF: 92B80000
    clr r3 <- r0                               ; 1300: 610C0000
    r3 = suma r4, r5                           ; 1301: C4AC0000
    r3 = mas16 r5, r4                          ; 1302: D78C0000
    r3 = add r3, r2                            ; 1303: B84C0000
    clip r2 <- r3 r3 = *dp0                    ; 1304: 776A0B00
    *dp3++ = r2h *dp7++ = r2l                  ; 1305: 4D10D2D2
    r1eh = *dp3++ r1l = *dp7++                 ; 1306: 4F13D1D1
    r2eh = *dp3-- r2l = *dp7--                 ; 1307: 4F13DADA
    r3 = suma r0, r1                           ; 1308: 842C0000
    r3 = mas16 r1, r0 r1 = *dp0                ; 1309: 970E0900
    r1 = suma r0, r3                           ; 130A: 84640000
    r1 = mas16 r3, r0 r3 = *dp0                ; 130B: B7060B00
    r3 = suma r0, r2                           ; 130C: 844C0000
    r3 = mas16 r2, r0 r2 = *dp0++              ; 130D: A70E1200
    r2 = suma r0, r3                           ; 130E: 84680000
    r2 = mas16 r3, r0                          ; 130F: B7080000
    clr r3 <- r0 r4 = *dp0++                   ; 1310: 710E1400
    r3 = suma r4, r1                           ; 1311: C42C0000
    r3 = mas16 r1, r4                          ; 1312: 978C0000
    r3 = sub r7, r3                            ; 1313: F96C0000
    r3 = sub r3, r2                            ; 1314: B94C0000
    clip r5 <- r3                              ; 1315: 67740000
    clr r3 <- r0 r4 = *dp0++                   ; 1316: 710E1400
    r3 = suma r4, r5                           ; 1317: C4AC0000
    r3 = mas16 r5, r4                          ; 1318: D78C0000
    r3 = add r3, r1                            ; 1319: B82C0000
    clip r5 <- r3 r1 = *dp0++                  ; 131A: 77761100
    *dp3++ = r5h *dp7++ = r5l                  ; 131B: 4D10D5D5
    r6 = madd r1, r5                           ; 131C: 92B80000
    clr r3 <- r0                               ; 131D: 610C0000
    r3 = suma r4, r5                           ; 131E: C4AC0000
    r3 = mas16 r5, r4                          ; 131F: D78C0000
    r3 = add r3, r2                            ; 1320: B84C0000
    clip r2 <- r3 r3 = *dp0                    ; 1321: 776A0B00
    *dp3++ = r2h *dp7++ = r2l                  ; 1322: 4D10D2D2
    r1eh = *dp3++ r1l = *dp7++                 ; 1323: 4F13D1D1
    r2eh = *dp3-- r2l = *dp7--                 ; 1324: 4F13DADA
    r3 = suma r0, r1                           ; 1325: 842C0000
    r3 = mas16 r1, r0 r1 = *dp0                ; 1326: 970E0900
    r1 = suma r0, r3                           ; 1327: 84640000
    r1 = mas16 r3, r0 r3 = *dp0                ; 1328: B7060B00
    r3 = suma r0, r2                           ; 1329: 844C0000
    r3 = mas16 r2, r0 r2 = *dp0++              ; 132A: A70E1200
    r2 = suma r0, r3                           ; 132B: 84680000
    r2 = mas16 r3, r0                          ; 132C: B7080000
    clr r3 <- r0 r4 = *dp0++                   ; 132D: 710E1400
    r3 = suma r4, r1                           ; 132E: C42C0000
    r3 = mas16 r1, r4                          ; 132F: 978C0000
    r3 = sub r7, r3                            ; 1330: F96C0000
    r3 = sub r3, r2                            ; 1331: B94C0000
    clip r5 <- r3                              ; 1332: 67740000
    clr r3 <- r0 r4 = *dp0++                   ; 1333: 710E1400
    r3 = suma r4, r5                           ; 1334: C4AC0000
    r3 = mas16 r5, r4                          ; 1335: D78C0000
    r3 = add r3, r1                            ; 1336: B82C0000
    clip r5 <- r3 r1 = *dp0++                  ; 1337: 77761100
    *dp3++ = r5h *dp7++ = r5l                  ; 1338: 4D10D5D5
    r6 = madd r1, r5                           ; 1339: 92B80000
    clr r3 <- r0                               ; 133A: 610C0000
    r3 = suma r4, r5                           ; 133B: C4AC0000
    r3 = mas16 r5, r4                          ; 133C: D78C0000
    r3 = add r3, r2                            ; 133D: B84C0000
    clip r2 <- r3                              ; 133E: 67680000
    *dp3++ = r2h *dp7++ = r2l                  ; 133F: 4D10D2D2
    clip r6 <- r6                              ; 1340: 67D80000
    *dp4++ = r6h                               ; 1341: 4C200016
    *dp4++ = r6h                               ; 1342: 4C200016
    ret                                        ; 1343: 24000000
