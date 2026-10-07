/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Experimental KernelSU profile-v3 visibility helper, NOT a release payload.
 * Uses the pinned upstream UAPI supplied by prepare_visibility.py.
 *
 * Profile ioctls require the manager's real UID. A root caller delegates that
 * identity only for an ioctl, retaining its effective/saved root UID, then
 * restores its real UID immediately. This needs device validation and is not
 * wired into installation or boot. No KernelSU database or global defaults
 * are edited, and root access is never granted or revoked.
 */
#define _GNU_SOURCE
#include <stdbool.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/file.h>
#include <sys/inotify.h>
#include <poll.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>
#include "uapi/supercall.h"

#define STATE_DIR "/data/adb/ooscamera-visibility"
_Static_assert(KSU_APP_PROFILE_VER == 3, "Only profile v3 is supported");
_Static_assert(sizeof(struct app_profile) == 776, "Unexpected profile ABI");
struct saved_state {
    char magic[8];
    struct app_profile original;
};
static int driver = -1;
static uid_t manager;
static int state_lock = -1;

static void fail(const char *message) {
    perror(message);
    exit(1);
}

static int manager_ioctl(unsigned long request, void *argument) {
    if (setresuid(manager, 0, 0)) fail("Delegate profile API identity");
    int result = ioctl(driver, request, argument), error = errno;
    if (setresuid(0, 0, 0)) fail("Restore root identity");
    errno = error;
    return result;
}

static bool visible(int uid) {
    struct ksu_uid_should_umount_cmd cmd = {.uid = uid};
    if (ioctl(driver, KSU_IOCTL_UID_SHOULD_UMOUNT, &cmd)) fail("Read mount policy");
    return !cmd.should_umount;
}

static struct app_profile read_profile(const char *package, int uid) {
    struct ksu_get_app_profile_cmd cmd = {0};
    cmd.profile.version = KSU_APP_PROFILE_VER;
    cmd.profile.current_uid = uid;
    strcpy(cmd.profile.key, package);
    if (manager_ioctl(KSU_IOCTL_GET_APP_PROFILE, &cmd)) {
        if (errno != ENOENT) fail("Read app profile");
        cmd.profile.nrp_config.use_default = true;
    }
    if (cmd.profile.version != KSU_APP_PROFILE_VER ||
        cmd.profile.current_uid != uid ||
        strnlen(cmd.profile.key, sizeof(cmd.profile.key)) == sizeof(cmd.profile.key) ||
        strcmp(cmd.profile.key, package)) {
        errno = EINVAL;
        fail("Profile identity or ABI mismatch");
    }
    return cmd.profile;
}

static void write_profile(struct app_profile profile) {
    if (profile.allow_su) { errno = EPERM; fail("Refuse root-profile mutation"); }
    struct ksu_set_app_profile_cmd cmd = {.profile = profile};
    if (manager_ioctl(KSU_IOCTL_SET_APP_PROFILE, &cmd)) fail("Write mount policy");
}

/* Independently verify package ownership; never modify a shared Android UID. */
static void verify_package(const char *package, int uid, bool restoring) {
    /* Binder services may not receive a root-only log FD as their stderr. */
    FILE *pipe = popen("/system/bin/cmd package list packages -U --user 0 2>/dev/null", "r");
    if (!pipe) fail("List package owners");
    char line[1024], found[256];
    int candidate, owners = 0;
    bool match = false;
    while (fgets(line, sizeof(line), pipe)) {
        if (sscanf(line, "package:%255s uid:%d", found, &candidate) == 2 && candidate == uid) {
            owners++;
            if (!strcmp(found, package)) match = true;
        }
    }
    int status = pclose(pipe);
    if (status || owners != 1 || !match) { errno = EINVAL; fail("Package UID ownership"); }
    if (restoring || !strcmp(package, "com.oplus.camera")) return;
    pipe = popen("/system/bin/cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME --user 0 2>/dev/null", "r");
    if (!pipe) fail("Resolve launcher");
    match = false;
    while (fgets(line, sizeof(line), pipe)) {
        char *slash = strchr(line, '/');
        if (slash) { *slash = 0; if (!strcmp(line, package)) match = true; }
    }
    status = pclose(pipe);
    if (status || !match) { errno = EPERM; fail("Target is not Camera or current launcher"); }
}

static struct app_profile applied(struct app_profile original) {
    original.nrp_config.use_default = false;
    original.nrp_config.profile.umount_modules = false;
    return original;
}

static void lock_state(void) {
    if (mkdir(STATE_DIR, 0700) && errno != EEXIST) fail("Create visibility state directory");
    struct stat st;
    if (lstat(STATE_DIR, &st) || !S_ISDIR(st.st_mode) || st.st_uid != 0 || (st.st_mode & 077)) {
        errno = EPERM; fail("Unsafe visibility state directory");
    }
    state_lock = open(STATE_DIR "/lock", O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (state_lock < 0 || fstat(state_lock, &st) || !S_ISREG(st.st_mode) ||
        st.st_uid != 0 || (st.st_mode & 077) || flock(state_lock, LOCK_EX)) {
        errno = EPERM; fail("Lock visibility state");
    }
}

static bool load_state(const char *path, struct saved_state *state, const char *package, int uid) {
    struct stat directory;
    if (lstat(STATE_DIR, &directory)) {
        if (errno == ENOENT) return false;
        fail("Inspect visibility state directory");
    }
    if (!S_ISDIR(directory.st_mode) || directory.st_uid != 0 || (directory.st_mode & 077)) {
        errno = EPERM; fail("Unsafe visibility state directory");
    }
    int fd = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) {
        if (errno == ENOENT) return false;
        fail("Open visibility backup");
    }
    struct stat st;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != 0 ||
        (st.st_mode & 077) || st.st_size != (off_t)sizeof(*state) ||
        read(fd, state, sizeof(*state)) != (ssize_t)sizeof(*state)) {
        errno = EINVAL; fail("Unsafe or incomplete visibility backup");
    }
    close(fd);
    if (memcmp(state->magic, "OOSVIS3", 8) || state->original.allow_su ||
        state->original.version != KSU_APP_PROFILE_VER ||
        state->original.current_uid != uid ||
        strnlen(state->original.key, sizeof(state->original.key)) == sizeof(state->original.key) ||
        strcmp(state->original.key, package)) {
        errno = EINVAL; fail("Visibility backup identity mismatch");
    }
    return true;
}

static void save_state(const char *path, struct saved_state state) {
    if (mkdir(STATE_DIR, 0700) && errno != EEXIST) fail("Create visibility state directory");
    struct stat st;
    if (lstat(STATE_DIR, &st) || !S_ISDIR(st.st_mode) || st.st_uid != 0 || (st.st_mode & 077)) {
        errno = EPERM; fail("Unsafe visibility state directory");
    }
    int fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) fail("Create visibility backup");
    if (write(fd, &state, sizeof(state)) != (ssize_t)sizeof(state) || fsync(fd)) {
        int error = errno; close(fd); unlink(path); errno = error;
        fail("Persist visibility backup");
    }
    if (close(fd)) fail("Close visibility backup");
    fd = open(STATE_DIR, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0 || fsync(fd)) fail("Persist visibility backup directory");
    close(fd);
}

int main(int argc, char **argv) {
    if (argc == 3 && !strcmp(argv[1], "watch")) {
        if (getuid() || geteuid() || strcmp(argv[2], "/data/adb/modules/ooscamera_op9")) {
            errno = EPERM; fail("Only this module's lifecycle may be watched");
        }
        int fd = inotify_init1(IN_CLOEXEC | IN_NONBLOCK);
        if (fd < 0) fail("Open module lifecycle watcher");
        if (inotify_add_watch(fd, argv[2], IN_CREATE | IN_MOVED_TO | IN_DELETE_SELF | IN_MOVE_SELF) < 0) {
            if (errno == ENOENT) return 0;
            fail("Watch module lifecycle");
        }
        while (access(argv[2], F_OK) == 0 &&
               access("/data/adb/modules/ooscamera_op9/disable", F_OK) != 0 &&
               access("/data/adb/modules/ooscamera_op9/remove", F_OK) != 0) {
            struct pollfd event = {.fd = fd, .events = POLLIN};
            int ready = poll(&event, 1, 1000);
            if (ready < 0 && errno != EINTR) fail("Wait for module lifecycle");
            char buffer[4096];
            if (ready > 0) while (read(fd, buffer, sizeof(buffer)) > 0) {}
        }
        close(fd);
        return 0;
    }
    if (argc == 2 && !strcmp(argv[1], "check")) {
        if (getuid() || geteuid()) { errno = EPERM; fail("Root caller required"); }
        syscall(SYS_reboot, KSU_INSTALL_MAGIC1, KSU_INSTALL_MAGIC2, 0, &driver);
        if (driver < 0) fail("Open KernelSU driver");
        struct ksu_get_manager_appid_cmd identity = {0};
        if (ioctl(driver, KSU_IOCTL_GET_MANAGER_APPID, &identity)) fail("Read manager identity");
        manager = identity.appid;
        if (manager && (manager < 10000 || manager >= 100000)) {
            errno = EINVAL; fail("Unsupported manager identity");
        }
        /* Read only: an absent profile also proves access to this ioctl ABI. */
        (void)read_profile("com.oplus.camera", 10000);
        puts("KernelSU profile interface accessible");
        return 0;
    }
    if (argc != 4 || (strcmp(argv[1], "probe") && strcmp(argv[1], "apply") && strcmp(argv[1], "restore"))) {
        fprintf(stderr, "Usage: ksu-visibility check | probe|apply|restore PACKAGE OWNER_UID | watch MODULE_DIR\n");
        return 2;
    }
    if (getuid() || geteuid()) { errno = EPERM; fail("Root caller required"); }
    const char *package = argv[2];
    if (!*package || strlen(package) >= KSU_MAX_PACKAGE_NAME ||
        strspn(package, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.") != strlen(package) ||
        strchr(package, '.') == NULL) { errno = EINVAL; fail("Invalid package name"); }
    char *end;
    errno = 0;
    long uid = strtol(argv[3], &end, 10);
    if (errno || !*argv[3] || *end || uid < 10000 || uid >= 100000) {
        fprintf(stderr, "Owner UID validation: length=%zu parsed=%ld errno=%d trailing=%d\n",
                strlen(argv[3]), uid, errno, (unsigned char)*end);
        errno = EINVAL; fail("Only owner-user app UIDs are supported");
    }
    bool restoring = !strcmp(argv[1], "restore");
    verify_package(package, (int)uid, restoring);
    syscall(SYS_reboot, KSU_INSTALL_MAGIC1, KSU_INSTALL_MAGIC2, 0, &driver);
    if (driver < 0) fail("Open KernelSU driver");
    struct ksu_get_info_cmd info = {0};
    if (ioctl(driver, KSU_IOCTL_GET_INFO, &info) || !info.version) fail("Read KernelSU interface");
    struct ksu_get_manager_appid_cmd identity = {0};
    if (ioctl(driver, KSU_IOCTL_GET_MANAGER_APPID, &identity)) fail("Read manager identity");
    manager = identity.appid;
    if (manager && (manager < 10000 || manager >= 100000)) {
        errno = EINVAL; fail("Unsupported manager identity");
    }
    if (strcmp(argv[1], "probe")) lock_state();
    struct app_profile current = read_profile(package, (int)uid);
    if (!strcmp(argv[1], "probe")) {
        printf("Profile v3 accessible; root=%s; modules=%s\n",
               current.allow_su ? "on" : "off", visible((int)uid) ? "visible" : "hidden");
        return 0;
    }
    char path[sizeof(STATE_DIR) + KSU_MAX_PACKAGE_NAME + 16];
    snprintf(path, sizeof(path), "%s/%s.state", STATE_DIR, package);
    struct saved_state state = {0};
    bool saved = load_state(path, &state, package, (int)uid);
    if (restoring) {
        if (!saved) { puts("No visibility policy to restore"); return 0; }
        struct app_profile expected = applied(state.original);
        if (memcmp(&current, &expected, sizeof(current))) {
            puts("Later profile changes preserved; restoration skipped");
        } else {
            write_profile(state.original);
            puts("Original mount policy restored");
        }
        if (unlink(path)) fail("Remove restored visibility backup");
        return 0;
    }
    if (current.allow_su || visible((int)uid)) { puts("No visibility change needed"); return 0; }
    if (saved) { errno = EBUSY; fail("Profile changed since automatic setup; preserve user choice"); }
    memcpy(state.magic, "OOSVIS3", 8);
    state.original = current;
    save_state(path, state);
    write_profile(applied(current));
    if (!visible((int)uid)) {
        write_profile(current);
        if (unlink(path)) fail("Remove rolled-back visibility backup");
        errno = EIO; fail("Mount visibility verification failed; original policy restored");
    }
    puts("Mount visibility enabled; root permission unchanged");
    return 0;
}
