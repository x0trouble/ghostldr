/*
 * The network installer on the console (netinst.h): struct ns_env over what
 * the game selector module has, ghost_api and libkernel, and the three calls
 * the selector's Settings make (info.c).
 *
 *  - Memory: the core's page_alloc (zeroed), freed in netinst_stop; nothing
 *    from the selector's heap.  The module's image is read-only, so the
 *    environment lives in that memory too.
 *  - Sockets: on a PS5 at 8.00 or later (a PS4 at 14.00 or later) SWRR's
 *    own socket() answers ENOSYS for an internet socket.  The listening
 *    socket is then made by the JIT compiler process and handed over
 *    (jit_call + jit_recv_fd), on the boot thread, which netinst_start runs
 *    on; accept and the transfers work in SWRR (ext/src/ftp_sys.c does the
 *    same).  Send and receive buffers of 2 MiB (SWRR's defaults held one
 *    connection to a few MiB/s), SO_NOSIGPIPE, and SIGPIPE ignored.
 *  - Threads: libkernel's, 256 KiB of stack, joined in netinst_stop before
 *    the selector returns and its image is wiped.
 *  - Save containers: the core's gfs_mount_user (SWRR's own
 *    sceSaveDataMount, the user running SWRR) and gfs_umount;
 *    sceSaveDataDelete for that user.
 *  - USB drives: the ones the extension mounted in SWRR's sandbox
 *    (ext/src/approot.c: the device list's drives in its order, at
 *    /ghostldr_usb, /ghostldr_usb2, ..., as Settings reads them in info.c),
 *    each still a folder there, with its free space at that moment: the
 *    mount point's statfs when libkernel answers it (the drive's own file
 *    system under the nullfs mount), else sceUsbStorageGetDeviceInfo of
 *    the list's drive with the same number.  Files go on with the kernel's
 *    own calls (the mount is read-write), folders with sceKernelMkdir.
 *  - The page: ghostldr/data/netinstall.html.gz, gzip of the page
 *    (netinstall_page.py keeps it current), included at build time.
 *  - The address shown on the TV: sceNetCtlGetInfo(IP_ADDRESS); the server
 *    corrects it from the first connection if that fails.
 */
#include "ghost_api.h"
#include "netinst.h"

/* the page; the selector is built from ghostldr/native (make -C), where the
 * assembler finds this path */
__asm__(".pushsection .rodata\n"
        ".balign 16\n"
        "netinst_page_start:\n"
        ".incbin \"../data/netinstall.html.gz\"\n"
        "netinst_page_end:\n"
        ".popsection\n");
extern const unsigned char netinst_page_start[] __attribute__((visibility("hidden")));
extern const unsigned char netinst_page_end[] __attribute__((visibility("hidden")));

#define AF_INET 2
#define SOCK_STREAM 1
#define SOL_SOCKET 0xffff
#define SO_REUSEADDR 0x4
#define SO_REUSEPORT 0x200
#define SO_NOSIGPIPE 0x800
#define SO_SNDBUF 0x1001
#define SO_RCVBUF 0x1002
#define SO_SNDTIMEO 0x1005
#define SO_RCVTIMEO 0x1006
#define POLLIN 1
#define SIGPIPE 13
#define SYS_socket 97
#define SYS_close 6
#define ENOSYS 78
#define EINTR 4

struct sel_env {
    struct ns_env e; /* first: netinst.c's view */
    const struct ghost_api *api;
    struct boot_ctx *ctx;
    struct kfuncs *k;
    int (*socket)(int, int, int);
    int (*bind)(int, const void *, u32);
    int (*listen)(int, int);
    int (*accept)(int, void *, u32 *);
    int (*setsockopt)(int, int, int, const void *, u32);
    int (*getsockname)(int, void *, u32 *);
    s64 (*recvfrom)(int, void *, u64, int, void *, u32 *);
    int (*shutdown)(int, int);
    int (*poll)(void *, u32, int);
    int (*gettimeofday)(void *);
    u64 (*process_time)(void);
    int (*join)(u64, void **);
    int (*sigaction)(int, const void *, void *);
    s32 (*sd_delete)(const void *);
    int (*initial_user)(u32 *);
    s32 (*mkdir)(const char *, int);
    s32 (*usb_list)(u32 *, s32 *);
    s32 (*usb_info)(u32, u8 *);
    int (*statfs)(const char *, void *);
};

struct sin {
    u8 len, family;
    u16 port;
    u32 addr;
    u8 zero[8];
};

#define S ((struct sel_env *)e)
static u16 be16(u16 v) { return (u16)(v << 8 | v >> 8); }
static u32 be32(u32 v) { return __builtin_bswap32(v); }

/* an SCE kernel error (0x8002xxxx) as -errno; a BSD call's -1 as -errno */
static long sce(long rc) { return rc < 0 ? -(long)(rc & 0xFFFF) : rc; }
static long bsd(struct ns_env *e, long rc)
{
    if (rc >= 0)
        return rc;
    int er = S->k->errno_fn ? *S->k->errno_fn() : 0;
    return -(long)(er ? er : NS_EIO);
}

static void *e_alloc(struct ns_env *e, unsigned long size) { return S->api->page_alloc(size); }
static void e_free(struct ns_env *e, void *p, unsigned long size) { S->api->page_free(p, size); }
static void e_log(struct ns_env *e, const char *line) { S->api->logf("%s", line); }

static int e_thread(struct ns_env *e, void *(*fn)(void *), void *arg, unsigned long *handle)
{
    u8 attr[0x40];
    u64 tid = 0;
    S->k->pthread_attr_init(attr);
    S->k->pthread_attr_setstacksize(attr, 256 << 10);
    int rc = S->k->pthread_create(&tid, attr, fn, arg, "netinst");
    S->k->pthread_attr_destroy(attr);
    if (rc != 0)
        return -NS_EAGAIN;
    *handle = tid;
    return 0;
}
static void e_join(struct ns_env *e, unsigned long handle)
{
    if (S->join)
        S->join(handle, NULL);
}
static void e_sleep(struct ns_env *e, unsigned ms) { S->k->usleep(ms ? ms * 1000 : 100); }
static long e_now(struct ns_env *e)
{
    s64 tv[2] = {0, 0};
    return S->gettimeofday && S->gettimeofday(tv) == 0 ? tv[0] : 0;
}
static long e_clock(struct ns_env *e) { return S->process_time ? (long)(S->process_time() / 1000) : 0; }

static int e_open(struct ns_env *e, const char *path, int flags, int mode) { return (int)sce(S->k->open(path, flags, mode)); }
static long e_read(struct ns_env *e, int fd, void *b, unsigned long n) { return sce(S->k->read(fd, b, n)); }
static long e_write(struct ns_env *e, int fd, const void *b, unsigned long n) { return sce(S->k->write(fd, b, n)); }
static long e_seek(struct ns_env *e, int fd, long off) { return sce(S->k->lseek(fd, off, 0)); }
static int e_close(struct ns_env *e, int fd) { return (int)sce(S->k->close(fd)); }
static int e_size(struct ns_env *e, const char *path, unsigned long *size)
{
    u8 st[0x78];
    long rc = sce(S->k->stat(path, st));
    if (rc < 0)
        return (int)rc;
    *size = *(u64 *)(st + 0x48);
    return 0;
}

static void sock_opts(struct ns_env *e, int fd)
{
    int one = 1;
    S->setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &one, 4);
    for (int k = 0; k < 2; k++)
        for (int size = 2 << 20; size >= 64 << 10; size >>= 1)
            if (S->setsockopt(fd, SOL_SOCKET, k ? SO_RCVBUF : SO_SNDBUF, &size, 4) == 0)
                break;
}

/* the listening socket: SWRR's own socket(), else one the JIT compiler
 * process makes (boot thread only: the compiler channel is the boot
 * thread's) */
static int e_listen(struct ns_env *e, unsigned short port)
{
    long fd = bsd(e, S->socket(AF_INET, SOCK_STREAM, 0));
    if (fd == -ENOSYS && S->ctx->jit_syscall) {
        if (S->api->rpc_lock)
            S->api->rpc_lock();
        long cfd = (long)S->api->jit_call(S->ctx->jit_syscall, SYS_socket, AF_INET, SOCK_STREAM, 0, 0, 0, 0);
        fd = cfd >= 0 ? S->api->jit_recv_fd((int)cfd) : -1;
        if (cfd >= 0)
            S->api->jit_call(S->ctx->jit_syscall, SYS_close, (u64)cfd, 0, 0, 0, 0, 0);
        if (S->api->rpc_unlock)
            S->api->rpc_unlock();
        S->api->logf("netinst: the compiler's socket -> %ld, here %ld", cfd, fd);
        if (fd < 0)
            fd = -ENOSYS;
    }
    if (fd < 0)
        return (int)fd;
    sock_opts(e, (int)fd);
    int one = 1;
    S->setsockopt((int)fd, SOL_SOCKET, SO_REUSEADDR, &one, 4);
    S->setsockopt((int)fd, SOL_SOCKET, SO_REUSEPORT, &one, 4);
    struct sin a = {16, AF_INET, be16(port), 0, {0}};
    long rc = bsd(e, S->bind((int)fd, &a, sizeof(a)));
    if (rc == 0)
        rc = bsd(e, S->listen((int)fd, 8));
    if (rc < 0) {
        S->k->close((int)fd);
        return (int)rc;
    }
    return (int)fd;
}

static int e_accept(struct ns_env *e, int fd, int timeout_ms)
{
    struct {
        int fd;
        s16 events, revents;
    } p = {fd, POLLIN, 0};
    long n;
    do
        n = bsd(e, S->poll(&p, 1, timeout_ms));
    while (n == -EINTR);
    if (n == 0)
        return -NS_ETIMEDOUT;
    if (n < 0)
        return (int)n;
    struct sin a;
    u32 len = sizeof(a);
    long c;
    do
        c = bsd(e, S->accept(fd, &a, &len));
    while (c == -EINTR);
    if (c >= 0)
        sock_opts(e, (int)c);
    return (int)c;
}

static int e_sockname(struct ns_env *e, int fd, unsigned *addr)
{
    struct sin a;
    u32 len = sizeof(a);
    long rc = bsd(e, S->getsockname(fd, &a, &len));
    if (rc < 0)
        return (int)rc;
    *addr = be32(a.addr);
    return 0;
}

static void e_timeouts(struct ns_env *e, int fd, int seconds)
{
    s64 tv[2] = {seconds, 0};
    S->setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, tv, sizeof(tv));
    S->setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, tv, sizeof(tv));
}

static long e_send(struct ns_env *e, int fd, const void *buf, unsigned long n)
{
    unsigned long done = 0;
    while (done < n) {
        long w = bsd(e, S->k->sendto(fd, (const u8 *)buf + done, n - done, 0, NULL, 0));
        if (w == -EINTR)
            continue;
        if (w <= 0)
            return w < 0 ? w : -NS_EIO;
        done += (unsigned long)w;
    }
    return (long)n;
}

static long e_recv(struct ns_env *e, int fd, void *buf, unsigned long n)
{
    long r;
    do
        r = bsd(e, S->recvfrom(fd, buf, n, 0, NULL, NULL));
    while (r == -EINTR);
    return r;
}

static void e_shutdown(struct ns_env *e, int fd)
{
    if (S->shutdown)
        S->shutdown(fd, 2);
}
static void e_sclose(struct ns_env *e, int fd)
{
    e_shutdown(e, fd);
    S->k->close(fd);
}

static int e_mount(struct ns_env *e, const char *name, int mode, unsigned long blocks, char mp[16],
                   unsigned long *required)
{
    u64 req = 0;
    int rc = S->api->gfs_mount_user(-1, name, mode, blocks, mp, &req);
    if (required)
        *required = req;
    return rc;
}
static int e_umount(struct ns_env *e, const char mp[16]) { return S->api->gfs_umount(mp, 60000); }

static int e_remove(struct ns_env *e, const char *name)
{
    u32 uid = 0;
    if (!S->sd_delete || !S->initial_user || S->initial_user(&uid) != 0)
        return (int)0x809F000B; /* INTERNAL */
    char dir[32];
    u8 d[0x40];
    for (unsigned i = 0; i < sizeof(dir); i++)
        dir[i] = 0;
    for (unsigned i = 0; i < sizeof(d); i++)
        d[i] = 0;
    for (unsigned i = 0; name[i] && i < sizeof(dir) - 1; i++)
        dir[i] = name[i];
    *(u32 *)d = uid;
    *(char **)(d + 0x10) = dir; /* SceSaveDataDelete: userId @0, dirName* @0x10 */
    return S->sd_delete(d);
}

static int e_mkdir(struct ns_env *e, const char *path) { return S->mkdir ? (int)sce(S->mkdir(path, 0777)) : -ENOSYS; }

/* the drives mounted at /ghostldr_usb, /ghostldr_usb2, ...: drive i of the
 * device list at mount point i, while that is a folder (approot.c mounts
 * them in the list's order) */
static int e_drives(struct ns_env *e, struct ns_drive *d, int max)
{
    if (!S->usb_list || !S->usb_info) { /* Settings loaded the library (info.c drives) */
        char name[32] = "libSceUsbStorage.sprx", f1[32] = "sceUsbStorageGetDeviceList",
             f2[32] = "sceUsbStorageGetDeviceInfo";
        u32 h = 0;
        if (S->api->host_find_module(name, &h) != 0 || !h)
            return 0;
        *(void **)&S->usb_list = S->api->host_dlsym(h, f1);
        *(void **)&S->usb_info = S->api->host_dlsym(h, f2);
        if (!S->usb_list || !S->usb_info)
            return 0;
    }
    u32 ids[16];
    s32 n = 0;
    for (unsigned i = 0; i < 16; i++)
        ids[i] = 0;
    if (S->usb_list(ids, &n) != 0)
        return 0;
    int k = 0;
    for (s32 i = 0; i < n && i < NS_MAX_DRIVES && k < max; i++) {
        struct ns_drive *x = &d[k];
        u8 st[0x78], b[0x400];
        char *mp = x->mp;
        const char *base = "/ghostldr_usb";
        unsigned l = 0;
        for (; base[l]; l++)
            mp[l] = base[l];
        if (i)
            mp[l++] = (char)('1' + i);
        mp[l] = 0;
        if (S->k->stat(mp, st) != 0 || (*(u16 *)(st + 8) & 0xF000) != 0x4000)
            continue;
        for (unsigned j = 0; j < sizeof(b); j++)
            b[j] = 0;
        x->n = (unsigned)i + 1, x->fs = NS_FS_UNKNOWN, x->total = x->free = 0;
        if (S->usb_info(ids[i], b) == 0) {
            u32 features = *(u32 *)(b + 0x330);
            x->total = *(u64 *)b, x->free = *(u64 *)(b + 8);
            x->fs = features & 0x80 ? NS_FS_EXFAT : features & 0x40 ? NS_FS_FAT32 : NS_FS_UNKNOWN; /* docs/usb.md */
        }
        /* struct statfs (FreeBSD 9 to 11, 472 bytes; 12's is 2344): f_bsize @16, f_blocks @32, f_bavail @48,
         * f_fstypename[16] @280 */
        u8 sf[4096];
        for (unsigned j = 0; j < sizeof(sf); j++)
            sf[j] = 0;
        if (S->statfs && S->statfs(mp, sf) == 0 && *(u64 *)(sf + 16) && *(u64 *)(sf + 32)) {
            u64 bs = *(u64 *)(sf + 16);
            s64 avail = *(s64 *)(sf + 48);
            const char *t = (const char *)sf + 280;
            x->total = *(u64 *)(sf + 32) * bs, x->free = avail > 0 ? (u64)avail * bs : 0;
            if (t[0] == 'e' && t[1] == 'x' && t[2] == 'f' && t[3] == 'a' && t[4] == 't')
                x->fs = NS_FS_EXFAT;
            else if (t[0] == 'm' && t[1] == 's' && t[2] == 'd' && t[3] == 'o' && t[4] == 's')
                x->fs = NS_FS_FAT32;
        }
        k++;
    }
    return k;
}

/* ---- the selector's calls (info.c) ---- */

int netinst_start(const struct ghost_api *api, void **handle)
{
    *handle = NULL;
    struct sel_env *v = api->page_alloc(sizeof(*v));
    if (!v)
        return -NS_ENOMEM;
    struct ns_env *e = &v->e;
    v->api = api, v->ctx = *api->ctx, v->k = api->k;
    u32 lk = (u32)v->ctx->libkernel_handle;
#define SYM(field, name) *(void **)&v->field = api->host_dlsym(lk, name)
    SYM(socket, "socket");
    SYM(bind, "bind");
    SYM(listen, "listen");
    SYM(accept, "accept");
    SYM(setsockopt, "setsockopt");
    SYM(getsockname, "getsockname");
    SYM(recvfrom, "recvfrom");
    SYM(shutdown, "shutdown");
    SYM(poll, "poll");
    SYM(gettimeofday, "sceKernelGettimeofday");
    SYM(process_time, "sceKernelGetProcessTime");
    SYM(join, "scePthreadJoin");
    SYM(sigaction, "sigaction");
    SYM(mkdir, "sceKernelMkdir");
    SYM(statfs, "statfs");
#undef SYM
    *(void **)&v->sd_delete = api->host_real_in("libSceSaveData", "sceSaveDataDelete");
    *(void **)&v->initial_user = api->host_real_in("libSceUserService", "sceUserServiceGetInitialUser");
    if (!v->socket || !v->bind || !v->listen || !v->accept || !v->setsockopt || !v->recvfrom || !v->poll ||
        !v->k->sendto || !v->join) {
        api->logf("netinst: libkernel lacks a socket or thread call");
        api->page_free(v, sizeof(*v));
        return -ENOSYS;
    }
    if (v->sigaction) { /* a browser that goes away must not take SWRR with it */
        struct {
            u64 handler;
            int flags;
            u32 mask[4];
        } sa = {1 /* SIG_IGN */, 0, {0}};
        v->sigaction(SIGPIPE, &sa, NULL);
    }
    e->ctx = v;
    e->alloc = e_alloc, e->free = e_free, e->log = e_log, e->thread = e_thread, e->join = e_join;
    e->sleep_ms = e_sleep, e->now = e_now, e->clock_ms = e_clock;
    e->open = e_open, e->read = e_read, e->write = e_write, e->seek = e_seek, e->close = e_close, e->size = e_size;
    e->listen = e_listen, e->accept = e_accept, e->sockname = e_sockname, e->timeouts = e_timeouts;
    e->send = e_send, e->recv = e_recv, e->sclose = e_sclose, e->shutdown = e_shutdown;
    e->mount = e_mount, e->umount = e_umount, e->remove = e_remove;
    e->mkdir = e_mkdir, e->drives = e_drives;
    e->page = netinst_page_start;
    e->page_size = (unsigned long)(netinst_page_end - netinst_page_start);
    e->platform[0] = 'p', e->platform[1] = 's', e->platform[2] = (v->ctx->flags & CTX_FLAG_PS4) ? '4' : '5';
    s32 (*info)(s32, void *) = api->host_real_in("libSceNetCtl", "sceNetCtlGetInfo");
    char b[0x200];
    for (unsigned i = 0; i < sizeof(b); i++)
        b[i] = 0;
    if (info && info(14 /* SCE_NET_CTL_INFO_IP_ADDRESS */, b) == 0)
        for (unsigned i = 0; b[i] && i < 15; i++)
            e->address[i] = b[i];
    struct netinst *n = NULL;
    int rc = ns_start(e, 0, &n);
    api->logf("netinst: start -> %d (page %lu bytes, address '%s')", rc, e->page_size, e->address);
    if (!n) {
        api->page_free(v, sizeof(*v));
        return rc;
    }
    *handle = n;
    return rc;
}

/* the card's poll: the screen is up (the server takes POSTs while it is) */
int netinst_status(void *handle, struct netinst_status *st)
{
    ns_seen(handle);
    return ns_get_status(handle, st);
}

void netinst_stop(void **handle)
{
    struct netinst *n = *handle;
    if (!n)
        return;
    *handle = NULL;
    struct ns_env *e = ns_env_of(n);
    ns_stop(n);
    S->api->page_free(S, sizeof(struct sel_env));
}
