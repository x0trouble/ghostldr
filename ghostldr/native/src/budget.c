/*
 * Fit the title's memory plan into SWRR's direct memory.
 *
 * The numbers below describe the built-in profile (Ghost CUSA11456
 * v2.18, profile.c); a host-supplied profile replaces them wholesale.
 *
 * Ghost's planner (eboot 0x895b40) reserves every byte of
 * sceKernelGetDirectMemorySize() up front.  In memory mode 0 (base PS4) it
 * needs ~5.07 GiB; SWRR's process has 4.5 GiB, ~4.37 GiB of it free once
 * hostmem.c releases the emulator's buffers.
 *
 * Measured: the type 3 pool at 0x1500000000 (table 0x111ce10) is the general
 * GPU heap (engine heap 0x390d80); boot alone needs ~900 MiB of it, so it
 * keeps its size.  The pool at 0x1200000000 (table 0x111cd50) feeds a paged
 * GPU pool manager and grows 1120 -> 2120 -> 4696 MiB with richer memory
 * modes: the texture streaming pool.  It takes the shortfall.  vdm.c removes
 * the need for physically contiguous blocks, so only the total matters.
 */
#include "ghost.h"

#define MiB (1UL << 20)

/* The built-in profile's mode-0 reservations other than the streaming
 * pool, in MiB: 0x111cd20 384 + 0x111cd80 116 + 0x111cdb0 64, 0x111cde0
 * 332 (type 0 pool), 0x111ce10 1390 (GPU heap), subsystem budgets 1660 —
 * FIXED_MIB 3946 in profile.c.  Its CPU malloc mspace (384 MiB) gives
 * 64 MiB to the streaming pool (the knob's 320 MiB default): at 352 MiB
 * the pool cannot hold core_common's textures and loading stalls; at
 * ~512 MiB the world loads.
 *
 * Reservations the title maps only partly; vdm.c backs them lazily,
 * 2 MiB at a time.  At the loading screen (measured 2026-10-20):
 * planner type-0 heap 927 of 1096 MiB mapped, planner type-3 heap 440
 * of 612, 64 KiB-page GPU pool 56 of 116 — the built-in profile's
 * lazy_total 1824 MiB.  Loading the beach commits 1040 + 606 + 62 MiB
 * of them, its fight takes the 64 KiB-page pool to 100 MiB; with the
 * movie reserve this covers all 1824 MiB and leaves the streaming
 * pool ~590 MiB (550 stalls the beach load) — lazy_reserve 1704. */

bool budget_lazy_site(u64 eboot_off)
{
    for (u32 i = 0; i < g_profile->n_lazy; i++)
        if (g_profile->lazy_sites[i] == eboot_off)
            return true;
    return false;
}

u64 g_reported_dmem;

struct hole {
    u64 s, e;
};
#define MAX_HOLES 96

/* free physical ranges: the complement of the allocated ones */
static u32 free_holes(struct hole *h)
{
    struct {
        off_t start, end;
        int type;
    } q;
    int (*dmq)(off_t, int, void *, size_t) = host_dlsym((u32)g_ctx->libkernel_handle, "sceKernelDirectMemoryQuery");
    u64 real = K.direct_size(), cur = 0, off = 0;
    u32 n = 0;
    for (int i = 0; dmq && i < 512 && n < MAX_HOLES; i++) {
        memset(&q, 0, sizeof(q));
        if (dmq((off_t)off, 1, &q, sizeof(q)) != 0)
            break;
        if ((u64)q.start > cur)
            h[n++] = (struct hole){cur, (u64)q.start};
        cur = off = (u64)q.end;
    }
    if (cur < real && n < MAX_HOLES)
        h[n++] = (struct hole){cur, real};
    return n;
}

static const char *const k_knob_names[] = {"general GPU heap", "type-0 engine heap", "CPU malloc heap"};

void budget_patch_text(struct module *m, u8 *text)
{
    const struct title_profile *prof = g_profile;
    u64 *pool = (u64 *)(text + prof->stream_tbl);
    if (prof->stream_tbl + sizeof(prof->stream_pool) > m->text_size ||
        memcmp(pool, prof->stream_pool, sizeof(prof->stream_pool))) {
        logf("budget: streaming pool table not found; leaving the plan alone");
        return;
    }
    /* experiment knobs (run.py --gpu-heap-mib/--pool1-mib/--cpu-heap-mib):
     * resize the other mode-0 reservations; the streaming pool absorbs it.
     * A knob's profile default applies when its ctx slot is 0. */
    s64 gpu_delta_mib = 0;
    for (u32 i = 0; i < prof->n_knobs; i++) {
        const struct profile_knob *knob = &prof->knobs[i];
        u64 want = g_ctx->reserved[knob->reserved_idx];
        if (!want)
            want = knob->default_mib;
        if (!want)
            continue;
        u64 *t = (u64 *)(text + knob->table);
        gpu_delta_mib += (s64)want - (s64)(t[0] / MiB);
        logf("budget: %s %lu -> %lu MiB",
             knob->name_id < ARRAY_SIZE(k_knob_names) ? k_knob_names[knob->name_id] : "pool table",
             t[0] / MiB, want);
        t[0] = want * MiB;
    }
    u64 slack_mib = g_ctx->reserved[5] ? g_ctx->reserved[5] : prof->slack_mib;
    struct hole free[MAX_HOLES];
    u32 nfree = free_holes(free);
    u64 total = 0;
    for (u32 i = 0; i < nfree; i++) {
        total += free[i].e - free[i].s;
        if (free[i].e - free[i].s >= 16 * MiB)
            logf("budget: free %lx-%lx (%lu MiB)", free[i].s, free[i].e, (free[i].e - free[i].s) / MiB);
    }
    /* the lazily backed reservations (planner heaps = subsystem budgets +
     * remainder, and the 64 KiB-page pool) count with lazy_reserve_mib
     * instead of their full lazy_total_mib */
    s64 pool_mib = (s64)(total / MiB) - (s64)(prof->fixed_mib + 2 + prof->remainder_mib + slack_mib) -
                   gpu_delta_mib + (s64)prof->lazy_total_mib - (s64)prof->lazy_reserve_mib -
                   (s64)prof->movie_reserve_mib;
    if (pool_mib > (s64)(prof->stream_pool[0] / MiB))
        pool_mib = (s64)(prof->stream_pool[0] / MiB);
    if (pool_mib < (s64)prof->min_pool_mib) {
        logf("budget: only %lu MiB free; streaming pool clamped to %lu MiB", total / MiB, prof->min_pool_mib);
        pool_mib = (s64)prof->min_pool_mib;
    }
    pool_mib &= ~1L;
    pool[0] = pool_mib * MiB;
    g_reported_dmem = (u64)((s64)prof->fixed_mib + gpu_delta_mib + pool_mib + 2 + (s64)prof->remainder_mib) * MiB;
    logf("budget: %lu MiB free in %u holes; streaming pool %lu -> %ld MiB; reporting %lu MiB direct memory",
         total / MiB, nfree, prof->stream_pool[0] / MiB, pool_mib, g_reported_dmem / MiB);
}
