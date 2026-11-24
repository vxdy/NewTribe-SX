; Newtribe overlay 3 (ESX-1 SD 01.03.01): "Shift Mute" - 9th page of GLOBAL ("ShiftMut", Off/On) + key hook.
;
; Persistence: stored in NT_CFG_BASE (0x0C2D0058..0x0C2D005F, bit 0 of flags0 = NT_FLAG_SHIFTMUTE) via settings.s.
; Saved permanently to internal NAND via standard GLOBAL -> WRITE (GloblWr? -> Yes) and reloaded at every boot.
;
; All addresses verified against factory-firmware-sd/ESX0103N.BSS (see sd-dump/BOOTLOADER_UND_DIFF.md).

SHIFTMUTE_PARAM = 0x1F7
shift_row0      = var_0C179E58

lcd_clamp       = func_0C09B818
lcd_print_onoff = func_0C0B2580
lcd_blank       = func_0C0B1CF2
set_param       = func_0C0BAA46

; ---- key hook --------------------------------------------------------------------------------------------------------
newtribe_mutemask_hook:
	mov.w	=SHIFTMUTE_PARAM,r0
	cmp/eq	r0,r4
	bf	newtribe_mutemask_pass
	sts.l	pr,@-r15
	mov.l	r4,@-r15
	mov.l	=nt_get_flag,r1
	jsr	@r1
	mov	#NT_FLAG_SHIFTMUTE,r4
	mov.l	@r15+,r4
	lds.l	@r15+,pr
	tst	r0,r0
	bt	newtribe_mutemask_pass
	mov.l	=shift_row0,r1
	mov.b	@r1,r0
	tst	#2,r0
	bf	newtribe_mutemask_pass
	rts
	nop
newtribe_mutemask_pass:
	mov.l	=set_param,r1
	jmp	@r1
	nop

.patchlong	lit_0C0BB328, newtribe_mutemask_hook, func_0C0BAA46

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
	mov.l	=nt_get_flag,r2
	jsr	@r2
	mov	#NT_FLAG_SHIFTMUTE,r4
	mov	r0,r4
	mov.l	=lcd_print_onoff,r2
	jsr	@r2
	nop
	mov.l	=lcd_blank,r2
	mov	#3,r4
	jmp	@r2
	lds.l	@r15+,pr

newtribe_page2_edit:
	mov.l	r14,@-r15
	sts.l	pr,@-r15
	exts.b	r4,r14
	mov.l	=nt_get_flag,r2
	jsr	@r2
	mov	#NT_FLAG_SHIFTMUTE,r4
	mov	r0,r4
	add	r14,r4
	mov.l	=lcd_clamp,r3
	mov	#1,r6
	jsr	@r3
	mov	#0,r5
	mov	r0,r14
	mov.l	=nt_set_flag,r2
	mov	#NT_FLAG_SHIFTMUTE,r4
	jsr	@r2
	mov	r14,r5
	mov.l	=lcd_set_cursor,r2
	jsr	@r2
	mov	#8,r4
	mov	r14,r4
	mov.l	=lcd_print_onoff,r2
	jsr	@r2
	nop
	lds.l	@r15+,pr
	rts
	mov.l	@r15+,r14
	.pool

newtribe_title2:
	.asciz	"ShiftMut"
	.align	4
