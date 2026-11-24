; Newtribe overlay 2 (ESX-1 SD 01.03.01): start-up / loading screen.
;   Physical Korg ESX-1 LCD layout (verified on real hardware & BFS 0x0C0030B8 / 0x0C0B22C2):
;     line 1 (pos 0..7,  8 chars): bold "Newtribe" via CGRAM slots 0..6
;     line 2 (pos 8..13, 6 chars): 2-cell progress bar (slot 7 / '=' / '.') + right-aligned "  0%" .. "100%"
;                                  e.g. "..  0%", "=. 25%", "#. 50%", "#= 75%", "##100%" (fits all 6 visible cells!)
;     line 2 (pos 14..15, 2 icon cells): cleared to spaces "  " at splash start so indicator icons stay dark until handover.
;
; BFS 01.03.01 LCD/delay routines (verified from esx1sd_bfs_512k.bin & ESX0103N.BSS):
;   bfs_func_0C003160(r4 = 8B glyph, r5 = slot)   [was 0x0C002BB0 in 01.02]
;   bfs_func_0C003122(r4 = str, r5 = pos 0..15)   [was 0x0C002B72 in 01.02; 0x0C00328E clamps pos>=14!]
;   bfs_func_0C00C766(r4 = microseconds)          [was 0x0C009B96 in 01.02]

NEWTRIBE_TICK_MS = 20
NEWTRIBE_HOLD_US = 250000

NT_VARS   = var_0C150A94
lcd_cgram = bfs_func_0C003160
lcd_puts  = bfs_func_0C003122
delay_us  = bfs_func_0C00C766

	.align	4

; ---------------------------------------------------------------- entry hook (first call in main_entry)
newtribe_entry:
	sts.l	pr,@-r15
	bsr	newtribe_splash
	nop
	lds.l	@r15+,pr
	mov.l	=func_0C0CD3C8__vanilla,r2
	jmp	@r2
	nop

newtribe_splash:
	sts.l	pr,@-r15
	mov.l	r14,@-r15
	mov.l	r13,@-r15
	mov.l	=newtribe_glyphs,r14
	mov	#0,r13
nt_glyph_loop:
	mov	r14,r4
	mov.l	=lcd_cgram,r2
	jsr	@r2
	mov	r13,r5
	add	#8,r14
	add	#1,r13
	mov	#8,r0
	cmp/eq	r0,r13
	bf	nt_glyph_loop
	mov.l	=newtribe_line1,r4
	mov.l	=lcd_puts,r2
	jsr	@r2
	mov	#0,r5
	mov.l	=newtribe_blank2,r4	; keep the 2 icon cells (pos 14..15) blank during splash
	mov.l	=lcd_puts,r2
	jsr	@r2
	mov	#14,r5
	bsr	newtribe_draw
	mov	#0,r4
	mov.l	@r15+,r13
	mov.l	@r15+,r14
	lds.l	@r15+,pr
	rts
	nop
	.pool

; ---------------------------------------------------------------- draw 6-char line 2 (pos 8..13) for percent r4 (0..100)
; Format: 2-cell bar + right-aligned "  0%" .. "100%" = 6 chars total: "..  0%", "=. 25%", "#. 50%", "#= 75%", "##100%"
newtribe_draw:
	sts.l	pr,@-r15
	add	#-12,r15
	mov	r4,r1
	mov.w	=164,r2			; floor(p * 4 / 100) = (p * 164) >> 12 (exact for all p = 0..100 -> 0..4 half-cells)
	mulu.w	r2,r4
	sts	macl,r0
	shlr8	r0
	shlr2	r0
	shlr2	r0
	mov	r0,r3
	mov	r15,r5
	mov	#2,r6			; 2 bar cells (pos 8..9)
	mov	#2,r7
nt_cell:
	cmp/ge	r7,r3
	bt	nt_cell_full
	mov	#46,r2			; '.'
	mov	r7,r0
	add	#-1,r0
	cmp/eq	r0,r3
	bf	nt_cell_store
	bra	nt_cell_store
	mov	#61,r2			; '='
nt_cell_full:
	mov	#15,r2			; CGRAM slot 7 = solid block
nt_cell_store:
	mov.b	r2,@r5
	add	#1,r5
	add	#2,r7
	dt	r6
	bf	nt_cell
	mov	r1,r7
	mov	#0,r6
nt_tens:
	mov	#10,r0
	cmp/ge	r0,r7
	bf	nt_tens_done
	add	#-10,r7
	bra	nt_tens
	add	#1,r6
nt_tens_done:
	mov	#32,r2
	cmp/ge	r0,r6
	bf	nt_no_hund
	mov	#49,r2
	add	#-10,r6
nt_no_hund:
	mov.b	r2,@r5
	add	#1,r5
	mov	#32,r3
	cmp/ge	r0,r1
	bf	nt_no_tens
	mov	r6,r3
	add	#48,r3
nt_no_tens:
	mov.b	r3,@r5
	add	#1,r5
	mov	r7,r3
	add	#48,r3
	mov.b	r3,@r5
	add	#1,r5
	mov	#37,r3			; '%'
	mov.b	r3,@r5
	add	#1,r5
	mov	#0,r3
	mov.b	r3,@r5
	mov	r15,r4
	mov.l	=lcd_puts,r2
	jsr	@r2
	mov	#8,r5
	add	#12,r15
	lds.l	@r15+,pr
	rts
	nop
	.pool

; ---------------------------------------------------------------- tick (cyclic handler)
newtribe_tick:
	mov.l	=NT_VARS,r2
	mov.b	@(3,r2),r0
	tst	#1,r0
	bf	nt_tick_ret
	tst	#4,r0
	bt	nt_tick_go
	and	#0xFB,r0
	mov.b	r0,@(3,r2)
nt_tick_ret:
	rts
	nop
nt_tick_go:
	mov.b	@(4,r2),r0
	add	#1,r0
	mov.b	r0,@(4,r2)
	mov	r0,r1
	mov.b	@r2,r3
	mov.b	@(2,r2),r0
	cmp/ge	r0,r3
	bt	nt_tick_nogrow
	; Smooth pacing across real-hardware boot (no stall at 24% during NAND sample load):
	;   cur < 30:  step every 2 ticks ( 40 ms / 1%)  -> 5..30% in 1.0 s
	;   cur < 75:  step every 4 ticks ( 80 ms / 1%)  -> 30..75% in 3.6 s
	;   cur >= 75: step every 8 ticks (160 ms / 1%)  -> 75..94% in 3.0 s
	mov	#30,r0
	cmp/ge	r0,r3
	bt	nt_tick_mid
	bra	nt_tick_mask
	mov	#1,r0
nt_tick_mid:
	mov	#75,r0
	cmp/ge	r0,r3
	bt	nt_tick_slow
	bra	nt_tick_mask
	mov	#3,r0
nt_tick_slow:
	mov	#7,r0
nt_tick_mask:
	tst	r0,r1
	bf	nt_tick_nogrow
nt_tick_step:
	add	#1,r3
	mov.b	r3,@r2
nt_tick_nogrow:
	mov.b	@(1,r2),r0
	cmp/eq	r0,r3
	bt	nt_tick_ret
	mov	r3,r0
	mov.b	r0,@(1,r2)
	sts.l	pr,@-r15
	bsr	newtribe_draw
	mov	r3,r4
	lds.l	@r15+,pr
	rts
	nop

; ---------------------------------------------------------------- stage events
newtribe_anim:
	mov	r4,r0
	add	#1,r0
	mov	#3,r1
	cmp/hi	r1,r0
	bt	nt_anim_ret
	shll	r0
	mov.l	=nt_stage_tbl,r1
	mov.b	@(r0,r1),r3
	add	#1,r0
	mov.b	@(r0,r1),r5
	mov.l	=NT_VARS,r2
	mov.b	@r2,r6
	cmp/ge	r3,r6
	bt	nt_anim_cap
	mov.b	r3,@r2
nt_anim_cap:
	mov	r5,r0
	mov.b	r0,@(2,r2)
	mov	#2,r0
	cmp/eq	r0,r4
	bf	nt_anim_ret
	mov.b	@(3,r2),r0
	or	#4,r0
	mov.b	r0,@(3,r2)
nt_anim_ret:
	rts
	nop

nt_stage_tbl:
	.byte	1, 4, 5, 92, 5, 92, 75, 96

newtribe_check:
	sts.l	pr,@-r15
	mov.l	=func_0C0C8054__vanilla,r2
	jsr	@r2
	nop
	mov	r0,r7
	mov.l	=NT_VARS,r2
	mov.b	@r2,r3
	mov	#60,r1
	cmp/ge	r1,r3
	bt	nt_chk_cap
	mov.b	r1,@r2
nt_chk_cap:
	mov	#94,r1
	mov.b	@(2,r2),r0
	cmp/ge	r1,r0
	bt	nt_chk_done
	mov	r1,r0
	mov.b	r0,@(2,r2)
nt_chk_done:
	mov	r7,r0
	lds.l	@r15+,pr
	rts
	nop
	.pool

newtribe_dsperr:
	mov.l	=NT_VARS,r2
	mov.b	@(3,r2),r0
	or	#3,r0
	mov.b	r0,@(3,r2)
	sts.l	pr,@-r15
	mov.l	r14,@-r15
	mov.l	r13,@-r15
	mov.l	=newtribe_zero8,r14
	mov	#0,r13
nt_err_loop:
	mov	r14,r4
	mov.l	=lcd_cgram,r2
	jsr	@r2
	mov	r13,r5
	add	#1,r13
	mov	#8,r0
	cmp/eq	r0,r13
	bf	nt_err_loop
	mov.l	=newtribe_blank2,r4
	mov.l	=lcd_puts,r2
	jsr	@r2
	mov	#14,r5
	mov.l	@r15+,r13
	mov.l	@r15+,r14
	lds.l	@r15+,pr
	mov.l	=func_0C0B2BAC__vanilla,r2
	jmp	@r2
	nop

newtribe_finish:
	sts.l	pr,@-r15
	mov.l	=NT_VARS,r2
	mov.b	@(3,r2),r0
	tst	#2,r0
	or	#1,r0
	mov.b	r0,@(3,r2)
	bf	nt_fin_end
	mov	#100,r0
	mov.b	r0,@r2
	mov.b	r0,@(1,r2)
	bsr	newtribe_draw
	mov	#100,r4
	mov.l	=NEWTRIBE_HOLD_US,r4
	mov.l	=delay_us,r2
	jsr	@r2
	nop
	mov.l	=newtribe_blank2,r4
	mov.l	=lcd_puts,r2
	jsr	@r2
	mov	#14,r5
nt_fin_end:
	lds.l	@r15+,pr
	mov.l	=func_0C0B2C1A__vanilla,r2
	jmp	@r2
	nop

newtribe_nop:
	rts
	nop
	.pool

; ---------------------------------------------------------------- data
	.align	4
newtribe_tick_desc:
	.long	0
	.long	0
	.long	0x0C0CD3C2		; task 3 cyclic wrapper: mov.l @(0x0C0CD408,pc),r2; jmp @r2; nop -> func_0C0B2B36
	.long	NEWTRIBE_TICK_MS
	.long	1

newtribe_zero8:
	.long	0, 0
newtribe_blank2:
	.asciz	"  "
	.align	4

newtribe_line1:
	.byte	8, 9, 10, 11, 12, 13, 14, 9, 0
	.align	4

newtribe_glyphs:
	.byte	0x19, 0x1D, 0x1D, 0x1F, 0x17, 0x17, 0x13, 0x00	; slot 0  N
	.byte	0x00, 0x00, 0x0E, 0x1B, 0x1F, 0x18, 0x0E, 0x00	; slot 1  e
	.byte	0x00, 0x00, 0x1B, 0x1B, 0x15, 0x1F, 0x0A, 0x00	; slot 2  w
	.byte	0x0C, 0x0C, 0x1F, 0x0C, 0x0C, 0x0C, 0x07, 0x00	; slot 3  t
	.byte	0x00, 0x00, 0x1B, 0x1D, 0x18, 0x18, 0x18, 0x00	; slot 4  r
	.byte	0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x0C, 0x0C, 0x00	; slot 5  i
	.byte	0x18, 0x18, 0x1E, 0x1B, 0x1B, 0x1B, 0x1E, 0x00	; slot 6  b
	.byte	0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x00	; slot 7  solid block

.redirect	func_0C0CD3C8, newtribe_entry
.redirect	func_0C0B2AF0, newtribe_nop
.redirect	func_0C0B2A98, newtribe_anim
.redirect	func_0C0C8054, newtribe_check
.redirect	func_0C0B2B36, newtribe_tick
.redirect	dat_0C0E1830, newtribe_tick_desc
.redirect	func_0C0B2BAC, newtribe_dsperr
.redirect	str_0C0E12E8, newtribe_line1
.redirect	func_0C0B2C1A, newtribe_finish
