; Newtribe overlay 2: start-up / loading screen.
;
;   line 1 :  "Newtribe" in BOLD (HD44780 has no bold font: the 7 distinct letters N,e,w,t,r,i,b are programmed as thick-stroke
;             5x7 glyphs into CGRAM slots 0..6, the 'e' is used twice, slot 7 is the solid block of the progress bar)
;   line 2 :  4 cell progress bar (solid block / '=' half cell / '.' empty, 12.5 % per half cell) + right aligned "  0%" .. "100%"
;
; Factory behaviour that this replaces (measured in the emulator, see README 9.2): the boot flash (BFS) shows NOTHING on the LCD in the
; normal boot (it only initialises the controller); the BSS then shows the 4 big KORG letters (CGRAM slots 2..5) on line 1 and the
; marquee "ELECTRIBE SX" on line 2 (func_0C0B2A5C + task 3 "tick" func_0C0B2AA2, period 300 ms), prints "Recovery" on line 1 while the
; sample memory recovery runs, and finally (func_0C0B2B86) clears the display, reloads CGRAM slots 2..7 (arrows) and 0/1 (meter, 0x80)
; before the pattern screen appears.  Because the firmware itself rewrites ALL eight CGRAM slots in func_0C0B2B86, nothing has to be
; restored here: our glyphs live only until that call.
;
; Hooks (all by .redirect, i.e. only literal pool words change, no generated code is touched):
;   func_0C0CC4EC  first call in main_entry (BSS clear)   -> newtribe_entry   : programs CGRAM, draws "Newtribe" + 0 %   (earliest point)
;   func_0C0B2A5C  factory KORG logo splash                -> newtribe_nop     : removed
;   func_0C0B2A04  animation mode set (-1,0,1,2)           -> newtribe_anim    : boot STAGE event  (floor/cap of the progress, see table)
;   func_0C0C71C8  sample memory check (returns r0)        -> newtribe_check   : stage event "check finished"
;   func_0C0B2AA2  task 3 tick (cyclic handler, ISR level) -> newtribe_tick    : progress +1 per tick (<= cap), redraw on change
;   dat_0C0E0894   descriptor of that cyclic handler       -> newtribe_tick_desc : same, period 300 ms -> NEWTRIBE_TICK_MS
;   func_0C0B2B18  "DSP Ver./Error" screen                 -> newtribe_dsperr  : stop drawing so that the error text stays visible
;   str_0C0E034C   "Recovery" (printed on line 1)          -> newtribe_line1   : the same bold "Newtribe" (line 1 is never overwritten)
;   func_0C0B2B86  end of the splash                       -> newtribe_finish  : 100 %, hold NEWTRIBE_HOLD_US, then the factory routine
;
; Progress = real boot stages + 1 % per tick between them (a stage can never run ahead of its cap):
;   event                     p >=   cap      (real position in main task func_0C0CBB12)
;   main_entry (BSS clear)       0     0      power on, BSS entered
;   anim(-1)  task start         1     4
;   anim(0)   init sequence      5    24      func_0C09EB5C ... func_0C0ADC8A
;   check finished              30    39      func_0C0C71C8 returned (normal boot continues directly to the end)
;   anim(2)   RECOVERY          40    94      factory "Recovery"/"Wait.." (sample memory recovery, 125 M instructions in the emulator)
;   finish                     100           func_0C0B2B86
;
; RAM state: 5 bytes at var_0C14F6E8 (only the factory animation used it, the two factory users are replaced here; BSS clear zeroes it):
;   +0 p (0..100, shown)   +1 drawn (last value on the LCD)   +2 cap   +3 flags: bit0 stop drawing, bit1 DSP error screen, bit2 skip next tick
;   +4 tick counter
; LCD access: only the BFS routines the factory splash uses itself:
;   bfs_func_0C002BB0(r4 = 8 byte glyph, r5 = slot)   bfs_func_0C002B72(r4 = NUL string, r5 = position 0..15, 8 = start of line 2)
;   bfs_func_0C009B96(r4 = microseconds)
; Concurrency: only the tick (timer handler) draws while the system runs; the entry draw is before the OS exists and the final draw is after
; the tick was stopped / flagged (flags bit0), so two LCD transfers never interleave.

NEWTRIBE_TICK_MS = 20		; period of the progress tick (factory marquee: 300)
NEWTRIBE_HOLD_US = 60000 	; minimum display time of "100%" before the factory hand-over routine clears the screen

NT_VARS = var_0C14F6E8
lcd_cgram = bfs_func_0C002BB0
lcd_puts  = bfs_func_0C002B72
delay_us  = bfs_func_0C009B96

	.align	4

; ---------------------------------------------------------------- entry hook (first thing in main_entry)
newtribe_entry:
	sts.l	pr,@-r15
	bsr	newtribe_splash
	nop
	lds.l	@r15+,pr
	mov.l	=func_0C0CC4EC__vanilla,r2
	jmp	@r2			; the factory BSS clear returns to main_entry
	nop

; program the glyphs, show "Newtribe" and the 0 % line
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
	mov	r13,r5			; slot
	add	#8,r14
	add	#1,r13
	mov	#8,r0
	cmp/eq	r0,r13
	bf	nt_glyph_loop
	mov.l	=newtribe_line1,r4
	mov.l	=lcd_puts,r2
	jsr	@r2
	mov	#0,r5
	bsr	newtribe_draw
	mov	#0,r4
	mov.l	@r15+,r13
	mov.l	@r15+,r14
	lds.l	@r15+,pr
	rts
	nop
	.pool

; ---------------------------------------------------------------- draw line 2 for percent r4 (0..100); clobbers r0-r7
newtribe_draw:
	sts.l	pr,@-r15
	add	#-12,r15		; 9 byte line buffer at r15
	mov	r4,r1			; r1 = p
	mov.w	=328,r2
	mulu.w	r2,r4
	sts	macl,r0
	shlr8	r0
	shlr2	r0
	shlr2	r0			; h = p*328 >> 12 = floor(p*8/100) = half cells 0..8
	mov	r0,r3
	mov	r15,r5
	mov	#4,r6			; 4 bar cells
	mov	#2,r7			; r7 = h needed for a full cell
nt_cell:
	cmp/ge	r7,r3
	bt	nt_cell_full
	mov	#46,r2			; '.'
	mov	r7,r0
	add	#-1,r0
	cmp/eq	r0,r3
	bf	nt_cell_store
	bra	nt_cell_store
	mov	#61,r2			; '=' (half cell), delay slot
nt_cell_full:
	mov	#15,r2			; CGRAM slot 7 = solid block
nt_cell_store:
	mov.b	r2,@r5
	add	#1,r5
	add	#2,r7
	dt	r6
	bf	nt_cell
	; digits: r6 = tens count, r7 = units
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
	mov	#32,r2			; hundreds char
	cmp/ge	r0,r6			; r0 is still 10 : tens count >= 10  <=>  p = 100
	bf	nt_no_hund
	mov	#49,r2			; '1'
	add	#-10,r6
nt_no_hund:
	mov.b	r2,@r5			; r5 = line buffer + 4
	add	#1,r5
	mov	#32,r3			; tens char: blank below 10 %
	cmp/ge	r0,r1			; p >= 10
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
	mov	#8,r5			; start of line 2
	add	#12,r15
	lds.l	@r15+,pr
	rts
	nop
	.pool

; ---------------------------------------------------------------- tick (cyclic handler, replaces the factory marquee)
newtribe_tick:
	mov.l	=NT_VARS,r2
	mov.b	@(3,r2),r0
	tst	#1,r0
	bf	nt_tick_ret		; stopped
	tst	#4,r0
	bt	nt_tick_go
	and	#0xFB,r0		; skip this tick once (the main task prints right now)
	mov.b	r0,@(3,r2)
nt_tick_ret:
	rts
	nop
nt_tick_go:
	mov.b	@(4,r2),r0
	add	#1,r0
	mov.b	r0,@(4,r2)		; tick counter
	mov	r0,r1
	mov.b	@r2,r3			; p
	mov.b	@(2,r2),r0		; cap
	cmp/ge	r0,r3
	bt	nt_tick_nogrow		; at the cap: wait for the next stage event
	sub	r3,r0			; r0 = cap - p
	mov	#12,r5
	cmp/ge	r5,r0
	bt	nt_tick_step		; far from the cap: +1 per tick
	mov	#3,r0
	tst	r0,r1
	bf	nt_tick_nogrow		; last 12 %: only every 4th tick (the bar slows down instead of stalling)
nt_tick_step:
	add	#1,r3
	mov.b	r3,@r2
nt_tick_nogrow:
	mov.b	@(1,r2),r0		; drawn
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
; replaces func_0C0B2A04 (r4 = -1, 0, 1, 2): p = max(p, floor), cap = new cap; mode 2 (recovery) also skips the next tick
newtribe_anim:
	mov	r4,r0
	add	#1,r0
	mov	#3,r1
	cmp/hi	r1,r0
	bt	nt_anim_ret
	shll	r0
	mov.l	=nt_stage_tbl,r1
	mov.b	@(r0,r1),r3		; floor
	add	#1,r0
	mov.b	@(r0,r1),r5		; cap
	mov.l	=NT_VARS,r2
	mov.b	@r2,r6			; p
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

nt_stage_tbl:				; floor, cap for anim(-1), anim(0), anim(1), anim(2)
	.byte	1, 4, 5, 24, 5, 24, 40, 94

; replaces func_0C0C71C8 (returns r0): after the sample memory check
newtribe_check:
	sts.l	pr,@-r15
	mov.l	=func_0C0C71C8__vanilla,r2
	jsr	@r2
	nop
	mov	r0,r7			; keep the result
	mov.l	=NT_VARS,r2
	mov.b	@r2,r3
	mov	#30,r1
	cmp/ge	r1,r3
	bt	nt_chk_cap
	mov.b	r1,@r2
nt_chk_cap:
	mov	#39,r1
	mov.b	@(2,r2),r0
	cmp/ge	r1,r0			; do not lower a higher cap
	bt	nt_chk_done
	mov	r1,r0
	mov.b	r0,@(2,r2)
nt_chk_done:
	mov	r7,r0
	lds.l	@r15+,pr
	rts
	nop
	.pool

; replaces func_0C0B2B18 (DSP error screen): stop drawing, restore the CGRAM state of that path (all zero: the error text uses the codes
; 0..15) and blank the two right cells of line 2, then let the factory error text appear
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
	mov.l	=func_0C0B2B18__vanilla,r2
	jmp	@r2
	nop

; replaces func_0C0B2B86 (end of splash, called after the tick was stopped): 100 %, short hold, then the factory routine
; (clears the display and reloads all CGRAM slots with the factory glyphs)
newtribe_finish:
	sts.l	pr,@-r15
	mov.l	=NT_VARS,r2
	mov.b	@(3,r2),r0
	tst	#2,r0
	or	#1,r0
	mov.b	r0,@(3,r2)
	bf	nt_fin_end		; T = 0 when the DSP error screen is up
	mov	#100,r0
	mov.b	r0,@r2
	mov.b	r0,@(1,r2)
	bsr	newtribe_draw
	mov	#100,r4
	mov.l	=NEWTRIBE_HOLD_US,r4
	mov.l	=delay_us,r2
	jsr	@r2
	nop
	mov.l	=newtribe_blank2,r4	; blank the percent's last two cells now: the factory routine only clears cells 0..5 of line 2
	mov.l	=lcd_puts,r2
	jsr	@r2
	mov	#14,r5
nt_fin_end:
	lds.l	@r15+,pr
	mov.l	=func_0C0B2B86__vanilla,r2
	jmp	@r2
	nop

newtribe_nop:				; replaces the factory KORG logo routine func_0C0B2A5C
	rts
	nop
	.pool

; ---------------------------------------------------------------- data
	.align	4
newtribe_tick_desc:			; copy of the cyclic handler descriptor dat_0C0E0894 {0, 0, handler, period [ms], 1} with a shorter period
	.long	0
	.long	0
	.long	func_0C0CC4E6
	.long	NEWTRIBE_TICK_MS
	.long	1

newtribe_zero8:
	.long	0, 0
newtribe_blank2:
	.asciz	"  "
	.align	4

newtribe_line1:				; "Newtribe": codes 8..15 show CGRAM slots 0..7 (the HD44780 mirrors 0..7 at 8..15; 0 would end the string)
	.byte	8, 9, 10, 11, 12, 13, 14, 9, 0	; N e w t r i b e
	.align	4

; the glyphs (5 x 7 used, row 7 empty), 2 pixel strokes:
newtribe_glyphs:
	.byte	0x19, 0x1D, 0x1D, 0x1F, 0x17, 0x17, 0x13, 0x00	; slot 0  N
	.byte	0x00, 0x00, 0x0E, 0x1B, 0x1F, 0x18, 0x0E, 0x00	; slot 1  e
	.byte	0x00, 0x00, 0x1B, 0x1B, 0x15, 0x1F, 0x0A, 0x00	; slot 2  w
	.byte	0x0C, 0x0C, 0x1F, 0x0C, 0x0C, 0x0C, 0x07, 0x00	; slot 3  t
	.byte	0x00, 0x00, 0x1B, 0x1D, 0x18, 0x18, 0x18, 0x00	; slot 4  r
	.byte	0x0C, 0x0C, 0x00, 0x0C, 0x0C, 0x0C, 0x0C, 0x00	; slot 5  i
	.byte	0x18, 0x18, 0x1E, 0x1B, 0x1B, 0x1B, 0x1E, 0x00	; slot 6  b
	.byte	0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x00	; slot 7  solid block (progress bar)

.redirect	func_0C0CC4EC, newtribe_entry
.redirect	func_0C0B2A5C, newtribe_nop
.redirect	func_0C0B2A04, newtribe_anim
.redirect	func_0C0C71C8, newtribe_check
.redirect	func_0C0B2AA2, newtribe_tick
.redirect	dat_0C0E0894, newtribe_tick_desc
.redirect	func_0C0B2B18, newtribe_dsperr
.redirect	str_0C0E034C, newtribe_line1
.redirect	func_0C0B2B86, newtribe_finish
