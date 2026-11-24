; Newtribe custom firmware version for ESX-1 SD (OS 01.03.01 base)
NEWTRIBE_VERSION:
	.asciz	"0.0.1"
	.align	4

newtribe_overlay_end:
	.assert	((newtribe_overlay_end - NEWTRIBE_GAP_END - 1) >> 63), "Newtribe overlay does not fit into the zero gap before main_entry (0x0C081000)"
