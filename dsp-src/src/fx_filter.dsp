; LPF / HPF Resonant Filter (FX 14/15)
; IRAM 0x1039..0x10F4 (188 words)

.org 0x1039
fx_filter:
    r0eh = *dp3 r0l = *dp7                     ; 1039: 4F13C8C8
    clr r7 <- r0 r1 = *dp0++                   ; 103A: 711E1100
    r0 = msub r0, r1 r4 = *dp0++               ; 103B: 83221400
    r0 = madd r4, r1                           ; 103C: C2200000
    *dp3++ = r0h *dp7++ = r0l                  ; 103D: 4D10D0D0
    r1eh = *dp3++ r1l = *dp7++                 ; 103E: 4F13D1D1
    if (r4 ==0) acc+ r1 <- r7                  ; 103F: 6CE40014
    r2eh = *dp3++ r2l = *dp7++                 ; 1040: 4F13D2D2
    if (r4 ==0) acc+ r2 <- r7                  ; 1041: 6CE80014
    r3 = *dp0++ r5 = *dp4                      ; 1042: 4FF3130D
    r7 = suma r3, r1                           ; 1043: B43C0000
    r7 = mas16 r1, r3 r1 = *dp0                ; 1044: 977E0900
    r1 = suma r3, r7                           ; 1045: B4E40000
    r1 = mas16 r7, r3 r7 = *dp0                ; 1046: F7660F00
    r7 = suma r3, r2 r6 = *dp0                 ; 1047: B45E0E00
    r7 = mas16 r2, r3 r2 = *dp0++              ; 1048: A77E1200
    r2 = suma r3, r7                           ; 1049: B4E80000
    r2 = mas16 r7, r3                          ; 104A: F7680000
    r4eh = *dp3 r4l = *dp7                     ; 104B: 4F13CCCC
    r7 = mul r5, r0 r3 = *dp0++                ; 104C: D11E1300
    r6 = suma r3, r4 r0 = *dp0++               ; 104D: B49A1000
    r0l = *dp0++                               ; 104E: 4C821000
    r6 = mas16 r4, r3                          ; 104F: C7780000
    r4 = sub r4, r6 r6 = *dp0                  ; 1050: C9D20E00
    r6 = suma r3, r0                           ; 1051: B4180000
    r6 = mas16 r0, r3                          ; 1052: 87780000
    r4 = add r4, r6 r3 = *dp0++                ; 1053: C8D21300
    *dp3++ = r4h *dp7++ = r4l                  ; 1054: 4D10D4D4
    r3 = suma r1, r4                           ; 1055: 948C0000
    r3 = suma r4, r1                           ; 1056: C42C0000
    r3 = mas16 r1, r4                          ; 1057: 978C0000
    r3 = add r3, r3                            ; 1058: B86C0000
    r7 = add r7, r3                            ; 1059: F87C0000
    r3 = sub r7, r2                            ; 105A: F94C0000
    clip r6 <- r3 r3 = *dp0++                  ; 105B: 777A1300
    r4eh = *dp3 r4l = *dp7                     ; 105C: 4F13CCCC
    r4 = msub r4, r3 r0 = *dp0++               ; 105D: C3721000
    r4 = madd r0, r3 r3 = *dp0                 ; 105E: 82720B00
    *dp3##-3 = r4h                             ; 105F: 4626FFFD
    *dp7##-3 = r4l                             ; 1060: 461EFFFD
    r3 = suma r4, r6                           ; 1061: C4CC0000
    r3 = mas16 r6, r4                          ; 1062: E78C0000
    r3 = add r3, r3                            ; 1063: B86C0000
    r3 = add r3, r1                            ; 1064: B82C0000
    clip r5 <- r3 r3 = *dp0++                  ; 1065: 77761300
    *dp3++ = r5h *dp7++ = r5l                  ; 1066: 4D10D5D5
    r3 = suma r4, r5 r1 = *dp0++               ; 1067: C4AE1100
    r3 = mas16 r5, r4                          ; 1068: D78C0000
    r3 = add r3, r3                            ; 1069: B86C0000
    r3 = add r3, r2                            ; 106A: B84C0000
    clip r2 <- r3 r0 = *dp0                    ; 106B: 776A0800
    *dp3##3 = r2h                              ; 106C: 45260003
    *dp7##3 = r2l                              ; 106D: 451E0003
    r3eh = *dp3 r3l = *dp7                     ; 106E: 4F13CBCB
    r0 = suma r1, r3                           ; 106F: 94600000
    r0 = mas16 r3, r1 r3 = *dp0                ; 1070: B7220B00
    r3 = suma r1, r0                           ; 1071: 940C0000
    r3 = mas16 r0, r1 r0 = *dp0                ; 1072: 872E0800
    *dp3++ = r3h *dp7++ = r3l                  ; 1073: 4D10D3D3
    r3eh = *dp3 r3l = *dp7                     ; 1074: 4F13CBCB
    r0 = suma r1, r3                           ; 1075: 94600000
    r0 = mas16 r3, r1 r3 = *dp0++              ; 1076: B7221300
    r3 = suma r1, r0                           ; 1077: 940C0000
    r3 = mas16 r0, r1 r1 = *dp0++              ; 1078: 872E1100
    *dp3-- = r3h *dp7-- = r3l                  ; 1079: 4D10DBDB
    r1 = mul r4, r1                            ; 107A: C1240000
    r1 = r1 sll 0x2                            ; 107B: 5F240002
    clip r1 <- r1 r0 = *dp0                    ; 107C: 77260800
    r3eh = *dp3 r3l = *dp7                     ; 107D: 4F13CBCB
    r0 = suma r1, r3                           ; 107E: 94600000
    r0 = mas16 r3, r1                          ; 107F: B7200000
    r3 = sub r3, r0 r0 = *dp0                  ; 1080: B90E0800
    r0 = suma r1, r2                           ; 1081: 94400000
    r0 = mas16 r2, r1                          ; 1082: A7200000
    r2 = add r3, r0 r0 = *dp0                  ; 1083: B80A0800
    *dp3++ = r2h *dp7++ = r2l                  ; 1084: 4D10D2D2
    r3eh = *dp3 r3l = *dp7                     ; 1085: 4F13CBCB
    r0 = suma r1, r3                           ; 1086: 94600000
    r0 = mas16 r3, r1                          ; 1087: B7200000
    r3 = sub r3, r0 r0 = *dp0++                ; 1088: B90E1000
    r0 = suma r1, r2                           ; 1089: 94400000
    r0 = mas16 r2, r1                          ; 108A: A7200000
    r2 = add r3, r0 r0 = *dp0++                ; 108B: B80A1000
    *dp3##-6 = r2h                             ; 108C: 4526FFFA
    *dp7##-6 = r2l                             ; 108D: 451EFFFA
    r4 = mul r0, r2 r0 = *dp0++                ; 108E: 81521000
    r4 = madd r0, r6 r0 = *dp0++               ; 108F: 82D21000
    r4 = madd r0, r5 r0 = *dp0++               ; 1090: 82B21000
    r4 = madd r0, r7                           ; 1091: 82F00000
    r0 = *dp0##-18                             ; 1092: 4471FFEE
    r7 = *dp4##2                               ; 1093: 47F90002
    r4 = madd r0, r7                           ; 1094: 82F00000
    clr r0 <- r0                               ; 1095: 61000000
    inc r0 <- r0                               ; 1096: 62000000
    r0 = r0 sll 0xf                            ; 1097: 5F00000F
    clr r1 <- r0                               ; 1098: 61040000
    if (r4 >=0) acc+ r0 <- r1                  ; 1099: 6C200034
    r4 = add r4, r0                            ; 109A: C8100000
    clip r4 <- r4                              ; 109B: 67900000
    round r4 <- r4                             ; 109C: 68900000
    *dp4-- = r4h                               ; 109D: 4C20001C
    r4 = *dp0++                                ; 109E: 4F821400
    r0eh = *dp3##7                             ; 109F: 44670007
    r0l = *dp7##7                              ; 10A0: 441F0007
    r1eh = *dp3++ r1l = *dp7++                 ; 10A1: 4F13D1D1
    clr r7 <- r0 r3 = *dp0++                   ; 10A2: 711E1300
    if (r4 ==0) acc+ r1 <- r7                  ; 10A3: 6CE40014
    r2eh = *dp3##-5                            ; 10A4: 4567FFFB
    r2l = *dp7##-5                             ; 10A5: 451FFFFB
    if (r4 ==0) acc+ r2 <- r7                  ; 10A6: 6CE80014
    r7 = suma r3, r1                           ; 10A7: B43C0000
    r7 = mas16 r1, r3 r1 = *dp0                ; 10A8: 977E0900
    r1 = suma r3, r7                           ; 10A9: B4E40000
    r1 = mas16 r7, r3 r7 = *dp0                ; 10AA: F7660F00
    r7 = suma r3, r2                           ; 10AB: B45C0000
    r7 = mas16 r2, r3 r2 = *dp0                ; 10AC: A77E0A00
    r2 = suma r3, r7                           ; 10AD: B4E80000
    r2 = mas16 r7, r3 r5 = *dp4                ; 10AE: F769000D
    r7 = mul r5, r0 r3 = *dp0                  ; 10AF: D11E0B00
    r4eh = *dp3++ r4l = *dp7++                 ; 10B0: 4F13D4D4
    r3 = suma r1, r4                           ; 10B1: 948C0000
    r3 = suma r4, r1                           ; 10B2: C42C0000
    r3 = mas16 r1, r4                          ; 10B3: 978C0000
    r3 = add r3, r3                            ; 10B4: B86C0000
    r7 = add r7, r3                            ; 10B5: F87C0000
    r3 = sub r7, r2                            ; 10B6: F94C0000
    clip r6 <- r3 r3 = *dp0                    ; 10B7: 777A0B00
    r4eh = *dp3##3                             ; 10B8: 46670003
    r4l = *dp7##3                              ; 10B9: 461F0003
    r3 = suma r4, r6                           ; 10BA: C4CC0000
    r3 = mas16 r6, r4                          ; 10BB: E78C0000
    r3 = add r3, r3                            ; 10BC: B86C0000
    r3 = add r3, r1                            ; 10BD: B82C0000
    clip r5 <- r3 r3 = *dp0--                  ; 10BE: 77761B00
    *dp3++ = r5h *dp7++ = r5l                  ; 10BF: 4D10D5D5
    r3 = suma r4, r5                           ; 10C0: C4AC0000
    r3 = mas16 r5, r4                          ; 10C1: D78C0000
    r3 = add r3, r3 r1 = *dp0++                ; 10C2: B86E1100
    r3 = add r3, r2 r0 = *dp0                  ; 10C3: B84E0800
    clip r2 <- r3                              ; 10C4: 67680000
    *dp3++ = r2h *dp7++ = r2l                  ; 10C5: 4D10D2D2
    r3eh = *dp3 r3l = *dp7                     ; 10C6: 4F13CBCB
    r0 = suma r1, r3                           ; 10C7: 94600000
    r0 = mas16 r3, r1 r3 = *dp0                ; 10C8: B7220B00
    r3 = suma r1, r0                           ; 10C9: 940C0000
    r3 = mas16 r0, r1 r0 = *dp0                ; 10CA: 872E0800
    *dp3++ = r3h *dp7++ = r3l                  ; 10CB: 4D10D3D3
    r3eh = *dp3 r3l = *dp7                     ; 10CC: 4F13CBCB
    r0 = suma r1, r3                           ; 10CD: 94600000
    r0 = mas16 r3, r1                          ; 10CE: B7200000
    r3 = *dp0##10                              ; 10CF: 45F1000A
    r3 = suma r1, r0                           ; 10D0: 940C0000
    r3 = mas16 r0, r1 r1 = *dp0++              ; 10D1: 872E1100
    *dp3-- = r3h *dp7-- = r3l                  ; 10D2: 4D10DBDB
    r1 = mul r4, r1                            ; 10D3: C1240000
    r1 = r1 sll 0x2                            ; 10D4: 5F240002
    clip r1 <- r1 r0 = *dp0                    ; 10D5: 77260800
    r3eh = *dp3 r3l = *dp7                     ; 10D6: 4F13CBCB
    r0 = suma r1, r3                           ; 10D7: 94600000
    r0 = mas16 r3, r1                          ; 10D8: B7200000
    r3 = sub r3, r0 r0 = *dp0                  ; 10D9: B90E0800
    r0 = suma r1, r2                           ; 10DA: 94400000
    r0 = mas16 r2, r1                          ; 10DB: A7200000
    r2 = add r3, r0 r0 = *dp0                  ; 10DC: B80A0800
    *dp3++ = r2h *dp7++ = r2l                  ; 10DD: 4D10D2D2
    r3eh = *dp3 r3l = *dp7                     ; 10DE: 4F13CBCB
    r0 = suma r1, r3                           ; 10DF: 94600000
    r0 = mas16 r3, r1                          ; 10E0: B7200000
    r3 = sub r3, r0 r0 = *dp0++                ; 10E1: B90E1000
    r0 = suma r1, r2                           ; 10E2: 94400000
    r0 = mas16 r2, r1                          ; 10E3: A7200000
    r2 = add r3, r0 r0 = *dp0++                ; 10E4: B80A1000
    *dp3++ = r2h *dp7++ = r2l                  ; 10E5: 4D10D2D2
    r4 = mul r0, r2 r0 = *dp0++                ; 10E6: 81521000
    r4 = madd r0, r6 r0 = *dp0++               ; 10E7: 82D21000
    r4 = madd r0, r5 r0 = *dp0++               ; 10E8: 82B21000
    r4 = madd r0, r7 r0 = *dp0++               ; 10E9: 82F21000
    clr r1 <- r0 r7 = *dp4++                   ; 10EA: 71050017
    r4 = madd r0, r7 r7 = *dp4++               ; 10EB: 82F10017
    clr r0 <- r0                               ; 10EC: 61000000
    inc r0 <- r0                               ; 10ED: 62000000
    r0 = r0 sll 0xf                            ; 10EE: 5F00000F
    if (r4 >=0) acc+ r0 <- r1                  ; 10EF: 6C200034
    r4 = add r4, r0                            ; 10F0: C8100000
    clip r4 <- r4                              ; 10F1: 67900000
    round r4 <- r4                             ; 10F2: 68900000
    *dp4 = r4h                                 ; 10F3: 4C20000C
    ret                                        ; 10F4: 24000000
