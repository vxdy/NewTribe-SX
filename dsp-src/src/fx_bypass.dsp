; FX Bypass (outL=inL, outR=inR)
; IRAM 0x1034..0x1038 (5 words)

.org 0x1034
fx_bypass:
    r0 = *dp4++                                ; 1034: 4C710010
    r1 = *dp4++                                ; 1035: 4C710011
    *dp4++ = r0h                               ; 1036: 4C200010
    *dp4++ = r1h                               ; 1037: 4C200011
    ret                                        ; 1038: 24000000
