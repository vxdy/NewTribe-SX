; Newtribe custom firmware version - THE ONLY PLACE where it is defined (shown on the read-only 8th Global page).
; Bump here, rebuild.  Must stay at most 8 characters (LCD line width) including nothing else; the NUL is added by .asciz.
NEWTRIBE_VERSION:
	.asciz	"0.0.1"
	.align	4

newtribe_overlay_end:
	.assert	((newtribe_overlay_end - NEWTRIBE_GAP_END - 1) >> 63), "Newtribe overlay does not fit into the zero gap before main_entry (0x0C081000)"
