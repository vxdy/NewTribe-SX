; Distortion (FX 11)
; IRAM 0x1182..0x1231 (176 words)

.org 0x1182
fx_dist:
    r0 = *dp0++ r5 = *dp4++                    ; 1182: 4FF31015
    r7 = *dp0++ r6 = *dp4--                    ; 1183: 4FF3171E
    r5 = add r5, r6 r6 = *dp0                  ; 1184: D8D60E00
    r5 = r5 sra 0x1                            ; 1185: 5DB40001
    r2 = mul r0, r5 r3 = *dp3                  ; 1186: 81AACB00
    r2 = msub r0, r3                           ; 1187: 83680000
    *dp3++ = r5h *dp7++ = r5l                  ; 1188: 4D10D5D5
    r4eh = *dp3++ r4l = *dp7++                 ; 1189: 4F13D4D4
    r3eh = *dp3-- r3l = *dp7--                 ; 118A: 4F13DBDB
    r6 = suma r7, r3                           ; 118B: F4780000
    r6 = mas16 r3, r7 r3 = *dp0                ; 118C: B7FA0B00
    r3 = suma r7, r6 r1 = *dp0++               ; 118D: F4CE1100
    r3 = mas16 r6, r7 r0 = *dp0++              ; 118E: E7EE1000
    *dp3++ = r3h *dp7++ = r3l                  ; 118F: 4D10D3D3
    r1 = suma r0, r3                           ; 1190: 84640000
    r1 = mas16 r3, r0                          ; 1191: B7040000
    r2 = add r2, r1 r7 = *dp0++                ; 1192: A82A1700
    clip r2 <- r2 r0 = *dp0                    ; 1193: 774A0800
    *dp3++ = r2h *dp7++ = r2l                  ; 1194: 4D10D2D2
    r6eh = *dp3++ r6l = *dp7++                 ; 1195: 4F13D6D6
    r5eh = *dp3-- r5l = *dp7--                 ; 1196: 4F13DDDD
    r0 = suma r7, r5                           ; 1197: F4A00000
    r0 = mas16 r5, r7 r5 = *dp0                ; 1198: D7E20D00
    r5 = suma r7, r0 r1 = *dp0++               ; 1199: F4161100
    r5 = mas16 r0, r7 r0 = *dp0++              ; 119A: 87F61000
    *dp3++ = r5h *dp7++ = r5l                  ; 119B: 4D10D5D5
    r1 = suma r0, r2 r0 = *dp0++               ; 119C: 84461000
    r1 = suma r0, r3 r0 = *dp0++               ; 119D: 84661000
    r1 = suma r0, r4 r0 = *dp0++               ; 119E: 84861000
    r1 = suma r0, r5 r0 = *dp0--               ; 119F: 84A61800
    r1 = suma r0, r6                           ; 11A0: 84C40000
    r1 = mas16 r6, r0 r0 = *dp0--              ; 11A1: E7061800
    r1 = madd r5, r0 r0 = *dp0--               ; 11A2: D2061800
    r1 = madd r4, r0 r0 = *dp0--               ; 11A3: C2061800
    r1 = madd r3, r0                           ; 11A4: B2040000
    r0 = *dp0##5                               ; 11A5: 44710005
    r1 = madd r2, r0                           ; 11A6: A2040000
    clip r1 <- r1 r2 = *dp0++                  ; 11A7: 77261200
    *dp3++ = r1h *dp7++ = r1l                  ; 11A8: 4D10D1D1
    r0eh = *dp3 r0l = *dp7                     ; 11A9: 4F13C8C8
    r0 = msub r0, r2 r4 = *dp0++               ; 11AA: 83421400
    r0 = madd r4, r2 r7 = *dp0++               ; 11AB: C2421700
    *dp3++ = r0h *dp7++ = r0l                  ; 11AC: 4D10D0D0
    r7 = suma r0, r1                           ; 11AD: 843C0000
    r7 = mas16 r1, r0                          ; 11AE: 971C0000
    r7 = r7 sll 0x8                            ; 11AF: 5FFC0008
    clip r7 <- r7 r2 = *dp0++                  ; 11B0: 77FE1200
    r7 = mul r7, r2                            ; 11B1: F15C0000
    r2 = r7 sll 0x1                            ; 11B2: 5FE80001
    clip r2 <- r7                              ; 11B3: 67E80000
    r3 = mul r7, r7                            ; 11B4: F1EC0000
    if (r7 <0) neg r3 <- r3                    ; 11B5: 666C003F
    r2 = sub r2, r3                            ; 11B6: A9680000
    clip r5 <- r2 r2 = *dp0++                  ; 11B7: 77561200
    r0eh = *dp3 r0l = *dp7                     ; 11B8: 4F13C8C8
    r0 = msub r0, r2 r4 = *dp0++               ; 11B9: 83421400
    r0 = madd r4, r2                           ; 11BA: C2400000
    *dp3++ = r0h *dp7++ = r0l                  ; 11BB: 4D10D0D0
    r2 = mul r5, r0                            ; 11BC: D1080000
    r4eh = *dp3++ r4l = *dp7++                 ; 11BD: 4F13D4D4
    r3eh = *dp3-- r3l = *dp7--                 ; 11BE: 4F13DBDB
    *dp3++ = r3h *dp7++ = r3l                  ; 11BF: 4D10D3D3
    *dp3++ = r2h *dp7++ = r2l                  ; 11C0: 4D10D2D2
    r6eh = *dp3++ r6l = *dp7++                 ; 11C1: 4F13D6D6
    r5eh = *dp3-- r5l = *dp7--                 ; 11C2: 4F13DDDD
    clr r0 <- r0 r7 = *dp0++                   ; 11C3: 71021700
    r0 = suma r7, r5 r1 = *dp0                 ; 11C4: F4A20900
    r0 = mas16 r5, r7 r5 = *dp0++              ; 11C5: D7E21500
    r5 = suma r7, r0                           ; 11C6: F4140000
    r5 = mas16 r0, r7 r0 = *dp0++              ; 11C7: 87F61000
    *dp3++ = r5h *dp7++ = r5l                  ; 11C8: 4D10D5D5
    r1 = suma r0, r2 r0 = *dp0++               ; 11C9: 84461000
    r1 = suma r0, r3 r0 = *dp0++               ; 11CA: 84661000
    r1 = suma r0, r4 r0 = *dp0++               ; 11CB: 84861000
    r1 = suma r0, r5 r0 = *dp0--               ; 11CC: 84A61800
    r1 = suma r0, r6                           ; 11CD: 84C40000
    r1 = mas16 r6, r0 r0 = *dp0--              ; 11CE: E7061800
    r1 = madd r5, r0 r0 = *dp0--               ; 11CF: D2061800
    r1 = madd r4, r0 r0 = *dp0--               ; 11D0: C2061800
    r1 = madd r3, r0                           ; 11D1: B2040000
    r0 = *dp0##6                               ; 11D2: 44710006
    r1 = madd r2, r0 r0 = *dp0--               ; 11D3: A2061800
    r7 = r1 sll 0x2                            ; 11D4: 5F3C0002
    clip r2 <- r7 r1 = *dp0++                  ; 11D5: 77EA1100
    *dp3++ = r2h *dp7++ = r2l                  ; 11D6: 4D10D2D2
    r4eh = *dp3++ r4l = *dp7++                 ; 11D7: 4F13D4D4
    r3eh = *dp3-- r3l = *dp7--                 ; 11D8: 4F13DBDB
    r0 = suma r1, r3                           ; 11D9: 94600000
    r0 = mas16 r3, r1 r3 = *dp0++              ; 11DA: B7221300
    r3 = suma r1, r0                           ; 11DB: 940C0000
    r3 = mas16 r0, r1                          ; 11DC: 872C0000
    *dp3++ = r3h *dp7++ = r3l                  ; 11DD: 4D10D3D3
    clr r1 <- r0 r0 = *dp0++                   ; 11DE: 71061000
    r1 = suma r0, r2 r0 = *dp0++               ; 11DF: 84461000
    r1 = suma r0, r5 r0 = *dp0++               ; 11E0: 84A61000
    r1 = suma r0, r6 r0 = *dp0++               ; 11E1: 84C61000
    r1 = suma r0, r3 r0 = *dp0--               ; 11E2: 84661800
    r1 = suma r0, r4                           ; 11E3: 84840000
    r1 = mas16 r4, r0 r0 = *dp0--              ; 11E4: C7061800
    r1 = madd r3, r0 r0 = *dp0--               ; 11E5: B2061800
    r1 = madd r6, r0 r0 = *dp0--               ; 11E6: E2061800
    r1 = madd r5, r0                           ; 11E7: D2040000
    r0 = *dp0##6                               ; 11E8: 44710006
    r1 = madd r2, r0 r0 = *dp0--               ; 11E9: A2061800
    r7 = r1 sll 0x2                            ; 11EA: 5F3C0002
    clip r2 <- r7 r1 = *dp0++                  ; 11EB: 77EA1100
    *dp3++ = r2h *dp7++ = r2l                  ; 11EC: 4D10D2D2
    r6eh = *dp3++ r6l = *dp7++                 ; 11ED: 4F13D6D6
    r5eh = *dp3-- r5l = *dp7--                 ; 11EE: 4F13DDDD
    r0 = suma r1, r5                           ; 11EF: 94A00000
    r0 = mas16 r5, r1 r5 = *dp0++              ; 11F0: D7221500
    r5 = suma r1, r0                           ; 11F1: 94140000
    r5 = mas16 r0, r1                          ; 11F2: 87340000
    *dp3++ = r5h *dp7++ = r5l                  ; 11F3: 4D10D5D5
    clr r1 <- r0 r0 = *dp0++                   ; 11F4: 71061000
    r1 = suma r0, r2 r0 = *dp0++               ; 11F5: 84461000
    r1 = suma r0, r3 r0 = *dp0++               ; 11F6: 84661000
    r1 = suma r0, r4 r0 = *dp0++               ; 11F7: 84861000
    r1 = suma r0, r5 r0 = *dp0--               ; 11F8: 84A61800
    r1 = suma r0, r6                           ; 11F9: 84C40000
    r1 = mas16 r6, r0 r0 = *dp0--              ; 11FA: E7061800
    r1 = madd r5, r0 r0 = *dp0--               ; 11FB: D2061800
    r1 = madd r4, r0 r0 = *dp0--               ; 11FC: C2061800
    r1 = madd r3, r0                           ; 11FD: B2040000
    r0 = *dp0##5                               ; 11FE: 44710005
    r1 = madd r2, r0                           ; 11FF: A2040000
    r7 = r1 sll 0x2                            ; 1200: 5F3C0002
    clip r7 <- r7 r0 = *dp0++                  ; 1201: 77FE1000
    *dp3++ = r7h *dp7++ = r7l                  ; 1202: 4D10D7D7
    acc+ r6 <- r7 r1 = *dp4++                  ; 1203: 7CF90011
    r6 = madd r0, r1 r1 = *dp4++               ; 1204: 82390011
    r7 = madd r0, r1                           ; 1205: 823C0000
    clip r6 <- r6 r5 = *dp0++                  ; 1206: 77DA1500
    clip r7 <- r7 r1 = *dp0                    ; 1207: 77FE0900
    r0h = *dp3 r0l = *dp7                      ; 1208: 4D13C8C8
    *dp3++ = r6h *dp7++ = r6l                  ; 1209: 4D10D6D6
    r1 = suma r5, r0                           ; 120A: D4040000
    r1 = mas16 r0, r5 r2 = *dp0                ; 120B: 87A60A00
    r2 = suma r5, r6 r3 = *dp0++               ; 120C: D4CA1300
    r2 = mas16 r6, r5 r5 = *dp0++              ; 120D: E7AA1500
    r0h = *dp3 r0l = *dp7                      ; 120E: 4D13C8C8
    r3 = suma r5, r0                           ; 120F: D40C0000
    r3 = mas16 r0, r5 r0 = *dp0                ; 1210: 87AE0800
    r0 = suma r5, r3 r6 = *dp0++               ; 1211: D4621600
    r0 = mas16 r3, r5                          ; 1212: B7A00000
    r5 = *dp0##-4                              ; 1213: 46F1FFFC
    r6 = suma r5, r0                           ; 1214: D4180000
    r6 = mas16 r0, r5                          ; 1215: 87B80000
    r2 = sub r2, r1                            ; 1216: A9280000
    r2 = add r2, r6 r5 = *dp0++                ; 1217: A8CA1500
    clip r2 <- r2 r1 = *dp0                    ; 1218: 774A0900
    *dp3++ = r2h *dp7++ = r2l                  ; 1219: 4D10D2D2
    r2 = r2 sll 0x1                            ; 121A: 5F480001
    clip r2 <- r2                              ; 121B: 67480000
    *dp4++ = r2h                               ; 121C: 4C200012
    r0h = *dp3 r0l = *dp7                      ; 121D: 4D13C8C8
    *dp3++ = r7h *dp7++ = r7l                  ; 121E: 4D10D7D7
    r1 = suma r5, r0                           ; 121F: D4040000
    r1 = mas16 r0, r5 r2 = *dp0                ; 1220: 87A60A00
    r2 = suma r5, r7 r3 = *dp0++               ; 1221: D4EA1300
    r2 = mas16 r7, r5 r5 = *dp0++              ; 1222: F7AA1500
    r0h = *dp3 r0l = *dp7                      ; 1223: 4D13C8C8
    r3 = suma r5, r0                           ; 1224: D40C0000
    r3 = mas16 r0, r5 r0 = *dp0                ; 1225: 87AE0800
    r0 = suma r5, r3 r6 = *dp0++               ; 1226: D4621600
    r0 = mas16 r3, r5 r5 = *dp0++              ; 1227: B7A21500
    r6 = suma r5, r0                           ; 1228: D4180000
    r6 = mas16 r0, r5                          ; 1229: 87B80000
    r2 = sub r2, r1                            ; 122A: A9280000
    r2 = add r2, r6                            ; 122B: A8C80000
    clip r2 <- r2                              ; 122C: 67480000
    *dp3++ = r2h *dp7++ = r2l                  ; 122D: 4D10D2D2
    r2 = r2 sll 0x1                            ; 122E: 5F480001
    clip r2 <- r2                              ; 122F: 67480000
    *dp4 = r2h                                 ; 1230: 4C20000A
    ret                                        ; 1231: 24000000
