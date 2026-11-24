; Parametric EQ (FX 13)
; IRAM 0x13DA..0x1445 (108 words)

.org 0x13DA
fx_eq:
    r1 = *dp0++                                ; 13DA: 4F821100
    r2 = *dp0++                                ; 13DB: 4F821200
    r3 = *dp0++                                ; 13DC: 4F821300
    r0 = *dp0                                  ; 13DD: 4F820800
    if (r0 ==0) jmp 0x13e8                     ; 13DE: 2C000510
    clr r0 <- r0                               ; 13DF: 61000000
    *dp0 = r0h                                 ; 13E0: 4D000800
    r4l = dp0                                  ; 13E1: 3E010000
    r4 = r4 add 0x6                            ; 13E2: 58900006
    dp1 = r4l                                  ; 13E3: 3E020000
    dn1 = 0x2                                  ; 13E4: 38120002
    *dp1## = r1h                               ; 13E5: 4D006100
    *dp1## = r2h                               ; 13E6: 4D006200
    *dp1 = r3h                                 ; 13E7: 4D004B00
    r7 = *dp0++                                ; 13E8: 4F821700
    r1 = *dp0++                                ; 13E9: 4F821100
    r2 = *dp0++                                ; 13EA: 4F821200
    r3 = *dp0++                                ; 13EB: 4F821300
    r0 = *dp0                                  ; 13EC: 4F820800
    if (r0 ==0) jmp 0x13f7                     ; 13ED: 2C000510
    clr r0 <- r0                               ; 13EE: 61000000
    *dp0 = r0h                                 ; 13EF: 4D000800
    r4l = dp0                                  ; 13F0: 3E010000
    r4 = r4 add 0x7                            ; 13F1: 58900007
    dp1 = r4l                                  ; 13F2: 3E020000
    dn1 = 0x2                                  ; 13F3: 38120002
    *dp1## = r1h                               ; 13F4: 4D006100
    *dp1## = r2h                               ; 13F5: 4D006200
    *dp1 = r3h                                 ; 13F6: 4D004B00
    r7 = *dp0##2                               ; 13F7: 47F10002
    r0 = *dp4##2                               ; 13F8: 44790002
    r1eh = *dp3 r1l = *dp7                     ; 13F9: 4F13C9C9
    *dp3++ = r0h *dp7++ = r0l                  ; 13FA: 4D10D0D0
    clr r3 <- r0 r7 = *dp0++                   ; 13FB: 710E1700
    r3 = suma r7, r1 r6 = *dp0++               ; 13FC: F42E1600
    r3 = mas16 r1, r7 r7 = *dp0++              ; 13FD: 97EE1700
    r3 = madd r0, r7 r0 = *dp0                 ; 13FE: 82EE0800
    r1eh = *dp3 r1l = *dp7                     ; 13FF: 4F13C9C9
    r5 = mul r1, r6                            ; 1400: 91D40000
    r1 = mul r5, r6                            ; 1401: D1C40000
    r0 = suma r6, r1 r5 = *dp0++               ; 1402: E4221500
    r0 = mas16 r1, r6 r7 = *dp0++              ; 1403: 97C21700
    r5 = suma r7, r0                           ; 1404: F4140000
    r5 = mas16 r0, r7 r7 = *dp0++              ; 1405: 87F61700
    r0 = add r3, r5 r3 = *dp0++                ; 1406: B8A21300
    r0 = r0 sll 0x2                            ; 1407: 5F000002
    clip r0 <- r0                              ; 1408: 67000000
    nop                                        ; 1409: 00000000
    *dp3++ = r0h *dp7++ = r0l                  ; 140A: 4D10D0D0
    r3 = suma r7, r1                           ; 140B: F42C0000
    r3 = mas16 r1, r7 r7 = *dp0++              ; 140C: 97EE1700
    r3 = madd r0, r7 r0 = *dp0                 ; 140D: 82EE0800
    r1eh = *dp3 r1l = *dp7                     ; 140E: 4F13C9C9
    clr r5 <- r0                               ; 140F: 61140000
    r5 = suma r6, r1                           ; 1410: E4340000
    r5 = mas16 r1, r6                          ; 1411: 97D40000
    clr r1 <- r0                               ; 1412: 61040000
    r1 = suma r6, r5                           ; 1413: E4A40000
    r1 = mas16 r5, r6                          ; 1414: D7C40000
    r0 = suma r6, r1 r5 = *dp0++               ; 1415: E4221500
    r0 = mas16 r1, r6 r7 = *dp0++              ; 1416: 97C21700
    r5 = suma r7, r0                           ; 1417: F4140000
    r5 = mas16 r0, r7                          ; 1418: 87F40000
    r0 = add r3, r5                            ; 1419: B8A00000
    r0 = r0 sll 0x1                            ; 141A: 5F000001
    clip r4 <- r0 r1 = *dp0++                  ; 141B: 77121100
    *dp3++ = r4h *dp7++ = r4l                  ; 141C: 4D10D4D4
    r6 = *dp0##-11                             ; 141D: 4771FFF5
    *dp4-- = r4h                               ; 141E: 4C20001C
    r0 = *dp4##2                               ; 141F: 44790002
    clr r3 <- r0                               ; 1420: 610C0000
    r1eh = *dp3 r1l = *dp7                     ; 1421: 4F13C9C9
    *dp3++ = r0h *dp7++ = r0l                  ; 1422: 4D10D0D0
    r7 = *dp0++                                ; 1423: 4F821700
    r3 = suma r7, r1 r6 = *dp0++               ; 1424: F42E1600
    r3 = mas16 r1, r7 r7 = *dp0++              ; 1425: 97EE1700
    r3 = madd r0, r7 r0 = *dp0                 ; 1426: 82EE0800
    r1eh = *dp3 r1l = *dp7                     ; 1427: 4F13C9C9
    r1 = mul r1, r6                            ; 1428: 91C40000
    r1 = mul r1, r6                            ; 1429: 91C40000
    r0 = suma r6, r1 r5 = *dp0++               ; 142A: E4221500
    r0 = mas16 r1, r6 r7 = *dp0++              ; 142B: 97C21700
    r5 = suma r7, r0                           ; 142C: F4140000
    r5 = mas16 r0, r7 r7 = *dp0++              ; 142D: 87F61700
    r0 = add r3, r5 r3 = *dp0++                ; 142E: B8A21300
    r0 = r0 sll 0x2                            ; 142F: 5F000002
    clip r0 <- r0                              ; 1430: 67000000
    *dp3++ = r0h *dp7++ = r0l                  ; 1431: 4D10D0D0
    r3 = suma r7, r1                           ; 1432: F42C0000
    r3 = mas16 r1, r7 r7 = *dp0++              ; 1433: 97EE1700
    r3 = madd r0, r7 r0 = *dp0                 ; 1434: 82EE0800
    r1eh = *dp3 r1l = *dp7                     ; 1435: 4F13C9C9
    clr r5 <- r0                               ; 1436: 61140000
    r5 = suma r6, r1                           ; 1437: E4340000
    r5 = mas16 r1, r6                          ; 1438: 97D40000
    clr r1 <- r0                               ; 1439: 61040000
    r1 = suma r6, r5                           ; 143A: E4A40000
    r1 = mas16 r5, r6                          ; 143B: D7C40000
    r0 = suma r6, r1 r5 = *dp0++               ; 143C: E4221500
    r0 = mas16 r1, r6 r7 = *dp0++              ; 143D: 97C21700
    r5 = suma r7, r0                           ; 143E: F4140000
    r5 = mas16 r0, r7                          ; 143F: 87F40000
    r0 = add r3, r5                            ; 1440: B8A00000
    r0 = r0 sll 0x1                            ; 1441: 5F000001
    clip r4 <- r0 r1 = *dp0++                  ; 1442: 77121100
    *dp3++ = r4h *dp7++ = r4l                  ; 1443: 4D10D4D4
    *dp4 = r4h                                 ; 1444: 4C20000C
    ret                                        ; 1445: 24000000
