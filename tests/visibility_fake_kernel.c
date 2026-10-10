/* SPDX-License-Identifier: GPL-2.0-only */
/* Host-side check of the helper's profile-version handling against a stand-in
 * for the kernel's get/set rules. Never packaged.
 * Usage: KERNEL_PROFILE_VERSION absent|present
 */
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
static int fake_ioctl(int fd, unsigned long request, ...);
static int fake_setresuid(uid_t r, uid_t e, uid_t s) { (void)r; (void)e; (void)s; return 0; }
#define ioctl fake_ioctl
#define setresuid fake_setresuid
#define main helper_main
#include "../native/ksu_visibility.c"
#undef main
#undef ioctl

static unsigned kernel_version;
static size_t kernel_size;
static bool stored;
static struct app_profile slot;
static int sets, refused;

static int fake_ioctl(int fd, unsigned long request, ...) {
    (void)fd;
    va_list arguments;
    va_start(arguments, request);
    void *argument = va_arg(arguments, void *);
    va_end(arguments);
    if (request == KSU_IOCTL_GET_APP_PROFILE) {
        if (!stored) { errno = ENOENT; return -1; }
        memcpy(argument, &slot, kernel_size);
        return 0;
    }
    if (request == KSU_IOCTL_SET_APP_PROFILE) {
        struct app_profile *profile = argument;
        sets++;
        /* Version 3 kernels accept anything from 3 up; later ones only their own. */
        if (kernel_version == 3 ? profile->version < 3 : profile->version != kernel_version) {
            refused++; errno = EINVAL; return -1;
        }
        memset(&slot, 0, sizeof(slot));
        memcpy(&slot, profile, kernel_size);
        stored = true;
        return 0;
    }
    if (request == KSU_IOCTL_UID_SHOULD_UMOUNT) {
        struct ksu_uid_should_umount_cmd *cmd = argument;
        cmd->should_umount = !stored || slot.nrp_config.use_default || slot.nrp_config.profile.umount_modules;
        return 0;
    }
    errno = ENOTTY;
    return -1;
}

#define CHECK(condition) do { if (!(condition)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); return 1; } } while (0)

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    kernel_version = (unsigned)atoi(argv[1]);
    kernel_size = kernel_version == 3 ? 776 : sizeof(struct app_profile);
    const char *package = "com.oplus.camera";
    int uid = 10371;
    if (!strcmp(argv[2], "present")) {
        slot.version = kernel_version;
        strcpy(slot.key, package);
        slot.curr_uid = uid;
        slot.nrp_config.profile.umount_modules = true;
        stored = true;
    }
    /* apply */
    struct app_profile original = read_profile(package, uid);
    CHECK(original.version == (stored ? kernel_version : 0));
    CHECK(!visible(uid));
    write_profile(applied(original));
    CHECK(slot.version == kernel_version);
    CHECK(visible(uid));
    CHECK(!strcmp(slot.key, package) && slot.curr_uid == uid && !slot.allow_su);
    /* A known version is written once; an unknown one costs a version 4 kernel one refusal. */
    CHECK(sets == 1 + refused);
    CHECK(refused == (original.version == 0 && kernel_version == 4 ? 1 : 0));
    /* restore, as main() does it */
    struct app_profile current = read_profile(package, uid);
    if (!original.version) original.version = current.version;
    struct app_profile expected = applied(original);
    CHECK(!memcmp(&current, &expected, sizeof(current)));
    write_profile(original);
    CHECK(!visible(uid));
    CHECK(slot.version == kernel_version);
    puts("PASS");
    return 0;
}
