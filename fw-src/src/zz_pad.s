; RAM filler: random bytes that the boot flash copies together with the image (SDRAM 0x0C0ED9F0..), used as RAM at run time
; The RAM variables (var_*) start right behind the image at FIXED addresses that the boot flash code shares, so the
; image may shrink (gap is zero filled) but must not grow past 0x0C0ED9F0.
	.org	0x0C0ED9F0, 0
	.incbin	"../data/ram_pad.bin"
