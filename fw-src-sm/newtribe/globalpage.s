; Newtribe overlay 1: 8th page of the GLOBAL menu (read-only, title "Newtrb I", value line = NEWTRIBE_VERSION) and the table
; entries of the 9th page "ShiftMut" (code in shiftmute.s).
;
; How the menu is wired (SDRAM addresses, all measured; see fw-analysis-sm/):
;   menu pages are addressed by idx = mode*7 + page (6 modes x 7 pages = 42 entries; Global = mode 5 = idx 35..41).
;   Four 42-entry function pointer tables are indexed by idx (they are packed back to back in the factory image, so they
;   cannot grow in place and are copied here with one extra entry, idx 42 = Global page 7):
;       dat_0C0D2740 display   dat_0C0D25F0 leave   dat_0C0D2698 enter   dat_0C0D23D0 value edit (encoder)
;   dat_0C0DBAF8 = highest page number per mode {6,4,4,6,6,6} (dword each); Global (index 5) becomes 7.
;   The code that uses these tables loads their addresses from literal pools (`.long dat_...` in src/*.s); `.redirect`
;   makes every such reference point to the copies below, the factory tables stay untouched (as dead data).
; Nothing here touches NVRAM / the settings structure: the page has no edit handler (encoder does nothing) and no state.
;
; Placement: the zero gap 0x0C080648..0x0C080FFF in front of main_entry (the image does not grow, RAM variables from
; 0x0C0ED9F0 are untouched).  tools/build.py additionally verifies that the destination bytes are all zero in the factory image.

NEWTRIBE_GAP_END = 0x0C081000

; factory routines used (names from src/part_0C0B11B4.s)
lcd_set_cursor = func_0C0B1B1C		; r4 = LCD position (0 = start of the title line, 8 = start of the value line)
lcd_print_str  = func_0C0B1D86		; r4 = NUL terminated string, printed at the current position
nop_stub_edit  = func_0C093228		; rts / nop
nop_stub_leave = func_0C093224
nop_stub_enter = func_0C093224

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
	lds.l	@r15+,pr		; delay slot of jmp: restore pr, the print routine returns to our caller
	.pool

newtribe_title:
	.asciz	"Newtrb I"		; 8 characters = width of the Global page title area
	.align	4

; relocated tables: the 42 factory entries are copied from the image, entry 42 is new
newtribe_tbl_edit:
	.copylong	dat_0C0D23D0__vanilla, 42
	.long	nop_stub_edit			; idx 42: "Newtrb I"  (read-only)
	.long	newtribe_page2_edit		; idx 43: "ShiftMut" (shiftmute.s)
newtribe_tbl_leave:
	.copylong	dat_0C0D25F0__vanilla, 42
	.long	nop_stub_leave
	.long	nop_stub_leave
newtribe_tbl_enter:
	.copylong	dat_0C0D2698__vanilla, 42
	.long	nop_stub_enter
	.long	nop_stub_enter
newtribe_tbl_display:
	.copylong	dat_0C0D2740__vanilla, 42
	.long	newtribe_page_display
	.long	newtribe_page2_display
newtribe_tbl_maxpage:
	.copylong	dat_0C0DBAF8__vanilla, 5	; modes 0..4 unchanged
	.long	8				; mode 5 (Global): highest page 6 -> 8 (pages 7 and 8 = overlay)

.redirect	dat_0C0D23D0, newtribe_tbl_edit
.redirect	dat_0C0D25F0, newtribe_tbl_leave
.redirect	dat_0C0D2698, newtribe_tbl_enter
.redirect	dat_0C0D2740, newtribe_tbl_display
.redirect	dat_0C0DBAF8, newtribe_tbl_maxpage
