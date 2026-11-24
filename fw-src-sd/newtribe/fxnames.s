; Newtribe overlay 5 (ESX-1 SD 01.03.01): LCD label rename for Tape Delay PoC in RingMod FX slot.
;   str_0C0DBC14 ("RingMod ") -> "TapeDly "
;   str_0C0DBB90 ("OSCFreq.") -> "TapeTime"

	.align	4
nt_str_tapedly:
	.asciz	"TapeDly "
	.byte	0x00, 0x00, 0x00

	.align	4
nt_str_tapetime:
	.asciz	"TapeTime"
	.byte	0x00, 0x00, 0x00

.redirect str_0C0DBC14, nt_str_tapedly
.redirect str_0C0DBB90, nt_str_tapetime
