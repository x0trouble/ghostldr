/*
 * Read access to the title's virtual save data, for the save data dialog
 * (libSceSaveDataDialog is virtual too: the real one would list SWRR's own
 * saves).  Implemented by the save data family (ext/src/hle_savedata.c).
 *
 * The dialog answers from what these report: a LIST dialog shows the
 * title's dirNames that sd_exists, focuses one by sd_mtime, and a chosen
 * save's result carries its dirName and SceSaveDataParam from sd_get_param.
 *
 * All of them read the catalogue of the title's saves (<prefix>SAVE/catalog.bin
 * on a stock console, <save root>/<user>/catalog.bin on a dev install).  The
 * first call for a user may mount <prefix>SAVE (~100 ms); later ones are
 * answered from memory.  They serialise with the title's own save calls and
 * work whether or not the title initialised libSceSaveData.  user < 0 means
 * the user who started SWRR (the initial user), which is also every title's
 * normal user.  Save data memory (sceSaveDataSetupSaveDataMemory2) is not a
 * save directory and is never listed, like on a PS4.
 */
#pragma once
#include "ghost.h"

/* SceSaveDataParam, 0x530 bytes */
struct sd_param {
    char title[128];
    char sub_title[128];
    char detail[1024];
    u32 user_param;
    u32 reserved0;
    s64 mtime; /* seconds since 1970, set at the last commit or SetParam */
    u8 reserved[32];
};

/* one save directory of the title */
struct sd_save_info {
    char dir[32];     /* SceSaveDataDirName: NUL-padded */
    u64 blocks;       /* the title's size in 32 KiB blocks */
    u64 free_blocks;  /* at its last read/write unmount */
    s64 mtime;
    u32 user_param;
    u32 has_icon;
};

/* Up to max saves of user, in the order they were created; returns how many
 * the user has (may exceed max), or a negative SCE_SAVE_DATA_ERROR_*. */
s32 sd_list(s32 user, struct sd_save_info *out, u32 max);

/* The title's save directory dir (char[32], NUL-terminated or full) of the
 * initial user: whether it exists, its param (0 or 0x809F0008 NOT_FOUND),
 * its mtime (-1 if missing).  The names dialogs.md proposed. */
bool sd_exists(const char *dir);
s32 sd_get_param(const char *dir, struct sd_param *out);
s64 sd_mtime(const char *dir);

/* Everything about one save (savedata.md §6.11): any of param
 * (SceSaveDataParam *), icon (SceSaveDataIcon *: buf and bufSize in,
 * dataSize out; 0 when there is no icon) and info (SceSaveDataSearchInfo *:
 * blocks, freeBlocks) may be NULL.  Returns 0, 0x809F0008 (NOT_FOUND) or
 * another SCE_SAVE_DATA_ERROR_*. */
s32 savedata_query(s32 user, const char *dir, struct sd_param *param, void *icon, void *info);

/* ---- other titles' saves, through the real save service (hle_savedata.c) ----
 * For the VSH save-mount stand-in (hle_fsvsh.c).  Never the host's own title.
 * tid is a 9-character title ID; dir a save directory name. */

/* Mount tid's save dir read-only, passing fp (that title's fingerprint: 64
 * lower-case hex characters) as a PS4 game may; mp gets the title-visible
 * "/savedataN".  The real service's error otherwise (0x809F0006 a wrong
 * fingerprint, 0x809F000F another account's save, 0x809F0008 none). */
s32 savedata_foreign_mount(s32 user, const char *tid, const char *dir, const char *fp, char mp[16]);
/* tid is another title than the running one and its host */
bool savedata_is_foreign(const char *tid);
/* Unmount what savedata_foreign_mount mounted. */
s32 savedata_umount(const char *mp);
/* tid's saves of user: up to max dir names, their params and sizes (blocks; any
 * of params and blocks may be NULL); *hits how many were filled. */
s32 savedata_foreign_search(s32 user, const char *tid, char (*dirs)[32], struct sd_param *params, u64 *blocks,
                            u32 max, u32 *hits);
/* Around every real sceSaveDataDirNameSearch: one at a time. */
void savedata_search_lock(void);
void savedata_search_unlock(void);
/* tid's fingerprint, from a keystone file where save tools keep them
 * (/data/ghostldr/keystones/<tid>.keystone, Apollo's /data/apollo/... ones). */
bool savedata_fingerprint(s32 user, const char *tid, char out[65]);
/* the keystone file itself (0x60 bytes, "keystone" first), from the same places */
bool savedata_keystone(s32 user, const char *tid, u8 out[0x60]);

/* A read-only copy of tid's save dir in dst (a host path), made through a
 * mount the save service binds and then refuses (no keystone match, perhaps
 * another account's): save_race.c.  0, or an error. */
s32 save_race_copy(s32 user, const char *tid, const char *dir, const char *dst);
/* The same H-RACE copy, left writable as a working tree.  Changes are not in
 * the save until save_race_write is called; that call may use a NULL fp. */
s32 save_race_rw_copy(s32 user, const char *tid, const char *dir, const char *dst);

/* ---- writing a save the service mounts and then refuses (save_race.c) ----
 * The resign without a jailbreak: tid's save dir of user gets the files of src
 * (a host folder; its sce_sys, if any, is ignored), through a read-write mount
 * the service binds before refusing it (another title's keystone).  Files are
 * rewritten, made and removed so the save holds exactly src's files; its own
 * sce_sys (owner, keystone) is never touched.  fp (64 hex characters, the
 * title's keystone fingerprint, or NULL) lets the save's present files be
 * found first, so the ones src lacks can be removed.  When r->needs_exit is
 * set, the write is in the mounted save and the system commits it when SWRR
 * closes: tell the user to close SWRR.  Never the running title's or its
 * host's saves.  The layout is shared with elfldr payloads
 * (ghostldr_save_race_write): keep it. */
struct save_race_result {
    s32 rc;          /* 0: written and checked */
    s32 mount_rc;    /* the save service's answer to the read-write mount */
    u32 slot;        /* the /savedataN it was bound to */
    u32 written;     /* files rewritten */
    u32 created;     /* files made */
    u32 unchanged;   /* files already the same */
    u32 deleted;     /* files and folders removed */
    u32 dirs_made;
    u32 verify_bad;  /* files that differ from the source after writing */
    u32 extra;       /* entries the source lacks still in the save */
    u64 bytes;
    bool committed;  /* the mount was allowed and its unmount committed it */
    bool needs_exit; /* written into the mounted save: committed when SWRR closes */
    u8 pad[6];
    char why[200];
};
_Static_assert(sizeof(struct save_race_result) == 256, "save_race_result is shared with payloads");

/* backup: a host folder (made if missing) that gets the save's present files before anything changes, or NULL */
s32 save_race_write(s32 user, const char *tid, const char *dir, const char *src, const char *fp, const char *backup,
                    struct save_race_result *r);
/* After SWRR restarted: whether tid's save dir now holds exactly src's files,
 * read-only with its fingerprint (needed).  r->rc 0: it does. */
s32 save_race_check(s32 user, const char *tid, const char *dir, const char *src, const char *fp,
                    struct save_race_result *r);

/* For save tools: tid's save dir copied whole (what the app may read of it) into the host folder dst (made
 * afresh), read-only with its fingerprint; and a digest of a host folder's save files (sce_sys left out), to see
 * whether a tool changed its copy. */
s32 save_fp_copy(s32 user, const char *tid, const char *dir, const char *fp, const char *dst);
u64 save_tree_digest(const char *dir);

/* ---- before a writable copy goes into its save (save tools, FTP /saves: save_race.c) ----
 * base is the save as it was: a host folder kept beside the writable copy
 * (save_tree_copy when the copy is made, again after each write), the
 * blocks it took then in had (save_tree_blocks; 0: count base now).
 * save_import_check says whether save_race_write can make the save hold
 * exactly what the copy src holds, before anything is asked of the save
 * service:
 *   - an entry base has and src lacks must be removed, which only a write
 *     with the game's fingerprint can (can_remove); without it: E_PERM;
 *   - a save's size is fixed (no write here can grow its image): src's
 *     files must fit in the room the save's files have, had plus its free
 *     blocks as the save service lists them (savedata_foreign_space), or
 *     estimated from base's sce_sys/param.sfo SAVEDATA_BLOCKS less the file
 *     system's share; otherwise 0x8002001C (ENOSPC).
 * Sizes are in 32 KiB blocks: each file takes at least one, each folder one.
 * c->why is the text for the screen (lines split by '\n') when rc != 0. */
struct save_import_check {
    s32 rc;
    u32 removed;       /* files base has and src lacks (folders if no file is missing) */
    bool removed_dirs; /* removed counts folders */
    u8 room_from;      /* 0 unknown, 1 the save service's free blocks, 2 the estimate from param.sfo */
    u8 pad[2];
    u64 had, need;     /* blocks of base's and of src's files and folders (sce_sys left out) */
    u64 blocks, free;  /* the save's size and free blocks (room_from) */
    char first[128];   /* the first entry that would have to go */
    char why[256];
};
s32 save_import_check(s32 user, const char *tid, const char *dir, const char *base, const char *src, u64 had,
                      bool can_remove, struct save_import_check *c);
/* dst made a copy of the host folder src (sce_sys too, as far as it can be read); keep_sys: dst's own top
 * sce_sys stays and src's is left out.  0, or an error: some file could not be copied (then, without keep_sys,
 * dst is gone, so a check against it fails instead of missing a file). */
s32 save_tree_copy(const char *src, const char *dst, bool keep_sys);
/* the blocks a host folder's files and folders take (sce_sys at the top left out) */
u64 save_tree_blocks(const char *dir);
/* the size and free blocks of tid's save dir of user, as the save service lists it (DirNameSearch's
 * SceSaveDataSearchInfo; hle_savedata.c).  0, or the service's error. */
s32 savedata_foreign_space(s32 user, const char *tid, const char *dir, u64 *blocks, u64 *free_blocks);

/* The title's /data, kept across SWRR sessions: the mount point of its
 * <prefix>D000SAVE container (made and mounted at the first call), or NULL
 * where there is none (no ghostfs title, no free mount point). */
const char *savedata_data_root(void);
/* Unmount it again (committed) if it is mounted: the selector's save scan,
 * whose extension may be given back before the title starts. */
void savedata_data_release(void);
