; Newtribe overlay 1 (ESX-1 SD 01.03.01):
;   - 8th page of the GLOBAL menu: "Newtrb I" / NEWTRIBE_VERSION (read-only)
;   - 9th page of the GLOBAL menu: "ShiftMut" / Off|On (code in shiftmute.s)
;
; All addresses verified against factory-firmware-sd/ESX0103N.BSS (see sd-dump/BOOTLOADER_UND_DIFF.md).

NEWTRIBE_GAP_END = 0x0C081000

; factory routines (01.03.01)
lcd_set_cursor = func_0C0B1BB0		; r4 = LCD position (0 = line 1, 8 = line 2)
lcd_print_str  = func_0C0B1E1A		; r4 = NUL terminated string
nop_stub_edit  = dat_0C093300		; rts / nop (000B 0009)
nop_stub_leave = dat_0C0932FC		; rts / nop (000B 0009)
nop_stub_enter = dat_0C0932FC

	.org	0x0C080648
	.align	4

; display handler of the new page (idx 42 of the display table)
newtribe_page_display:
	sts.l	pr,@-r15
	mov.l	=lcd_set_cursor,r2
	jsr	@r2
	mov	#0,r4
	mov.l	=newtribe_title,r4
	mov.l	=lcd_print_str,r2
	jsr	@r2
	nop
	mov.l	=lcd_set_cursor,r2
	jsr	@r2
	mov	#8,r4
	mov.l	=NEWTRIBE_VERSION,r4
	mov.l	=lcd_print_str,r2
	jmp	@r2
	lds.l	@r15+,pr
	.pool

newtribe_title:
	.asciz	"Newtrb I"
	.align	4

; relocated 44-entry menu tables (42 factory entries + idx 42 "Newtrb I" + idx 43 "ShiftMut")
newtribe_tbl_edit:
	.copylong	dat_0C0D333C__vanilla, 42
	.long	nop_stub_edit			; idx 42: "Newtrb I" (read-only)
	.long	newtribe_page2_edit		; idx 43: "ShiftMut" (shiftmute.s)
newtribe_tbl_leave:
	.copylong	dat_0C0D355C__vanilla, 42
	.long	nop_stub_leave
	.long	nop_stub_leave
newtribe_tbl_enter:
	.copylong	dat_0C0D3604__vanilla, 42
	.long	nop_stub_enter
	.long	nop_stub_enter
newtribe_tbl_display:
	.copylong	dat_0C0D36AC__vanilla, 42
	.long	newtribe_page_display
	.long	newtribe_page2_display
newtribe_tbl_maxpage:
	.copylong	dat_0C0DCA58__vanilla, 5	; modes 0..4 unchanged
	.long	8				; mode 5 (Global): highest page 6 -> 8

.redirect	dat_0C0D333C, newtribe_tbl_edit
.redirect	dat_0C0D355C, newtribe_tbl_leave
.redirect	dat_0C0D3604, newtribe_tbl_enter
.redirect	dat_0C0D36AC, newtribe_tbl_display
.redirect	dat_0C0DCA58, newtribe_tbl_maxpage
