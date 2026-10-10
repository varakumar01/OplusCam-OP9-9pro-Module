/* SPDX-License-Identifier: GPL-2.0-only */
/* Developer-only device fixture. Never packaged.
 * PACKAGE UID: apply/idempotence/restore roundtrip.
 * PACKAGE UID prepare: save original and select inherited hidden policy.
 * PACKAGE UID recover: restore the durable original after lifecycle tests.
 * Backups contain private profiles; keep them on the device and remove on recovery.
 */
#define main visibility_main
#include "../native/ksu_visibility.c"
#undef main
#include <sys/wait.h>
#define RECOVERY "/data/adb/ooscamera-visibility-test.original"
static int run(const char *action, const char *package, const char *uid) {
    pid_t pid = fork();
    if (pid < 0) fail("fork");
    if (!pid) {
        execl("/data/local/tmp/ooscamera-visibility-test", "ksu-visibility", action, package, uid, NULL);
        _exit(127);
    }
    int status;
    if (waitpid(pid, &status, 0) < 0) fail("wait");
    return WIFEXITED(status) && WEXITSTATUS(status) == 0;
}
int main(int argc, char **argv) {
    if ((argc != 3 && argc != 4) || getuid() || geteuid()) return 2;
    const char *package = argv[1], *uid_text = argv[2];
    char *end;
    long parsed = strtol(uid_text, &end, 10);
    if (!*uid_text || *end || parsed < 10000 || parsed >= 100000) return 2;
    int uid = (int)parsed;
    if (argc == 4 && strcmp(argv[3], "prepare") && strcmp(argv[3], "recover")) return 2;
    verify_package(package, uid, false);
    syscall(SYS_reboot, KSU_INSTALL_MAGIC1, KSU_INSTALL_MAGIC2, 0, &driver);
    if (driver < 0) fail("driver");
    struct ksu_get_manager_appid_cmd id = {0};
    if (ioctl(driver, KSU_IOCTL_GET_MANAGER_APPID, &id)) fail("manager");
    manager = id.appid;
    if (manager && (manager < 10000 || manager >= 100000)) return 2;
    struct app_profile original = read_profile(package, uid);
    if (original.allow_su) return 2;
    char statepath[512];
    snprintf(statepath, sizeof(statepath), "%s/%s.state", STATE_DIR, package);
    if (access(statepath, F_OK) == 0) { fprintf(stderr, "Existing backup: refuse test\n"); return 2; }
    char recovery_path[512];
    snprintf(recovery_path, sizeof(recovery_path), "%s.%s", RECOVERY, package);
    if (argc == 4 && !strcmp(argv[3], "recover")) {
        int fd = open(recovery_path, O_RDONLY|O_NOFOLLOW);
        if (fd < 0 || read(fd, &original, sizeof(original)) != sizeof(original)) fail("Read original");
        close(fd);
        if (strcmp(original.key, package) || original.curr_uid != uid || original.allow_su || !known_version(original.version)) return 2;
        write_profile(original);
        struct app_profile actual = read_profile(package, uid);
        if (memcmp(&actual, &original, sizeof(actual))) fail("Recover original");
        unlink(recovery_path);
        puts("Original test profile recovered");
        return 0;
    }
    int recovery = open(recovery_path, O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0600);
    if (recovery < 0) fail("Recovery backup (do not overwrite)");
    if (write(recovery, &original, sizeof(original)) != sizeof(original) || fsync(recovery)) fail("Persist recovery");
    close(recovery);
    if (argc == 4 && !strcmp(argv[3], "prepare")) {
        struct app_profile inherited = original;
        inherited.nrp_config.use_default = true;
        write_profile(inherited);
        if (visible(uid)) fail("Inherited profile unexpectedly visible");
        puts("Inherited hidden profile prepared; durable original saved");
        return 0;
    }
    struct app_profile hidden = original;
    hidden.nrp_config.use_default = false;
    hidden.nrp_config.profile.umount_modules = true;
    write_profile(hidden);
    int ok = !visible(uid);
    if (ok) ok = run("apply", package, uid_text);
    struct app_profile current = read_profile(package, uid), expected = applied(hidden);
    if (ok) ok = visible(uid) && !memcmp(&current, &expected, sizeof(current));
    if (ok) ok = run("apply", package, uid_text);
    if (ok) ok = run("restore", package, uid_text);
    current = read_profile(package, uid);
    if (ok) ok = !visible(uid) && !memcmp(&current, &hidden, sizeof(current));
    /* Always return the real original profile, even if an assertion failed. */
    write_profile(original);
    current = read_profile(package, uid);
    if (memcmp(&current, &original, sizeof(current))) fail("Original profile verification");
    if (!ok && access(statepath, F_OK) == 0) run("restore", package, uid_text);
    if (unlink(recovery_path)) fail("Remove recovery file");
    puts(ok ? "PASS: apply, idempotence, restore; original profile unchanged" : "FAIL: original profile restored");
    return ok ? 0 : 1;
}
