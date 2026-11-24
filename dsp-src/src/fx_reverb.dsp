; Reverb (FX 0, extRAM)
; IRAM 0x10F5..0x1181 (141 words)

.org 0x10F5
fx_reverb:
    r7l = *dp0++                               ; 10F5: 4C821700
    r6l = *dp0++                               ; 10F6: 4C821600
    dp1 = r7l                                  ; 10F7: 3F820000
    *x:0x386c = r7l                            ; 10F8: 4B90386C
    dp2 = r6l                                  ; 10F9: 3F040000
    r7 = *dp4++                                ; 10FA: 4C710017
    r6 = *dp4--                                ; 10FB: 4C71001E
    r6 = add r6, r7 r0 = *dp0++                ; 10FC: E8FA1000
    r2eh = *dp3++ r2l = *dp7++                 ; 10FD: 4F13D2D2
    r2eh = *dp3-- r2l = *dp7--                 ; 10FE: 4F13DADA
    r0 = madd r0, r2                           ; 10FF: 82400000
    r6 = mul r6, r0 r4 = *dp0++                ; 1100: E11A1400
    r0eh = *dp3 r0l = *dp7                     ; 1101: 4F13C8C8
    r0 = msub r0, r4 r2 = *dp0++               ; 1102: 83821200
    r0 = madd r2, r4 r2 = *dp0++               ; 1103: A2821200
    *dp3++ = r0h *dp7++ = r0l                  ; 1104: 4D10D0D0
    acc+ r7 <- r6 r3 = *dp2++                  ; 1105: 7CDE9300
    r3 = mul r3, r2                            ; 1106: B14C0000
    r3 = mul r3, r2                            ; 1107: B14C0000
    r7 = madd r3, r0                           ; 1108: B21C0000
    clip r7 <- r7 r3 = *dp2++                  ; 1109: 77FE9300
    r3 = mul r3, r2 *dp1++ = r7h               ; 110A: B14C5700
    r3 = mul r3, r2                            ; 110B: B14C0000
    r6 = msub r3, r0                           ; 110C: B3180000
    clip r6 <- r6 r3 = *dp0++                  ; 110D: 77DA1300
    r7 = add r7, r6 *dp1++ = r6h               ; 110E: F8DC5600
    clip r1 <- r7 r7 = *dp2++                  ; 110F: 77E69700
    r7 = mul r7, r3                            ; 1110: F17C0000
    r7 = mul r7, r3 r2 = *dp0++                ; 1111: F17E1200
    r1 = msub r7, r2                           ; 1112: F3440000
    clip r1 <- r1                              ; 1113: 67240000
    r7 = madd r1, r2 *dp1++ = r1h              ; 1114: 925C5100
    clip r7 <- r7 r6 = *dp2++                  ; 1115: 77FE9600
    r6 = mul r6, r3 r2 = *dp0++                ; 1116: E17A1200
    r6 = mul r6, r3                            ; 1117: E1780000
    r7 = msub r6, r2                           ; 1118: E35C0000
    clip r7 <- r7 r0 = *dp0++                  ; 1119: 77FE1000
    r6 = madd r7, r2 *dp1++ = r7h              ; 111A: F2585700
    clip r7 <- r6 r2 = *dp0++                  ; 111B: 77DE1200
    r7 = mul r7, r0 *dp1 = r7h                 ; 111C: F11C4F00
    r0eh = *dp3 r0l = *dp7                     ; 111D: 4F13C8C8
    r0 = msub r0, r2 r3 = *dp0++               ; 111E: 83421300
    r0 = madd r3, r2 r2 = *dp4++               ; 111F: B2410012
    *dp3++ = r0h *dp7++ = r0l                  ; 1120: 4D10D0D0
    r2 = madd r7, r0 r1 = *dp4++               ; 1121: F2090011
    clip r2 <- r2 r6 = *dp2                    ; 1122: 774A8E00
    r1 = madd r6, r0                           ; 1123: E2040000
    clip r1 <- r1 *dp4++ = r2h                 ; 1124: 77240012
    r5l = *dp0 *dp4 = r1h                      ; 1125: 4CA20D09
    inc r5 <- r5                               ; 1126: 62B40000
    r5 = r5 and 0xfff                          ; 1127: 5AB40FFF
    *dp0++ = r5l                               ; 1128: 4C801500
    r0 = *dp0++                                ; 1129: 4F821000
    r0l = *dp0++                               ; 112A: 4C821000
    r7 = add r5, r0                            ; 112B: D81C0000
    *x:0x3849 = r7l                            ; 112C: 4B903849
    *x:0x384a = r7h                            ; 112D: 4BA0384A
    r7l = 0x1000                               ; 112E: 3B811000
    *x:0x384b = r7l                            ; 112F: 4B90384B
    r7l = 0x1                                  ; 1130: 3B810001
    *x:0x384c = r7l                            ; 1131: 4B90384C
    r7l = 0x50                                 ; 1132: 3B810050
    *x:0x3842 = r7l                            ; 1133: 4B903842
    r1l = *dp0++                               ; 1134: 4C821100
    r1 = sub r5, r1                            ; 1135: D9240000
    r1 = r1 and 0xfff                          ; 1136: 5A240FFF
    r1 = add r1, r0                            ; 1137: 98040000
    r0 = r0 add 0x1000                         ; 1138: 58001000
    r2l = *dp0++                               ; 1139: 4C821200
    r2 = sub r5, r2                            ; 113A: D9480000
    r2 = r2 and 0xfff                          ; 113B: 5A480FFF
    r2 = add r2, r0                            ; 113C: A8080000
    r0 = r0 add 0x1000                         ; 113D: 58001000
    r3l = *dp0++                               ; 113E: 4C821300
    r3 = sub r5, r3                            ; 113F: D96C0000
    r3 = r3 and 0xfff                          ; 1140: 5A6C0FFF
    r3 = add r3, r0                            ; 1141: B80C0000
    r0 = r0 add 0x1000                         ; 1142: 58001000
    r4l = *dp0++                               ; 1143: 4C821400
    r4 = sub r5, r4                            ; 1144: D9900000
    r4 = r4 and 0xfff                          ; 1145: 5A900FFF
    r4 = add r4, r0                            ; 1146: C8100000
    r0 = r0 add 0x1000                         ; 1147: 58001000
    r6l = *dp0++                               ; 1148: 4C821600
    r6 = sub r5, r6                            ; 1149: D9D80000
    r6 = r6 and 0xfff                          ; 114A: 5AD80FFF
    r6 = add r6, r0                            ; 114B: E8180000
    r0l = 0x3f                                 ; 114C: 3801003F
    *x:0x38c1 = r0l                            ; 114D: 481038C1
    r0 = r1 srl 0xc                            ; 114E: 5E20000C
    r0 = r0 add 0x18                           ; 114F: 58000018
    r0 = r0 and 0x18                           ; 1150: 5A000018
    *x:0x3844 = r0l                            ; 1151: 48103844
    r0 = r1 and 0x7fff                         ; 1152: 5A207FFF
    r0 = r0 add 0x8000                         ; 1153: 58008000
    dp6 = r0l                                  ; 1154: 3C0C0000
    r0 = r2 srl 0xc                            ; 1155: 5E40000C
    r1l = *dp6                                 ; 1156: 4C110089
    r0 = r0 add 0x18                           ; 1157: 58000018
    r0 = r0 and 0x18                           ; 1158: 5A000018
    *x:0x3844 = r0l                            ; 1159: 48103844
    r0 = r2 and 0x7fff                         ; 115A: 5A407FFF
    r0 = r0 add 0x8000                         ; 115B: 58008000
    dp6 = r0l                                  ; 115C: 3C0C0000
    r0 = r3 srl 0xc                            ; 115D: 5E60000C
    r2l = *dp6                                 ; 115E: 4C11008A
    r0 = r0 add 0x18                           ; 115F: 58000018
    r0 = r0 and 0x18                           ; 1160: 5A000018
    *x:0x3844 = r0l                            ; 1161: 48103844
    r0 = r3 and 0x7fff                         ; 1162: 5A607FFF
    r0 = r0 add 0x8000                         ; 1163: 58008000
    dp6 = r0l                                  ; 1164: 3C0C0000
    r0 = r4 srl 0xc                            ; 1165: 5E80000C
    r3l = *dp6                                 ; 1166: 4C11008B
    r0 = r0 add 0x18                           ; 1167: 58000018
    r0 = r0 and 0x18                           ; 1168: 5A000018
    *x:0x3844 = r0l                            ; 1169: 48103844
    r0 = r4 and 0x7fff                         ; 116A: 5A807FFF
    r0 = r0 add 0x8000                         ; 116B: 58008000
    dp6 = r0l                                  ; 116C: 3C0C0000
    r0 = r6 srl 0xc                            ; 116D: 5EC0000C
    r4l = *dp6                                 ; 116E: 4C11008C
    r0 = r0 add 0x18                           ; 116F: 58000018
    r0 = r0 and 0x18                           ; 1170: 5A000018
    *x:0x3844 = r0l                            ; 1171: 48103844
    r0 = r6 and 0x7fff                         ; 1172: 5AC07FFF
    r0 = r0 add 0x8000                         ; 1173: 58008000
    dp6 = r0l                                  ; 1174: 3C0C0000
    r0l = 0x0                                  ; 1175: 38010000
    r6l = *dp6                                 ; 1176: 4C11008E
    *x:0x38c1 = r0l                            ; 1177: 481038C1
    *dp2-- = r6l                               ; 1178: 4C809E00
    *dp2-- = r4l                               ; 1179: 4C809C00
    *dp2-- = r3l                               ; 117A: 4C809B00
    *dp2-- = r2l                               ; 117B: 4C809A00
    *dp2 = r1l                                 ; 117C: 4C808900
    r0l = 0x5                                  ; 117D: 38010005
    *x:0x386d = r0l                            ; 117E: 4810386D
    r0l = 0x30                                 ; 117F: 38010030
    *x:0x386e = r0l                            ; 1180: 4810386E
    ret                                        ; 1181: 24000000
