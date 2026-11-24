; Newtribe overlay 3: "Shift Mute" - 9th page of the GLOBAL menu ("ShiftMut", value Off/On, VALUE encoder) and the key hook.
;
; Feature: option On + SHIFT held while a PART key is pressed  ->  the part is only SELECTED, its mute state stays as it is.
; Factory behaviour (measured in the emulator, see README 9.3): the press handlers of the part keys (normal modes) call
;   func_0C0BB0C8(part)   which rewrites the PART MUTE mask word (var_0C17A3A6, bit n = part n muted, bits 0..14) so that the
;                         selected part is un-muted (solo flag var_0C17A3AA set: mask = all other parts muted), through
;   func_0C0BA992(0x1F7, mask, 0, 0, 1)   (generic "set parameter" call, 0x1F7 = PART MUTE).
; Selecting itself (LEDs, selected part var_0C0F09AF, LCD) is done by other calls and stays untouched.
; Hook: the ONE literal pool word lit_0C0BB274 (only func_0C0BB0C8 uses it; it holds the pointer to func_0C0BA992) is replaced
; (.patchlong) by newtribe_mutemask_hook, which swallows exactly that mute-mask call when (option && SHIFT) and otherwise jumps
; on to func_0C0BA992 with all arguments unchanged (also the stack argument), so every other case is byte-for-byte the factory path.
; The mute mode itself (PART MUTE key held + part key, func_0C0BB816) uses another literal and is not touched.
;
; SHIFT: panel key matrix row 0, bit 1 (keymap.json "shift": 0,2).  scan_panel_keys keeps the (active low) port level of
; row 0 in var_0C178694 (idle 0x9F, SHIFT pressed 0x9D) -> pressed = (byte & 2) == 0.
;
; The option is ONE byte in the overlay (SDRAM, written at run time like the image's own variables from 0x0C0E08E8).  It is
; not stored in the settings structure (NVRAM 0xC2D0000): after power-on it is Off again.
; Registers: the hook only uses r0, r1 (volatile), the factory caller (func_0C0BB0C8) does not use them after the call.

SHIFTMUTE_PARAM = 0x1F7			; "PART MUTE" parameter id of func_0C0BA992 (mov #2,r4 / shll8 / add #-9)
shift_row0      = var_0C178694		; port level of key matrix row 0 (bit 1 = SHIFT, 0 = pressed)

lcd_clamp       = func_0C09B734		; r4 = value, r5 = min, r6 = max -> r0
lcd_print_onoff = func_0C0B24EC		; r4 = 0: "Off", else "On" (padded to the value area), printed at the current cursor
lcd_blank       = func_0C0B1C5E		; r4 = number of blanks written at the current cursor
set_param       = func_0C0BA992		; factory: set parameter r4 to r5 (r6/r7 = 0, stack arg 1)

; ---- key hook --------------------------------------------------------------------------------------------------------
newtribe_mutemask_hook:
	mov.w	=SHIFTMUTE_PARAM,r0
	cmp/eq	r0,r4
	bf	newtribe_mutemask_pass		; some other parameter: factory
	mov.l	=newtribe_opt_shiftmute,r1
	mov.b	@r1,r0
	tst	r0,r0
	bt	newtribe_mutemask_pass		; option Off: factory
	mov.l	=shift_row0,r1
	mov.b	@r1,r0
	tst	#2,r0				; T = 1 when SHIFT is pressed (bit cleared)
	bf	newtribe_mutemask_pass		; SHIFT not held: factory
	rts					; option On + SHIFT: do not touch the mute mask (part is only selected)
	nop
newtribe_mutemask_pass:
	mov.l	=set_param,r1
	jmp	@r1
	nop

.patchlong	lit_0C0BB274, newtribe_mutemask_hook, func_0C0BA992

; ---- GLOBAL page 9: "ShiftMut" ------------------------------------------------------------------------------------------
newtribe_page2_display:
	sts.l	pr,@-r15
	mov.l	=lcd_set_cursor,r2
	jsr	@r2
	mov	#0,r4
	mov.l	=newtribe_title2,r4
	mov.l	=lcd_print_str,r2
	jsr	@r2
	nop
	mov.l	=lcd_set_cursor,r2
	jsr	@r2
	mov	#8,r4
	mov.l	=newtribe_opt_shiftmute,r1
	mov.b	@r1,r4
	mov.l	=lcd_print_onoff,r2
	jsr	@r2
	nop
	mov.l	=lcd_blank,r2			; like the factory Global pages: 3 blanks behind "On "/"Off" wipe the rest of the
	mov	#3,r4				; value area (leftovers of the previous page, e.g. "0.0.1")
	jmp	@r2
	lds.l	@r15+,pr			; delay slot: restore pr, the routine returns to our caller

; edit handler: r4 = VALUE encoder delta (signed byte).  Off (0) <-> On (1), clamped like the factory pages.
newtribe_page2_edit:
	mov.l	r14,@-r15
	sts.l	pr,@-r15
	mov.l	=newtribe_opt_shiftmute,r14
	exts.b	r4,r2
	mov.b	@r14,r4
	extu.b	r4,r4
	add	r2,r4
	mov.l	=lcd_clamp,r3
	mov	#1,r6
	jsr	@r3
	mov	#0,r5
	mov.b	r0,@r14
	mov.l	=lcd_set_cursor,r2
	jsr	@r2
	mov	#8,r4
	mov.b	@r14,r4
	mov.l	=lcd_print_onoff,r2
	jsr	@r2
	nop
	lds.l	@r15+,pr
	rts
	mov.l	@r15+,r14
	.pool

newtribe_title2:
	.asciz	"ShiftMut"			; 8 characters = width of the Global page title area
	.align	4

; the option (0 = Off, 1 = On); the overlay is loaded from the BSS at every start-up, so it starts as Off
newtribe_opt_shiftmute:
	.byte	0, 0, 0, 0
