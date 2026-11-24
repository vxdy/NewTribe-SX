; Short Delay (FX 2, extRAM)
; IRAM 0x1362..0x13D9 (120 words)

.org 0x1362
fx_shortdly:
    r7l = *dp0++                               ; 1362: 4C821700
    r6l = *dp0++                               ; 1363: 4C821600
    dp1 = r7l                                  ; 1364: 3F820000
    *x:0x386c = r7l                            ; 1365: 4B90386C
    dp2 = r6l                                  ; 1366: 3F040000
    r1eh = *dp3 r1l = *dp7                     ; 1367: 4F13C9C9
    clr r7 <- r0 r0 = *dp0++                   ; 1368: 711E1000
    r1 = msub r1, r0 r2 = *dp0++               ; 1369: 93061200
    r1 = madd r2, r0 r0 = *dp0++               ; 136A: A2061000
    *dp3++ = r1h *dp7++ = r1l                  ; 136B: 4D10D1D1
    r0l = *dp0++                               ; 136C: 4C821000
    r2 = r1 sra 0x1                            ; 136D: 5D280001
    r2 = sub r0, r2 r4 = *dp4++                ; 136E: 89490014
    r5 = mul r4, r2 r4 = *dp4++                ; 136F: C1550014
    r6 = mul r4, r2 r4 = *dp0++                ; 1370: C15A1400
    r7 = *dp0++                                ; 1371: 4F821700
    r2 = *dp0++                                ; 1372: 4F821200
    r7 = mul r7, r2                            ; 1373: F15C0000
    r3eh = *dp3 r3l = *dp7                     ; 1374: 4F13CBCB
    clr r2 <- r0                               ; 1375: 61080000
    r2 = suma r4, r3                           ; 1376: C4680000
    r2 = mas16 r3, r4                          ; 1377: B7880000
    r3 = sub r3, r2                            ; 1378: B94C0000
    clr r2 <- r0                               ; 1379: 61080000
    r2 = suma r4, r7                           ; 137A: C4E80000
    r2 = mas16 r7, r4                          ; 137B: F7880000
    r3 = add r3, r2 r2 = *dp2++                ; 137C: B84E9200
    r7eh = *dp3 r7l = *dp7                     ; 137D: 4F13CFCF
    *dp3++ = r3h *dp7++ = r3l                  ; 137E: 4D10D3D3
    r4 = r7 sll 0xf                            ; 137F: 5FF0000F
    r4 = and r4, r0 r7 = *dp2++                ; 1380: CA129700
    r2 = msub r2, r4                           ; 1381: A3880000
    r2 = madd r7, r4 r0 = *dp0++               ; 1382: F28A1000
    clip r2 <- r2                              ; 1383: 67480000
    r2 = mul r2, r0                            ; 1384: A1080000
    r6 = msub r2, r1 r2 = *dp2++               ; 1385: A33A9200
    clip r6 <- r6 r7 = *dp2                    ; 1386: 77DA8F00
    r2 = msub r2, r4                           ; 1387: A3880000
    r2 = madd r7, r4                           ; 1388: F2880000
    clip r2 <- r2                              ; 1389: 67480000
    r2 = mul r2, r0                            ; 138A: A1080000
    r5 = msub r2, r1                           ; 138B: A3340000
    clip r5 <- r5                              ; 138C: 67B40000
    *dp1++ = r5h *dp4++ = r5h                  ; 138D: 4D205515
    *dp1 = r6h *dp4 = r6h                      ; 138E: 4D204E0E
    clr r5 <- r0                               ; 138F: 61140000
    r5l = *dp0                                 ; 1390: 4C820D00
    inc r5 <- r5                               ; 1391: 62B40000
    r5 = r5 and 0x3fff                         ; 1392: 5AB43FFF
    *dp0++ = r5l                               ; 1393: 4C801500
    r0 = *dp0++                                ; 1394: 4F821000
    r0l = *dp0++                               ; 1395: 4C821000
    r7 = add r5, r0                            ; 1396: D81C0000
    *x:0x3849 = r7l                            ; 1397: 4B903849
    *x:0x384a = r7h                            ; 1398: 4BA0384A
    r7l = 0x4000                               ; 1399: 3B814000
    *x:0x384b = r7l                            ; 139A: 4B90384B
    r7l = 0x1                                  ; 139B: 3B810001
    *x:0x384c = r7l                            ; 139C: 4B90384C
    r7l = 0x50                                 ; 139D: 3B810050
    *x:0x3842 = r7l                            ; 139E: 4B903842
    r3 = r3 sra 0x10                           ; 139F: 5D6C0010
    r1 = sub r5, r3                            ; 13A0: D9640000
    r1 = r1 and 0x3fff                         ; 13A1: 5A243FFF
    dec r2 <- r1                               ; 13A2: 63280000
    r2 = r2 and 0x3fff                         ; 13A3: 5A483FFF
    r1 = add r1, r0                            ; 13A4: 98040000
    r2 = add r2, r0                            ; 13A5: A8080000
    r0 = r0 add 0x4000                         ; 13A6: 58004000
    r3 = sub r5, r3                            ; 13A7: D96C0000
    r3 = r3 and 0x3fff                         ; 13A8: 5A6C3FFF
    dec r4 <- r3                               ; 13A9: 63700000
    r4 = r4 and 0x3fff                         ; 13AA: 5A903FFF
    r3 = add r3, r0                            ; 13AB: B80C0000
    r4 = add r4, r0                            ; 13AC: C8100000
    r0l = 0x3f                                 ; 13AD: 3801003F
    *x:0x38c1 = r0l                            ; 13AE: 481038C1
    r0 = r1 srl 0xc                            ; 13AF: 5E20000C
    r0 = r0 add 0x18                           ; 13B0: 58000018
    r0 = r0 and 0x18                           ; 13B1: 5A000018
    *x:0x3844 = r0l                            ; 13B2: 48103844
    r0 = r1 and 0x7fff                         ; 13B3: 5A207FFF
    r0 = r0 add 0x8000                         ; 13B4: 58008000
    dp6 = r0l                                  ; 13B5: 3C0C0000
    r0 = r2 srl 0xc                            ; 13B6: 5E40000C
    r1l = *dp6                                 ; 13B7: 4C110089
    r0 = r0 add 0x18                           ; 13B8: 58000018
    r0 = r0 and 0x18                           ; 13B9: 5A000018
    *x:0x3844 = r0l                            ; 13BA: 48103844
    r0 = r2 and 0x7fff                         ; 13BB: 5A407FFF
    r0 = r0 add 0x8000                         ; 13BC: 58008000
    dp6 = r0l                                  ; 13BD: 3C0C0000
    r0 = r3 srl 0xc                            ; 13BE: 5E60000C
    r2l = *dp6                                 ; 13BF: 4C11008A
    r0 = r0 add 0x18                           ; 13C0: 58000018
    r0 = r0 and 0x18                           ; 13C1: 5A000018
    *x:0x3844 = r0l                            ; 13C2: 48103844
    r0 = r3 and 0x7fff                         ; 13C3: 5A607FFF
    r0 = r0 add 0x8000                         ; 13C4: 58008000
    dp6 = r0l                                  ; 13C5: 3C0C0000
    r0 = r4 srl 0xc                            ; 13C6: 5E80000C
    r3l = *dp6                                 ; 13C7: 4C11008B
    r0 = r0 add 0x18                           ; 13C8: 58000018
    r0 = r0 and 0x18                           ; 13C9: 5A000018
    *x:0x3844 = r0l                            ; 13CA: 48103844
    r0 = r4 and 0x7fff                         ; 13CB: 5A807FFF
    r0 = r0 add 0x8000                         ; 13CC: 58008000
    dp6 = r0l                                  ; 13CD: 3C0C0000
    r0l = 0x0                                  ; 13CE: 38010000
    r4l = *dp6                                 ; 13CF: 4C11008C
    *x:0x38c1 = r0l                            ; 13D0: 481038C1
    *dp2-- = r4l                               ; 13D1: 4C809C00
    *dp2-- = r3l                               ; 13D2: 4C809B00
    *dp2-- = r2l                               ; 13D3: 4C809A00
    *dp2 = r1l                                 ; 13D4: 4C808900
    r0l = 0x2                                  ; 13D5: 38010002
    *x:0x386d = r0l                            ; 13D6: 4810386D
    r0l = 0x30                                 ; 13D7: 38010030
    *x:0x386e = r0l                            ; 13D8: 4810386E
    ret                                        ; 13D9: 24000000
