/*
 * Title profiles (fork): the per-title constants that budget.c and
 * hooks.c used to hardcode, in one struct, selectable at boot.
 *
 * The built-in profile below is Ghost of Tsushima CUSA11456 v2.18 —
 * exactly the values the code shipped with, moved, not changed.
 * run.py --title-profile titles/<id>.json sends another title's
 * numbers as a flat u64 array in the boot context (the layout is
 * PROFILE_WORDS in ghost.h, encoded by tools/title_profile.py);
 * profile_select() runs before any module is loaded and either
 * adopts the host profile (validated; anything malformed falls
 * back to the built-in with a log line) or keeps the built-in.
 *
 * Safety does not rest on the profile being right: budget.c still
 * verifies the streaming-pool table's contents in the title's own
 * text before patching, and hooks.c still matches prologues byte
 * for byte.  A wrong profile patches nothing; it just logs.
 */
#include "ghost.h"

static const struct title_profile k_builtin = {
    .tag = 0x3534313141535543ULL, /* "CUSA1145" little-endian */
    .flags = PROFILE_FLAG_BUILTIN_HOOKS,
    .n_knobs = 3,
    .knobs = {
        {0x111ce10, 4, 0, 0},   /* general GPU heap table (TBL_GPU_HEAP) */
        {0x111cde0, 6, 1, 0},   /* type-0 engine heap table (TBL_POOL1) */
        {0x111cd20, 7, 2, 320}, /* CPU malloc heap table (TBL_CPU_HEAP) */
    },
    .stream_tbl = 0x111cd50,
    .stream_pool = {0x46000000, 0x46000000, 0x46000000, 0x84800000, 0x125800000, 0x125800000},
    .fixed_mib = 3946,
    .remainder_mib = 48,
    .slack_mib = 32,
    .lazy_total_mib = 1824, /* 1096 + 612 + 116 */
    .lazy_reserve_mib = 1704,
    .movie_reserve_mib = 100,
    .min_pool_mib = 128,
    .n_lazy = 3,
    .lazy_sites = {0x896126, 0x89614a, 0xeee2cf},
    .heap_obj0 = 0x16b2930,
    .heap_obj1 = 0x16b29f8,
};

static struct title_profile g_host_profile;
const struct title_profile *g_profile = &k_builtin;

/* flat u64 layout (PROFILE_WORDS): see docs/host-tooling.md */
#define W_MAGIC 0
#define W_VERSION 1
#define W_TAG 2
#define W_FLAGS 3
#define W_NKNOBS 4
#define W_STREAM_TBL 5
#define W_STREAM_POOL 6
#define W_KNOBS 12 /* 4 x {table, reserved_idx, name_id, default_mib} */
#define W_FIXED 28
#define W_REMAINDER 29
#define W_SLACK 30
#define W_LAZY_TOTAL 31
#define W_LAZY_RESERVE 32
#define W_MOVIE 33
#define W_MIN_POOL 34
#define W_NLAZY 35
#define W_LAZY 36 /* 8 sites */
#define W_HEAP0 44
#define W_HEAP1 45

static bool mib_ok(u64 v) { return v < 65536; }
static bool off_ok(u64 v) { return v != 0 && v < (1ULL << 32); }

void profile_select(void)
{
    struct boot_ctx *c = g_ctx;
    if (c->size < __builtin_offsetof(struct boot_ctx, profile_len) + 8 || !c->profile_ptr || !c->profile_len) {
        logf("profile: built-in (CUSA11456 v2.18)");
        return;
    }
    if (c->profile_len != PROFILE_WORDS * 8) {
        logf("profile: host profile is %lu bytes, want %u; keeping the built-in", c->profile_len,
             PROFILE_WORDS * 8);
        return;
    }
    const u64 *w = (const u64 *)c->profile_ptr;
    if (w[W_MAGIC] != PROFILE_MAGIC || w[W_VERSION] != PROFILE_VERSION) {
        logf("profile: bad magic/version (%lx/%lu); keeping the built-in", w[W_MAGIC], w[W_VERSION]);
        return;
    }
    struct title_profile *p = &g_host_profile;
    memset(p, 0, sizeof(*p));
    p->tag = w[W_TAG];
    p->flags = (u32)w[W_FLAGS] & PROFILE_FLAG_BUILTIN_HOOKS;
    p->n_knobs = (u32)w[W_NKNOBS];
    p->stream_tbl = w[W_STREAM_TBL];
    for (int i = 0; i < 6; i++)
        p->stream_pool[i] = w[W_STREAM_POOL + i];
    for (u32 i = 0; i < PROFILE_MAX_KNOBS; i++) {
        const u64 *k = w + W_KNOBS + 4 * i;
        p->knobs[i].table = k[0];
        p->knobs[i].reserved_idx = (u32)k[1];
        p->knobs[i].name_id = (u32)k[2];
        p->knobs[i].default_mib = k[3];
    }
    p->fixed_mib = w[W_FIXED];
    p->remainder_mib = w[W_REMAINDER];
    p->slack_mib = w[W_SLACK];
    p->lazy_total_mib = w[W_LAZY_TOTAL];
    p->lazy_reserve_mib = w[W_LAZY_RESERVE];
    p->movie_reserve_mib = w[W_MOVIE];
    p->min_pool_mib = w[W_MIN_POOL];
    p->n_lazy = (u32)w[W_NLAZY];
    for (int i = 0; i < PROFILE_MAX_LAZY; i++)
        p->lazy_sites[i] = w[W_LAZY + i];
    p->heap_obj0 = w[W_HEAP0];
    p->heap_obj1 = w[W_HEAP1];

    bool ok = p->n_knobs <= PROFILE_MAX_KNOBS && p->n_lazy <= PROFILE_MAX_LAZY && off_ok(p->stream_tbl) &&
              mib_ok(p->fixed_mib) && mib_ok(p->remainder_mib) && mib_ok(p->slack_mib) &&
              mib_ok(p->lazy_total_mib) && mib_ok(p->lazy_reserve_mib) && mib_ok(p->movie_reserve_mib) &&
              mib_ok(p->min_pool_mib);
    for (u32 i = 0; ok && i < p->n_knobs; i++)
        ok = off_ok(p->knobs[i].table) && p->knobs[i].reserved_idx >= 4 && p->knobs[i].reserved_idx <= 7 &&
             p->knobs[i].name_id < 8 && mib_ok(p->knobs[i].default_mib);
    for (u32 i = 0; ok && i < p->n_lazy; i++)
        ok = p->lazy_sites[i] < (1ULL << 32);
    if (!ok) {
        logf("profile: host profile failed validation; keeping the built-in");
        return;
    }
    g_profile = p;
    logf("profile: host profile tag %lx flags %u (%u knobs, %u lazy sites)", p->tag, p->flags, p->n_knobs,
         p->n_lazy);
}

bool profile_allows_builtin_hooks(void)
{
    return (g_profile->flags & PROFILE_FLAG_BUILTIN_HOOKS) != 0;
}
