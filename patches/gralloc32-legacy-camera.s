/* Pinned ARMv7 ROM library: only legacy 10-bit camera PRIVATE / P010 usage.
 * Branch targets are virtual addresses, unchanged by the RX file relocation.
 */
.syntax unified
.thumb
.arch armv7-a
.text
.org 0x7d8c
    b.w format_stub
format_resume:
.org 0xabe0
format_stub:
    cmp r2, #34
    bne format_original
    tst.w r4, #0x40000000
    beq format_original
    tst.w r4, #0x20000
    beq format_original
    movw r0, #0xc0a
    movt r0, #0x7fa3
    add sp, #8
    pop {r4, pc}
format_original:
    movw r0, #0xc04
    b.w format_resume
