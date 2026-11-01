/*
 * ghostldr's network installer (docs/using-the-release.md "Install over the network"): a web
 * server that installs a game from a browser, into SWRR's saved data or
 * onto a USB drive, started from the game selector's Settings ("Install
 * over network").  It serves the install page
 * (ghostldr/data/netinstall.html), whose JavaScript lays the game's folder
 * or .zip out the way gfs_pack.py does, and stores what the page sends into
 * save containers through the same /api/install/ requests as manager.lua;
 * onto a drive, the dump's files as they are (/api/install/usb/).
 *
 * No token: it changes nothing unless the TV shows its screen.  The
 * selector starts it as the screen opens and stops it as it closes, and
 * the server itself refuses every POST once the screen hasn't asked for
 * its status (ns_seen) for NETINST_SEEN_MS.
 *
 *   netinst.c      the server: HTTP, the requests, the status the selector
 *                  shows.  Freestanding C with no globals and no relocations
 *                  (it links into the selector module, whose image is
 *                  read-only), every outside call through struct ns_env.
 *   netinst_sel.c  the console's environment, in the selector module:
 *                  libkernel, sockets made by the JIT compiler process,
 *                  SWRR's save calls, the page (gzip) in the image.
 *
 * The selector module runs in the emulator's JIT buffer and is wiped when it
 * returns: ns_stop joins every thread the server started.  The host tests
 * (ghostldr/tests/test_netinstall.py) build netinst.c natively against
 * tests/ext_native/netinst_host.c.  Plain C types only.
 */
#pragma once

/* a USB drive (ns_env.drives) */
#define NS_FS_UNKNOWN 0
#define NS_FS_EXFAT 1
#define NS_FS_FAT32 2
struct ns_drive {
    unsigned n;    /* "USB drive n": its mount point's number (1: /ghostldr_usb, 2: /ghostldr_usb2) */
    unsigned fs;   /* NS_FS_* */
    unsigned long long total, free; /* bytes; 0: unknown */
    char mp[24];   /* its mount point */
};
#define NS_MAX_DRIVES 4

struct ns_env {
    void *ctx; /* the environment's own */
    /* memory: zeroed; NULL when there is none */
    void *(*alloc)(struct ns_env *e, unsigned long size);
    void (*free)(struct ns_env *e, void *p, unsigned long size);
    void (*log)(struct ns_env *e, const char *line);
    /* a thread, and waiting for it to end: 0, or < 0 */
    int (*thread)(struct ns_env *e, void *(*fn)(void *), void *arg, unsigned long *handle);
    void (*join)(struct ns_env *e, unsigned long handle);
    void (*sleep_ms)(struct ns_env *e, unsigned ms);
    long (*now)(struct ns_env *e);      /* seconds since 1970 */
    long (*clock_ms)(struct ns_env *e); /* monotonic milliseconds */
    /* files (paths in a mount point): fd or -errno; flags as ftp.h's FV_O_* */
    int (*open)(struct ns_env *e, const char *path, int flags, int mode);
    long (*read)(struct ns_env *e, int fd, void *buf, unsigned long n);
    long (*write)(struct ns_env *e, int fd, const void *buf, unsigned long n);
    long (*seek)(struct ns_env *e, int fd, long off);
    int (*close)(struct ns_env *e, int fd);
    int (*size)(struct ns_env *e, const char *path, unsigned long *size); /* 0, or -errno */
    int (*mkdir)(struct ns_env *e, const char *path); /* 0, or -errno (-NS_EEXIST: there already) */
    /* the USB drives mounted in SWRR's sandbox (/ghostldr_usb, /ghostldr_usb2,
     * ...), with their free space now: up to max, the count */
    int (*drives)(struct ns_env *e, struct ns_drive *d, int max);
    /* TCP: a listening socket on port (any address), or -errno; accept waits
     * up to timeout_ms (-ETIMEDOUT); send sends all of it */
    int (*listen)(struct ns_env *e, unsigned short port);
    int (*accept)(struct ns_env *e, int fd, int timeout_ms);
    int (*sockname)(struct ns_env *e, int fd, unsigned *addr); /* host order */
    void (*timeouts)(struct ns_env *e, int fd, int seconds);
    long (*send)(struct ns_env *e, int fd, const void *buf, unsigned long n);
    long (*recv)(struct ns_env *e, int fd, void *buf, unsigned long n);
    void (*sclose)(struct ns_env *e, int fd);
    void (*shutdown)(struct ns_env *e, int fd); /* wake a thread using it */
    /* SWRR's save containers for the user running it: 0 or an SCE error.
     * mode 1 read-only, 2 read-write, 6 create; mount points "/savedataN";
     * required gets the blocks a NO_SPACE_FS create is short of */
    int (*mount)(struct ns_env *e, const char *name, int mode, unsigned long blocks, char mp[16],
                 unsigned long *required);
    int (*umount)(struct ns_env *e, const char mp[16]); /* the commit */
    int (*remove)(struct ns_env *e, const char *name);
    /* the page, gzip-compressed */
    const unsigned char *page;
    unsigned long page_size;
    char address[24];  /* the console's IPv4 address as text, "" when unknown */
    char swrr[16];     /* "CUSA03474", "" when unknown */
    char platform[8];  /* "ps5", "ps4" */
};

/* ns_env's errno values (FreeBSD's) */
#define NS_ENOENT 2
#define NS_EIO 5
#define NS_ENOMEM 12
#define NS_EEXIST 17
#define NS_ENOSPC 28
#define NS_EAGAIN 35
#define NS_ETIMEDOUT 60
#define NS_O_RDONLY 0
#define NS_O_WRONLY 1
#define NS_O_CREAT 0x200
#define NS_O_TRUNC 0x400

/* what the server is doing (the selector shows it) */
#define NETINST_IDLE 0    /* never started */
#define NETINST_WAITING 1 /* listening: open url in a browser */
#define NETINST_BUSY 2    /* a browser is installing title */
#define NETINST_STOPPED 3
#define NETINST_FAILED 4  /* message says why */
struct netinst_status {
    unsigned size;  /* sizeof(struct netinst_status), set by the caller */
    unsigned state; /* NETINST_* */
    char url[40];   /* "http://192.168.1.10:8090/" */
    char where[12]; /* "USB drive 1" while installing onto a drive, "" into saved data */
    char title[16]; /* what is being installed ("" when nothing) */
    char name[64];  /* its name */
    unsigned long long done, total; /* bytes of it stored so far, of its total */
    unsigned rate_kib;  /* recent speed, KiB/s */
    unsigned installed; /* installs finished since the start: reread the catalogue when it changes */
    char message[128];  /* the latest event or error, one line */
    unsigned changes;   /* writes of the catalogue since the start (installs, removals): reread it when this changes */
};

#define NETINST_PORT 8090 /* the first port tried, then the next ones up to +9 */
#ifndef NETINST_SEEN_MS
#define NETINST_SEEN_MS 30000 /* POSTs refused once the TV's screen hasn't asked for so long (it asks 4 times a second) */
#endif
#define NETINST_BUF (4u << 20)
#define NETINST_BUFS 4

struct netinst;
/* Listen and serve from a thread of its own (e stays the caller's until
 * ns_stop).  0 and *out, or < 0 with *out still set when there is a status
 * to show (its message says why). */
int ns_start(struct ns_env *e, unsigned short port, struct netinst **out);
int ns_get_status(struct netinst *n, struct netinst_status *st); /* a snapshot: 0 */
void ns_seen(struct netinst *n); /* the TV shows the installer's screen now (netinst_status, at each poll) */
/* stop serving, commit an open container, join the threads, free it all */
void ns_stop(struct netinst *n);
struct ns_env *ns_env_of(struct netinst *n);

/* ---- the game selector's Settings > Network > Install over network
 * (selector/src/info.c; netinst_sel.c).  start: on the boot thread; 0, or
 * < 0 (a handle may still be set: its status says why).  status: a
 * snapshot, st->size set by the caller; it also tells the server that the
 * screen is up (ns_seen), so only the screen's own poll calls it.  stop: joins the server's threads
 * and frees everything; *handle is NULL afterwards.  The selector calls it
 * before it returns. ---- */
struct ghost_api;
int netinst_start(const struct ghost_api *api, void **handle);
int netinst_status(void *handle, struct netinst_status *st);
void netinst_stop(void **handle);
