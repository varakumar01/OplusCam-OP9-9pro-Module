/*
 * SPDX-FileCopyrightText: 2025 The LineageOS Project
 * SPDX-License-Identifier: Apache-2.0
 *
 * liboplus-uah-client for ROMs without the aox-cam4 hardware/oplus change
 * 238ddc9 ("[uah-client] send the camera HAL's scene requests to the power
 * HAL"). Same behaviour as that uah-client.cpp, rebuilt so it can be shipped
 * in a module without the platform build:
 *
 *  - no libc++: the std::string arguments are read through libc++'s string
 *    layout, which is fixed by the caller's (platform libc++) ABI;
 *  - no generated AIDL code: IPower V1 setMode/setBoost are two oneway
 *    transactions written by hand;
 *  - libbinder_ndk and liblog are opened on first use, so the library still
 *    loads (with hints disabled) wherever they are unavailable.
 *
 * DT_NEEDED is limited to libc.so and libdl.so.
 */

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* bionic */
typedef unsigned int uid_t;
typedef long pthread_t;
typedef struct { int32_t __private[10]; } pthread_mutex_t;  /* LP64 bionic */
struct timespec { long tv_sec; long tv_nsec; };
extern uid_t getuid(void);
extern int pthread_mutex_lock(pthread_mutex_t*);
extern int pthread_mutex_unlock(pthread_mutex_t*);
extern int pthread_create(pthread_t*, const void*, void* (*)(void*), void*);
extern int pthread_detach(pthread_t);
extern int nanosleep(const struct timespec*, struct timespec*);
extern void* malloc(size_t);
extern void free(void*);
extern void* memcpy(void*, const void*, size_t);
extern char* strstr(const char*, const char*);
extern void* dlopen(const char*, int);
extern void* dlsym(void*, const char*);
#define RTLD_NOW 2

/* libbinder_ndk, liblog: resolved at run time */
typedef struct AIBinder AIBinder;
typedef struct AIBinder_Class AIBinder_Class;
typedef struct AParcel AParcel;
static struct {
    bool tried, ok;
    AIBinder* (*checkService)(const char*);
    AIBinder_Class* (*classDefine)(const char*, void* (*)(void*), void (*)(void*),
                                   int32_t (*)(AIBinder*, uint32_t, const AParcel*, AParcel*));
    bool (*associateClass)(AIBinder*, const AIBinder_Class*);
    int32_t (*prepareTransaction)(AIBinder*, AParcel**);
    int32_t (*transact)(AIBinder*, uint32_t, AParcel**, AParcel**, uint32_t);
    int32_t (*writeInt32)(AParcel*, int32_t);
    int32_t (*writeBool)(AParcel*, bool);
    void (*parcelDelete)(AParcel*);
    void (*decStrong)(AIBinder*);
    int (*log)(int, const char*, const char*, ...);
} ndk;

#define LOG_TAG "uah-client"
#define ALOGD(...) do { if (ndk.log) ndk.log(3, LOG_TAG, __VA_ARGS__); } while (0)

/* android.hardware.power IPower V1 (frozen API) */
static const char kDescriptor[] = "android.hardware.power.IPower";
static const char kInstance[] = "android.hardware.power.IPower/default";
enum { TX_SET_MODE = 1, TX_SET_BOOST = 3 };            /* FIRST_CALL_TRANSACTION + 0, + 2 */
enum { FLAG_ONEWAY = 0x01, FLAG_PRIVATE_VENDOR = 0x10000000 };
enum { CAMERA_STREAMING_LOW = 12, CAMERA_STREAMING_MID = 13, CAMERA_STREAMING_HIGH = 14 };
enum { CAMERA_LAUNCH = 4, CAMERA_SHOT = 5 };
#define NO_MODE (-1)

static const uid_t kCameraProviderUid = 1047;  /* AID_CAMERASERVER */

static pthread_mutex_t gLock;  /* zero is PTHREAD_MUTEX_INITIALIZER on bionic */
static AIBinder* gPower;
static AIBinder_Class* gClass;
static int gMode = NO_MODE;
static int gHandle;      /* last handle given out */
static int gModeHandle;  /* handle that owns gMode */

static void* onCreate(void* args) { return args; }
static void onDestroy(void* data) { (void)data; }
static int32_t onTransact(AIBinder* b, uint32_t c, const AParcel* i, AParcel* o) {
    (void)b; (void)c; (void)i; (void)o;
    return -74; /* STATUS_UNKNOWN_TRANSACTION: this class is only used as a client */
}

static bool loadNdk(void) {
    if (ndk.tried) return ndk.ok;
    ndk.tried = true;
    void* log = dlopen("liblog.so", RTLD_NOW);
    if (log) ndk.log = (int (*)(int, const char*, const char*, ...))dlsym(log, "__android_log_print");
    void* b = dlopen("libbinder_ndk.so", RTLD_NOW);
    if (!b) return false;
#define SYM(field, name) *(void**)&ndk.field = dlsym(b, name); if (!ndk.field) return false
    SYM(checkService, "AServiceManager_checkService");
    SYM(classDefine, "AIBinder_Class_define");
    SYM(associateClass, "AIBinder_associateClass");
    SYM(prepareTransaction, "AIBinder_prepareTransaction");
    SYM(transact, "AIBinder_transact");
    SYM(writeInt32, "AParcel_writeInt32");
    SYM(writeBool, "AParcel_writeBool");
    SYM(parcelDelete, "AParcel_delete");
    SYM(decStrong, "AIBinder_decStrong");
#undef SYM
    gClass = ndk.classDefine(kDescriptor, onCreate, onDestroy, onTransact);
    ndk.ok = gClass != NULL;
    return ndk.ok;
}

static void dropPower(void) {
    if (gPower) ndk.decStrong(gPower);
    gPower = NULL;
}

/*
 * Only the camera provider gets to talk to the power HAL; every other
 * process that loads this library (the camera app does) gets handles
 * that do nothing.
 */
static AIBinder* getPower(void) {
    if (getuid() != kCameraProviderUid || !loadNdk()) return NULL;
    if (gPower == NULL) {
        gPower = ndk.checkService(kInstance);
        if (gPower && !ndk.associateClass(gPower, gClass)) dropPower();
    }
    return gPower;
}

/* One oneway IPower call with two int-sized arguments. */
static bool call(uint32_t code, int32_t a, int32_t b, bool bIsBool) {
    AIBinder* power = getPower();
    if (power == NULL) return false;
    AParcel* in = NULL;
    AParcel* out = NULL;
    if (ndk.prepareTransaction(power, &in) != 0) { dropPower(); return false; }
    int32_t st = ndk.writeInt32(in, a);
    if (st == 0) st = bIsBool ? ndk.writeBool(in, b != 0) : ndk.writeInt32(in, b);
    if (st != 0) { ndk.parcelDelete(in); return false; }
    /* AIBinder_transact takes ownership of `in`. */
    st = ndk.transact(power, code, &in, &out, FLAG_ONEWAY | FLAG_PRIVATE_VENDOR);
    if (out) ndk.parcelDelete(out);
    if (st != 0) { dropPower(); return false; }
    return true;
}

static void setMode(int mode) {
    if (mode == gMode) return;
    if (getPower() == NULL) return;
    if (gMode != NO_MODE) call(TX_SET_MODE, gMode, false, true);
    if (mode != NO_MODE) call(TX_SET_MODE, mode, true, true);
    gMode = mode;
}

static bool has(const char* s, const char* token) { return strstr(s, token) != NULL; }

/* Scene names are the camera HAL's OSENSE_ACTION_CAMERA_* strings. */
static int modeFor(const char* s) {
    static const char* const high[] = {"UHD120", "8K", "HFR", "SLOW", "4K", "60FPS", "SUPER_STEADY"};
    static const char* const mid[] = {"VIDEO", "MOVIE", "48M", "MULTI_SCENE", "STIKER_RECORD"};
    for (size_t i = 0; i < sizeof(high) / sizeof(high[0]); i++)
        if (has(s, high[i])) return CAMERA_STREAMING_HIGH;
    for (size_t i = 0; i < sizeof(mid) / sizeof(mid[0]); i++)
        if (has(s, mid[i])) return CAMERA_STREAMING_MID;
    return CAMERA_STREAMING_LOW;
}

static void release(int handle) {
    pthread_mutex_lock(&gLock);
    if (handle == gModeHandle) {
        setMode(NO_MODE);
        gModeHandle = 0;
    }
    pthread_mutex_unlock(&gLock);
}

struct expiry { int handle; int timeoutMs; };

static void* expire(void* arg) {
    struct expiry e = *(struct expiry*)arg;
    free(arg);
    struct timespec t = { e.timeoutMs / 1000, (long)(e.timeoutMs % 1000) * 1000000L };
    while (nanosleep(&t, &t) != 0) {}
    release(e.handle);
    return NULL;
}

/*
 * libc++ std::string (platform ABI, little-endian, default layout):
 * short: byte 0 = size << 1 (bit 0 clear), characters from byte 1;
 * long:  word 0 = capacity | 1, word 1 = size, word 2 = data pointer.
 */
static const char* strData(const void* s, size_t* size) {
    const unsigned char* p = (const unsigned char*)s;
    if (p[0] & 1) {
        *size = ((const size_t*)s)[1];
        return ((const char* const*)s)[2];
    }
    *size = p[0] >> 1;
    return (const char*)p + 1;
}

/* scene + " " + action as a C string; NULL on allocation failure. */
static char* joinScene(const void* scene, const void* action) {
    size_t n1, n2;
    const char* s1 = strData(scene, &n1);
    const char* s2 = strData(action, &n2);
    char* name = (char*)malloc(n1 + n2 + 2);
    if (name == NULL) return NULL;
    memcpy(name, s1, n1);
    name[n1] = ' ';
    memcpy(name + n1 + 1, s2, n2);
    name[n1 + n2 + 1] = '\0';
    return name;
}

#define EXPORT __attribute__((visibility("default")))

/*
 * int UahEventAcquireWrapper(std::string scene, std::string& action,
 *                            std::string& identity, int timeoutMs)
 * A by-value std::string is passed by invisible reference (Itanium C++ ABI).
 */
EXPORT int UahEventAcquireWrapper(const void* scene, const void* action, const void* identity,
                                  int timeoutMs) {
    (void)identity;
    char* name = joinScene(scene, action);
    pthread_mutex_lock(&gLock);
    const int handle = ++gHandle;
    if (name == NULL) {
        pthread_mutex_unlock(&gLock);
        return handle;
    }
    ALOGD("acquire %d: '%s' timeout %d", handle, name, timeoutMs);

    if (has(name, "CAMERA_CLOSE")) {
        setMode(NO_MODE);
        gModeHandle = 0;
    } else if (has(name, "CAMERA_OPEN") || has(name, "CAMERA_CAPTURE")) {
        const int boost = has(name, "CAMERA_OPEN") ? CAMERA_LAUNCH : CAMERA_SHOT;
        /* A negative duration would end the hint; 0 uses its configured length. */
        call(TX_SET_BOOST, boost, timeoutMs > 0 ? timeoutMs : 0, false);
    } else {
        setMode(modeFor(name));
        gModeHandle = handle;
        if (timeoutMs > 0) {
            struct expiry* e = (struct expiry*)malloc(sizeof(*e));
            pthread_t thread;
            if (e) {
                e->handle = handle;
                e->timeoutMs = timeoutMs;
                if (pthread_create(&thread, NULL, expire, e) == 0) pthread_detach(thread);
                else free(e);
            }
        }
    }
    pthread_mutex_unlock(&gLock);
    free(name);
    return handle;
}

EXPORT int UahRelease(int handle) { release(handle); return 0; }
EXPORT int UahReleaseWapper(int handle) { release(handle); return 0; }

/*
 * The rest of the stock library's interface. The osense client resolves
 * every one of these when it loads the library; none has a power HAL
 * equivalent.
 */
EXPORT int setRelatedSysInfo(void) { return 0; }
EXPORT int uahInit(void) { return 0; }
EXPORT int UahNotifyWapper(void) { return 0; }
EXPORT int UahNotify(void) { return 0; }
EXPORT int UahEventAcquire(void) { return 0; }
EXPORT int UahEventAcquireOneWay(void) { return 0; }
EXPORT int UahResAcquire(void) { return 0; }
EXPORT int UahPlatformResAcquire(void) { return 0; }
EXPORT int UahResStateRequest(void) { return 0; }
EXPORT int UahMutiResStateRequest(void) { return 0; }
EXPORT int UahGetHistory(void) { return 0; }
EXPORT int UahGetPowerConsis(void) { return 0; }
EXPORT int UahGetPMStatus(void) { return 0; }
EXPORT int Uah_fetch_dataset(void) { return 0; }
EXPORT int uahRuleCtl(void) { return 0; }
EXPORT int UahResourceInfo(void) { return 0; }

/* Marker for the installer: this copy may be replaced by later module builds. */
EXPORT const char ooscamera_uah_client_marker[] = "ooscamera-aox-cam4-uah-client";

#ifdef UAH_HOST_TEST
/* Host-test hooks (tests/test_aox_cam4.py); not built for the device. */
EXPORT char* uah_test_join(const void* scene, const void* action) { return joinScene(scene, action); }
EXPORT int uah_test_mode(const char* name) { return modeFor(name); }
#endif
