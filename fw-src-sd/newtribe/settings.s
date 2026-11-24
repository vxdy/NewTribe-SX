; Newtribe persistent custom settings (ESX-1 SD 01.03.01)
;
; Stored in the 8 verified-unused bytes 0x0C2D0058..0x0C2D005F inside the 64-byte Global Settings block
; (see fw-src-sm/SETTINGS_FORMAT.md Section 6; verified 0 references in 01.03.01 and all 0x00 in real NAND).
;
; Layout (8 bytes at NT_CFG_BASE = 0x0C2D0058):
;   +0  0x4E ('N')    magic byte 0
;   +1  0x54 ('T')    magic byte 1
;   +2  0x01          schema version
;   +3  flags0        bitfield of up to 8 On/Off custom options:
;                       bit 0 (0x01) = ShiftMut (0 = Off, 1 = On)
;                       bits 1..7    = reserved (0)
;   +4..+7            4 reserved bytes (0x00) for future multi-value custom settings
;
; Persistence:
;   - Loaded automatically at boot by factory global_load (0x0C0B927A -> NAND 0x2FC000, 512 B -> 0x0C2D0000).
;   - Saved automatically via standard GLOBAL -> WRITE -> GloblWr? Yes (0x0C0B9260 -> NAND page 0x5F8).
;   - Preserved in .ESX/.PSG SD card saves (lies within the 224-byte preserved prefix 0x00..0xDF).
;   - Safe against uninitialized NAND (0xFF) or stock Global blocks (0x00): invalid magic always reads as 0 (Off).

NT_CFG_BASE    = 0x0C2D0058
NT_CFG_MAGIC0  = 0x4E			; 'N'
NT_CFG_MAGIC1  = 0x54			; 'T'
NT_CFG_VER     = 0x01

NT_FLAG_SHIFTMUTE = 0x01		; bit 0 of flags0 (+3)

	.align	4

; ---------------------------------------------------------------- nt_get_flag(r4 = bitmask) -> r0 (0 or 1)
; Clobbers ONLY r0, r1 (safe to call from hooks that preserve r4..r7).
nt_get_flag:
	mov.l	=NT_CFG_BASE,r1
	mov.b	@r1,r0
	cmp/eq	#NT_CFG_MAGIC0,r0
	bf	nt_gf_zero
	mov.b	@(1,r1),r0
	cmp/eq	#NT_CFG_MAGIC1,r0
	bf	nt_gf_zero
	mov.b	@(2,r1),r0
	cmp/eq	#NT_CFG_VER,r0
	bf	nt_gf_zero
	mov.b	@(3,r1),r0
	tst	r4,r0
	bt	nt_gf_zero
	rts
	mov	#1,r0
nt_gf_zero:
	rts
	mov	#0,r0

; ---------------------------------------------------------------- nt_set_flag(r4 = bitmask, r5 = 0|1)
; Ensures magic/version header is initialized (zeroing reserved bytes on first use), then updates flags0.
; Clobbers r0..r3.
nt_set_flag:
	mov.l	=NT_CFG_BASE,r1
	mov.b	@r1,r0
	cmp/eq	#NT_CFG_MAGIC0,r0
	bf	nt_sf_init
	mov.b	@(1,r1),r0
	cmp/eq	#NT_CFG_MAGIC1,r0
	bf	nt_sf_init
	mov.b	@(2,r1),r0
	cmp/eq	#NT_CFG_VER,r0
	bt	nt_sf_upd
nt_sf_init:
	mov	#NT_CFG_MAGIC0,r0
	mov.b	r0,@r1
	mov	#NT_CFG_MAGIC1,r0
	mov.b	r0,@(1,r1)
	mov	#NT_CFG_VER,r0
	mov.b	r0,@(2,r1)
	mov	#0,r0
	mov.b	r0,@(3,r1)
	mov.b	r0,@(4,r1)
	mov.b	r0,@(5,r1)
	mov.b	r0,@(6,r1)
	mov.b	r0,@(7,r1)
nt_sf_upd:
	mov.b	@(3,r1),r0
	tst	r5,r5
	bt	nt_sf_clr
	or	r4,r0
	bra	nt_sf_store
	nop
nt_sf_clr:
	not	r4,r2
	and	r2,r0
nt_sf_store:
	mov.b	r0,@(3,r1)
	rts
	nop
	.pool
