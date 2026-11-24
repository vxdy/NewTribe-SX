; Compressor (FX 10)
; IRAM 0x1232..0x127F (78 words)

.org 0x1232
fx_comp:
    r6 = *dp4++                                ; 1232: 4C710016
    clr r3 <- r0 r2 = *dp0++ r7 = *dp4++       ; 1233: 710F1217
    r0eh = *dp3 r0l = *dp7                     ; 1234: 4F13C8C8
    r6 = r6 sra 0x1                            ; 1235: 5DD80001
    *dp3++ = r6h *dp7++ = r6l                  ; 1236: 4D10D6D6
    r6 = sub r6, r0 r1 = *dp0++                ; 1237: E91A1100
    r0eh = *dp3 r0l = *dp7                     ; 1238: 4F13C8C8
    r3 = suma r1, r0                           ; 1239: 940C0000
    r3 = mas16 r0, r1 r4 = *dp0                ; 123A: 872E0C00
    r4 = suma r2, r3                           ; 123B: A4700000
    r4 = mas16 r3, r2 r3 = *dp0                ; 123C: B7520B00
    r3 = suma r2, r4                           ; 123D: A48C0000
    r3 = mas16 r4, r2                          ; 123E: C74C0000
    r6 = add r6, r3                            ; 123F: E8780000
    clip r6 <- r6                              ; 1240: 67D80000
    *dp3++ = r6h *dp7++ = r6l                  ; 1241: 4D10D6D6
    r0eh = *dp3 r0l = *dp7                     ; 1242: 4F13C8C8
    r7 = r7 sra 0x1                            ; 1243: 5DFC0001
    *dp3++ = r7h *dp7++ = r7l                  ; 1244: 4D10D7D7
    r7 = sub r7, r0 r3 = *dp0                  ; 1245: F91E0B00
    r0eh = *dp3 r0l = *dp7                     ; 1246: 4F13C8C8
    r3 = suma r1, r0                           ; 1247: 940C0000
    r3 = mas16 r0, r1 r4 = *dp0                ; 1248: 872E0C00
    r4 = suma r2, r3                           ; 1249: A4700000
    r4 = mas16 r3, r2 r3 = *dp0++              ; 124A: B7521300
    r3 = suma r2, r4                           ; 124B: A48C0000
    r3 = mas16 r4, r2                          ; 124C: C74C0000
    r7 = add r7, r3                            ; 124D: F87C0000
    clip r7 <- r7                              ; 124E: 67FC0000
    *dp3++ = r7h *dp7++ = r7l                  ; 124F: 4D10D7D7
    acc+ r4 <- r6                              ; 1250: 6CD00000
    abs r1 <- r6                               ; 1251: 64C40000
    abs r2 <- r7                               ; 1252: 64E80000
    r3 = sub r2, r1                            ; 1253: A92C0000
    if (r3 >0) acc+ r4 <- r7                   ; 1254: 6CF00023
    r1eh = *dp3 r1l = *dp7                     ; 1255: 4F13C9C9
    r2 = *dp0++                                ; 1256: 4F821200
    r2 = mul r2, r1                            ; 1257: A1280000
    r4 = r4 or 0x1                             ; 1258: 5B900001
    abs r4 <- r4                               ; 1259: 64900000
    r1 = sub r2, r4                            ; 125A: A9840000
    if (r1 <0) acc+ r2 <- r4                   ; 125B: 6C880039
    *dp3++ = r2h *dp7++ = r2l                  ; 125C: 4D10D2D2
    r1eh = *dp3 r1l = *dp7                     ; 125D: 4F13C9C9
    r3 = *dp0++                                ; 125E: 4F821300
    r1 = msub r1, r3                           ; 125F: 93640000
    r1 = madd r2, r3                           ; 1260: A2640000
    *dp3++ = r1h *dp7++ = r1l                  ; 1261: 4D10D1D1
    r0 = *dp0++                                ; 1262: 4F821000
    r0l = *dp0++                               ; 1263: 4C821000
    r4 = *dp0++                                ; 1264: 4F821400
    r5eh = *dp3 r5l = *dp7                     ; 1265: 4F13CDCD
    r5 = msub r5, r4 r2 = *dp0++               ; 1266: D3961200
    r5 = madd r2, r4                           ; 1267: A2940000
    *dp3 = r5h *dp7++ = r5l                    ; 1268: 4D10CDD5
    clr r4 <- r0 r5 = *dp3++                   ; 1269: 7112D500
    r4h = *dp0++                               ; 126A: 4D021400
    repeat 8                                   ; 126B: 1C000008
    acc- r4 <- r5                              ; 126C: 6DB00000
    r4 = r4 sll 0x10                           ; 126D: 5F900010
    r4 = and r4, r0                            ; 126E: CA100000
    *dp0 = r4h                                 ; 126F: 4D000C00
    r1 = sub r0, r1 r2 = *dp0++                ; 1270: 89261200
    r3eh = *dp3 r3l = *dp7                     ; 1271: 4F13CBCB
    r2 = madd r3, r1                           ; 1272: B2280000
    clip r2 <- r2                              ; 1273: 67480000
    *dp3++ = r2h *dp7++ = r2l                  ; 1274: 4D10D2D2
    r2 = mul r2, r5 r1 = *dp0++                ; 1275: A1AA1100
    r2 = mul r2, r1                            ; 1276: A1280000
    r6 = mul r6, r2                            ; 1277: E1580000
    r7 = mul r7, r2                            ; 1278: F15C0000
    r6 = r6 sll 0x7                            ; 1279: 5FD80007
    clip r6 <- r6                              ; 127A: 67D80000
    r7 = r7 sll 0x7                            ; 127B: 5FFC0007
    clip r7 <- r7                              ; 127C: 67FC0000
    *dp4++ = r6h                               ; 127D: 4C200016
    *dp4++ = r7h                               ; 127E: 4C200017
    ret                                        ; 127F: 24000000
