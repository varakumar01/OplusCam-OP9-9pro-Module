"""Host checks for the aox installer logic, build staging and uah client.

Configuration tests need the pinned fixtures:
    python scripts/prepare_aox.py --fixtures
Shell tests run under BusyBox ash (as KernelSU does) when it is installed.
"""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/aox"
FIXTURES = CACHE / "fixtures/lemonade"
PRO_FIXTURES = CACHE / "fixtures/lemonadep"
SCRIPT = ROOT / "module/aox.sh"
CONFIGS = [
    "odm/etc/camera/CameraHWConfiguration.config",
    "odm/etc/camera/config/camera_unit_config",
    "odm/etc/camera/config/oplus_camera_algo_switch_config",
    "odm/etc/camera/config/oplus_camera_aps_config",
    "odm/etc/camera/config/oplus_camera_config",
]
MEDIA = "vendor/etc/media_profiles_vendor.xml"
SHELL = shutil.which("busybox")

sys.path.insert(0, str(ROOT / "scripts"))


def staged(modpath, path):
    if path.startswith("odm/"):
        return modpath / "system/vendor" / path
    return modpath / "system" / path


@unittest.skipUnless(SHELL, "BusyBox is required")
class Installer(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.root = self.tmp / "root"
        self.modpath = self.tmp / "module"
        self.root.mkdir()
        shutil.copytree(ROOT / "module/aox", self.modpath / "aox")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def install(self, device="lemonade", check=True, **env):
        script = ("ui_print() { :; }; . \"$1\"; aox_install")
        env = dict(os.environ, MODPATH=str(self.modpath), AOX_ROOT=str(self.root),
                   AOX_DEVICE=device, AOX_OLD=str(self.tmp / "old"),
                   AOX_OLD_MODULE=str(self.tmp / "old-module"), **env)
        result = subprocess.run([SHELL, "sh", "-c", script, "test", str(SCRIPT)], env=env)
        if check:
            self.assertEqual(result.returncode, 0)
        self.status = result.returncode
        return (self.modpath / "aox.log").read_text()

    def device_file(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    # ----------------------------------------------------------- configs
    def fixtures(self):
        if not (FIXTURES / "base" / CONFIGS[0]).exists():
            self.skipTest("run scripts/prepare_aox.py --fixtures")
        for path in CONFIGS + [MEDIA]:
            self.device_file(path, (FIXTURES / "base" / path).read_bytes())

    def test_base_configs_become_head(self):
        self.fixtures()
        log = self.install()
        self.assertNotIn("skip", log)
        for path in CONFIGS:
            result = staged(self.modpath, path).read_bytes()
            head = (FIXTURES / "head" / path).read_bytes()
            if path.endswith("oplus_camera_aps_config"):
                # Not strict JSON; the one new tag is appended.
                self.assertIn(b'"com.oplus.aps.support.hw_jpeg"', result)
                self.assertIn(b'"com.oplus.aps.support.hw_jpeg"', head)
                continue
            if path.endswith("oplus_camera_config"):
                # New tags are appended rather than inserted mid-file.
                tags = lambda data: {e["VendorTag"]: e for e in json.loads(data)}
                self.assertEqual(tags(result), tags(head), path)
            else:
                self.assertEqual(result, head, path)
        media = self.modpath / "aox/media" / MEDIA
        self.assertEqual(media.read_bytes(), (FIXTURES / "head" / MEDIA).read_bytes())

    def test_pro_base_configs_become_pro_head(self):
        if not (PRO_FIXTURES / "base" / CONFIGS[0]).exists():
            self.skipTest("run scripts/prepare_aox.py --fixtures")
        for path in CONFIGS:
            self.device_file(path, (PRO_FIXTURES / "base" / path).read_bytes())
        self.install(device="lemonadep")
        tags = lambda data: {e["VendorTag"]: e for e in json.loads(data)}
        for path in CONFIGS:
            head = (PRO_FIXTURES / "head" / path).read_bytes()
            target = staged(self.modpath, path)
            # Untouched files are not staged: the device copy already is head.
            result = target.read_bytes() if target.exists() else (self.root / path).read_bytes()
            if path.endswith("oplus_camera_aps_config"):
                self.assertIn(b'"com.oplus.aps.support.hw_jpeg"', result)
            elif path.endswith("oplus_camera_config"):
                self.assertEqual(tags(result), tags(head), path)
            else:
                # The Pro tree's jni.version line ends in LF inside a CRLF file.
                unix = lambda data: data.replace(b"\r\n", b"\n")
                self.assertEqual(unix(result), unix(head), path)

    def test_running_module_edits_are_provided_again(self):
        # The visible file is already head because the running module
        # overlays it; the new install must stage it again.
        self.fixtures()
        path = "odm/etc/camera/config/camera_unit_config"
        head = (FIXTURES / "head" / path).read_bytes()
        self.device_file(path, head)
        old = self.tmp / "old/vendor" / path
        old.parent.mkdir(parents=True)
        old.write_bytes(head)
        self.install()
        self.assertEqual(staged(self.modpath, path).read_bytes(), head)

    def test_second_install_is_a_no_op(self):
        self.fixtures()
        self.install()
        edited = [p for p in CONFIGS if staged(self.modpath, p).exists()]
        self.assertEqual(len(edited), len(CONFIGS))
        first = {p: staged(self.modpath, p).read_bytes() for p in edited}
        log = self.install()
        self.assertNotIn("apply odm", log)
        self.assertEqual(first, {p: staged(self.modpath, p).read_bytes() for p in edited})

    def test_head_device_needs_no_config_copy(self):
        if not (FIXTURES / "head" / CONFIGS[0]).exists():
            self.skipTest("run scripts/prepare_aox.py --fixtures")
        for path in CONFIGS + [MEDIA]:
            self.device_file(path, (FIXTURES / "head" / path).read_bytes())
        log = self.install()
        self.assertNotIn("apply", log)
        self.assertFalse(any(staged(self.modpath, p).exists() for p in CONFIGS))
        self.assertFalse((self.modpath / "aox/media").exists())

    def test_unmatched_edits_are_skipped_not_forced(self):
        self.fixtures()
        path = "odm/etc/camera/CameraHWConfiguration.config"
        text = (FIXTURES / "base" / path).read_text()
        # A different SAT device: other ultrawide map, no [ZoomRange] section.
        text = text.replace("fixActiveMapList            =      0x1",
                            "fixActiveMapList            =      0x7")
        text = text.replace("[ZoomRange]", "[OtherZoom]")
        self.device_file(path, text.encode())
        unit = "odm/etc/camera/config/camera_unit_config"
        # A different rear_main video table; the fps map alone still matches.
        old = (ROOT / "module/aox/blocks/video-120fps-rear-main.old").read_bytes()
        data = (FIXTURES / "base" / unit).read_bytes().replace(old, old.replace(b'"fovc/', b'"fovc2/'))
        self.device_file(unit, data)
        log = self.install()
        self.assertIn("skip  odm/etc/camera/CameraHWConfiguration.config: [UltraWideStrategy]", log)
        self.assertIn("skip  odm/etc/camera/CameraHWConfiguration.config: [ZoomRange]", log)
        self.assertIn("apply odm/etc/camera/CameraHWConfiguration.config: [SatSmoothZoom]", log)
        result = staged(self.modpath, path).read_text()
        self.assertIn("fixActiveMapList            =      0x7", result)
        self.assertIn("closeSlaveThresholdTime = 1", result)
        # The 120fps group needs both blocks; neither is applied alone.
        self.assertIn("skip  odm/etc/camera/config/camera_unit_config", log)
        self.assertFalse(staged(self.modpath, unit).exists())

    def test_module_copy_is_edited_and_its_own_values_kept(self):
        self.fixtures()
        path = "odm/etc/camera/config/oplus_camera_config"
        entries = json.loads((FIXTURES / "base" / path).read_text())
        sat = next(e for e in entries if e["VendorTag"] == "com.oplus.feature.video.sat.support")
        sat["Value"] = "0"
        module_copy = staged(self.modpath, path)
        module_copy.parent.mkdir(parents=True)
        module_copy.write_text(json.dumps(entries, indent=2) + "\n")
        self.install()
        result = {e["VendorTag"]: e["Value"] for e in json.loads(module_copy.read_text())}
        self.assertEqual(result["com.oplus.feature.video.sat.support"], "0")
        self.assertEqual(result["com.oplus.video.4k.track.focus.support"], "1")

    # --------------------------------------------------------- libraries
    def stage_libraries(self, rows):
        lines = []
        for path, rule, data, replace, needed, *device in rows:
            device = device[0] if device else ""
            target = staged(self.modpath, path)
            if device:
                target = self.modpath / "aox/variants" / device / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            lines.append("|".join([path, rule, hashlib.sha256(data).hexdigest(),
                                   ",".join(replace), ",".join(needed), device]))
        (self.modpath / "aox/files.txt").write_text("\n".join(lines) + "\n")
        (self.modpath / "aox/edits.txt").write_text("")

    def test_library_rules_and_dependencies(self):
        sha = lambda data: hashlib.sha256(data).hexdigest()
        for lib in ("libc.so", "liblog.so"):
            self.device_file("system/lib64/" + lib, b"bionic")
        self.device_file("odm/lib64/libEIS.so", b"base libEIS")
        self.device_file("odm/lib64/libnightvision.so", b"rom nightvision")
        self.device_file("odm/lib/rfsa/adsp/libarcsoft_hdrplus_hvx_skel_lemonade.so", b"base skel")
        self.device_file("odm/lib64/libFDClite.so", b"rom FDClite")
        self.stage_libraries([
            ("odm/lib64/libAncFilter.so", "add", b"new", [], ["libc.so", "liblog.so"]),
            ("odm/lib64/libFDClite.so", "add", b"branch FDClite", [], ["libc.so"]),
            ("odm/lib64/libEIS.so", "replace", b"relinked", [sha(b"base libEIS")],
             ["libui-oplus.so", "libc.so"]),
            ("odm/lib64/libui-oplus.so", "add", b"ui", [], ["libc.so"]),
            ("odm/lib64/libnightvision.so", "add-or-replace", b"lsnr", [sha(b"stock nightvision")],
             ["libc.so"]),
            ("odm/lib/rfsa/adsp/libarcsoft_hdrplus_hvx_skel_lemonade.so", "replace", b"stock skel",
             [sha(b"base skel")], []),
            # libYTCommon needs a shim this ROM lacks; its dependents go too.
            ("odm/lib64/libYTCommon.so", "add", b"yt", [], ["libstdc++_vendor.so"]),
            ("odm/lib64/libXDocProcessSDK.so", "add", b"xdoc", [], ["libYTCommon.so"]),
            ("odm/lib64/libSuperTextWrapper.so", "add", b"st", [], ["libXDocProcessSDK.so"]),
        ])
        log = self.install()
        present = lambda p: staged(self.modpath, p).exists()
        self.assertTrue(present("odm/lib64/libAncFilter.so"))
        self.assertFalse(present("odm/lib64/libFDClite.so"), "device copy must stay")
        self.assertTrue(present("odm/lib64/libEIS.so"))
        self.assertTrue(present("odm/lib64/libui-oplus.so"))
        self.assertFalse(present("odm/lib64/libnightvision.so"), "unknown ROM build must stay")
        self.assertTrue(present("odm/lib/rfsa/adsp/libarcsoft_hdrplus_hvx_skel_lemonade.so"))
        for name in ("libYTCommon.so", "libXDocProcessSDK.so", "libSuperTextWrapper.so"):
            self.assertFalse(present("odm/lib64/" + name), name)
        self.assertIn("needs libstdc++_vendor.so", log)

    def test_per_device_variant(self):
        path = "odm/etc/camera/config/camera_unit_feature_config.protobuf"
        sha = lambda data: hashlib.sha256(data).hexdigest()
        for device, expected in (("lemonade", b"nine head"), ("lemonadep", b"pro head")):
            self.device_file(path, b"nine stock" if device == "lemonade" else b"pro stock")
            self.stage_libraries([
                (path, "replace", b"nine head", [sha(b"nine stock")], [], "lemonade"),
                (path, "replace", b"pro head", [sha(b"pro stock")], [], "lemonadep"),
            ])
            self.install(device=device)
            self.assertEqual(staged(self.modpath, path).read_bytes(), expected)
            self.assertFalse((self.modpath / "aox/variants").exists())
            staged(self.modpath, path).unlink()

    def test_running_module_library_is_provided_again(self):
        path = "odm/lib64/libAncFilter.so"
        self.device_file("system/lib64/libc.so", b"bionic")
        self.device_file(path, b"new")  # visible through the running module's overlay
        old = self.tmp / "old/vendor" / path
        old.parent.mkdir(parents=True)
        old.write_bytes(b"new")
        self.stage_libraries([(path, "add", b"new", [], ["libc.so"])])
        self.install()
        self.assertTrue(staged(self.modpath, path).exists())

    # --------------------------------------------------------------- app
    APK = "system/system_ext/priv-app/OplusCamera/OplusCamera.apk"
    JAR = "system/framework/oplus-fwk.jar"
    PAIR = "odm/lib64/libAlgoInterface.so"

    def stage_app(self, rom_camera=None, rom_markers=("Lfive/A;", "Lfive/B;")):
        """A staged 5.045.451 app with one paired library and the boot jar."""
        import zipfile
        self.device_file("system/lib64/libc.so", b"bionic")
        self.device_file(self.PAIR, b"rom algo")
        self.stage_libraries([(self.PAIR, "pair", b"5.x algo", [], ["libc.so"])])
        for path in (self.APK, self.JAR):
            (self.modpath / path).parent.mkdir(parents=True, exist_ok=True)
            (self.modpath / path).write_bytes(b"module")
        (self.modpath / "aox/app.txt").write_text(self.APK + "\n")
        (self.modpath / "aox/app-version.txt").write_text("5.045.451\n")
        (self.modpath / "aox/fwk-markers.txt").write_text("Lfive/A;\nLfive/B;\n")
        jar = self.root / self.JAR
        jar.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(jar, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("classes.dex", "".join(rom_markers) * 50)
        dump = self.tmp / "dump"
        if rom_camera:
            code, version = rom_camera
            (self.root / code.lstrip("/")).mkdir(parents=True, exist_ok=True)
            (self.root / code.lstrip("/") / "Cam.apk").write_bytes(b"rom")
            # An update under /data comes first; the system copy is what counts.
            dump.write_text("  Package [com.oplus.camera] (1):\n    codePath=/data/app/x/com.oplus.camera-1\n"
                            "    versionName=9.9.9\nHidden system packages:\n"
                            f"    codePath={code}\n    versionName={version}\n")
        else:
            dump.write_text("")
        return {"AOX_CAMERA_DUMP": str(dump)}

    def test_rom_without_camera_gets_app_pair_and_framework_decision(self):
        log = self.install(**self.stage_app())
        self.assertIn("app   no system OplusCamera", log)
        self.assertTrue((self.modpath / self.APK).exists())
        self.assertEqual(staged(self.modpath, self.PAIR).read_bytes(), b"5.x algo")
        self.assertFalse((self.modpath / self.JAR).exists(), "ROM jar already has the classes")

    def test_old_framework_is_overlaid(self):
        log = self.install(**self.stage_app(rom_markers=("Lfive/A;",)))
        self.assertIn("lacks Lfive/B;", log)
        self.assertTrue((self.modpath / self.JAR).exists())

    def test_rom_with_same_or_newer_camera_keeps_its_own(self):
        for version in ("5.045.451", "5.100.2"):
            env = self.stage_app(rom_camera=("/system_ext/priv-app/OplusCamera", version))
            log = self.install(**env)
            self.assertIn("keeping it, fixes only", log)
            self.assertFalse((self.modpath / self.APK).exists())
            self.assertFalse((self.modpath / "system/system_ext").exists(), "empty dirs pruned")
            self.assertFalse(staged(self.modpath, self.PAIR).exists())
            self.assertFalse((self.modpath / self.JAR).exists())

    def test_rom_with_older_camera_is_replaced_in_place(self):
        env = self.stage_app(rom_camera=("/product/priv-app/OnePlusCamera", "4.040.557"))
        log = self.install(**env)
        self.assertIn("replacing it with 5.045.451", log)
        self.assertFalse((self.modpath / self.APK).exists())
        self.assertEqual((self.modpath / "system/product/priv-app/OnePlusCamera/Cam.apk").read_bytes(),
                         b"module")
        self.assertTrue(staged(self.modpath, self.PAIR).exists())

    def test_camera_outside_the_overlaid_roots_stops_the_install(self):
        env = self.stage_app(rom_camera=("/vendor/app/OplusCamera", "4.040.557"))
        log = self.install(check=False, **env)
        self.assertEqual(self.status, 1)
        self.assertIn("cannot overlay", log)

    def test_running_module_camera_is_installed_again(self):
        env = self.stage_app(rom_camera=("/system_ext/priv-app/OplusCamera", "5.045.451"))
        (self.tmp / "old/system_ext/priv-app/OplusCamera").mkdir(parents=True)
        (self.tmp / "old/framework").mkdir(parents=True)
        (self.tmp / "old/framework/oplus-fwk.jar").write_bytes(b"old")
        log = self.install(**env)
        self.assertIn("is this module's", log)
        self.assertTrue((self.modpath / "system/system_ext/priv-app/OplusCamera/Cam.apk").exists())
        self.assertTrue((self.modpath / self.JAR).exists())

    def test_missing_pair_dependency_stops_the_install(self):
        env = self.stage_app()
        self.stage_libraries([(self.PAIR, "pair", b"5.x algo", [], ["libgone.so"])])
        log = self.install(check=False, **env)
        self.assertEqual(self.status, 1)
        self.assertIn("fail  /" + self.PAIR, log)

    def test_version_compare(self):
        for a, b, expected in (("5.045.451", "5.045.451", 0), ("5.045.452", "5.045.451", 0),
                               ("5.46.1", "5.045.451", 0), ("4.040.557", "5.045.451", 1),
                               ("5.045", "5.045.451", 1), ("6", "5.045.451", 0)):
            result = subprocess.run([SHELL, "sh", "-c", '. "$1"; aox_version_ge "$2" "$3"', "t",
                                     str(SCRIPT), a, b])
            self.assertEqual(result.returncode, expected, (a, b))

    def test_unused_adsp_overlay_is_removed(self):
        self.device_file("odm/lib/rfsa/adsp/libarcsoft_hdrplus_hvx_skel_lemonade.so", b"other skel")
        self.stage_libraries([
            ("odm/lib/rfsa/adsp/libarcsoft_hdrplus_hvx_skel_lemonade.so", "replace", b"stock skel",
             [hashlib.sha256(b"base skel").hexdigest()], []),
        ])
        self.install()
        self.assertFalse((self.modpath / "system/vendor/odm/lib/rfsa/adsp").exists())

    def test_stock_uah_client_is_never_replaced(self):
        self.device_file("system/lib64/libc.so", b"bionic")
        self.device_file("system/lib64/libdl.so", b"bionic")
        path = "odm/lib64/liboplus-uah-client.so"
        for device, kept in ((b"\x7fELF stub", True), (b"\x7fELF needs libuahcore.so", False), (None, True)):
            if device is None:
                (self.root / path).unlink()
            else:
                self.device_file(path, device)
            self.stage_libraries([(path, "uah", b"aox client", [], ["libc.so", "libdl.so"])])
            self.install()
            self.assertEqual(staged(self.modpath, path).exists(), kept, device)


@unittest.skipUnless(SHELL, "BusyBox is required")
class MountList(unittest.TestCase):
    def test_only_payload_directories_are_mounted(self):
        with tempfile.TemporaryDirectory() as tmp:
            for relative in ("framework", "system_ext/priv-app", "vendor/odm/lib64"):
                (pathlib.Path(tmp) / relative).mkdir(parents=True)
            out = subprocess.run([SHELL, "sh", "-c", '. "$1"; camera_mounts "$2"', "t",
                                  str(ROOT / "module/mount-camera.sh"), tmp],
                                 capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.splitlines(), ["framework /system/framework",
                                            "system_ext/priv-app /system_ext/priv-app",
                                            "vendor/odm/lib64 /odm/lib64"])


class BuildStaging(unittest.TestCase):
    def test_app_set_variants_and_files_list(self):
        if not (CACHE / "source.json").exists() or not shutil.which("apksigner"):
            self.skipTest("run scripts/prepare_aox.py; apksigner required")
        import build
        manifest = json.loads(build.AOX_MANIFEST.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            stage = pathlib.Path(tmp)
            owned = stage / "system/vendor/odm/lib64/libAncHumBokeh.so"
            owned.parent.mkdir(parents=True)
            owned.write_bytes(b"collected from the device")
            build.stage_aox(stage, CACHE, None)
            self.assertEqual(owned.read_bytes(), b"collected from the device")
            source = json.loads((stage / "aox-source.json").read_text())
            self.assertIn("odm/lib64/libAncHumBokeh.so", source["module_provided"])
            for path in (stage / "aox/app.txt").read_text().split():
                self.assertTrue((stage / path).is_file(), path)
            apk = stage / "system" / build.CAMERA_APK
            subprocess.run(["apksigner", "verify", "--min-sdk-version", "30", str(apk)], check=True)
            build.check_apk_alignment(apk)
            rows = [line.split("|") for line in (stage / "aox/files.txt").read_text().splitlines()
                    if not line.startswith("#")]
            self.assertEqual(sorted(e["path"] for e in manifest["files"]
                                    if e["group"] != "app" and e["path"] != "odm/lib64/libAncHumBokeh.so"),
                             sorted(row[0] for row in rows))
            for row in rows:
                target = (stage / "aox/variants" / row[5] / row[0]) if row[5] else build.aox_target(stage, row[0])
                data = target.read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), row[2])
                if row[0].endswith(".so") and "/lib64/" in row[0]:  # elf_needed reads AArch64
                    self.assertEqual(row[4].split(","), build.elf_needed(data), row[0])
            self.assertEqual({row[5] for row in rows if row[5]}, {"lemonade", "lemonadep"})
            self.assertTrue((stage / "sepolicy.rule").exists())
            self.assertTrue((stage / "aox/blocks/video-120fps-rear-main.old").exists())


@unittest.skipUnless(shutil.which("clang") and shutil.which("ld.lld"), "clang and lld required")
class UahClient(unittest.TestCase):
    def test_device_build(self):
        import build
        with tempfile.TemporaryDirectory() as tmp:
            first, second = pathlib.Path(tmp) / "a.so", pathlib.Path(tmp) / "b.so"
            for output in (first, second):
                subprocess.run(["sh", str(ROOT / "native/uah-client/build.sh"), str(output)],
                               check=True, capture_output=True)
            data = first.read_bytes()
            self.assertEqual(data, second.read_bytes(), "build must be reproducible")
            self.assertEqual(build.elf_needed(data), ["libc.so", "libdl.so"])
            for symbol in build.UAH_CLIENT_SYMBOLS:
                self.assertIn(symbol.encode() + b"\0", data)

    def test_libcxx_string_layout(self):
        probe = subprocess.run(["clang++", "-stdlib=libc++", "-x", "c++", "-fsyntax-only", "-"],
                               input="#include <string>\n", text=True, capture_output=True)
        if probe.returncode:
            self.skipTest("host libc++ headers required")
        harness = r'''
#include <cstdio>
#include <cstdlib>
#include <string>
extern "C" char* uah_test_join(const void*, const void*);
extern "C" int uah_test_mode(const char*);
int main() {
    const std::string cases[][2] = {
        {"", ""}, {"CAMERA", "OPEN"},
        {"OSENSE_ACTION_CAMERA_VIDEO_4K_RECORDING_SCENE_WITH_A_LONG_NAME", "start"},
        {std::string(22, 's'), std::string(23, 'l')}};
    for (const auto& c : cases) {
        char* joined = uah_test_join(&c[0], &c[1]);
        if ((c[0] + " " + c[1]) != joined) { std::printf("bad join\n"); return 1; }
        std::free(joined);
    }
    if (uah_test_mode("OSENSE_ACTION_CAMERA_VIDEO_4K") != 14) return 2;
    if (uah_test_mode("OSENSE_ACTION_CAMERA_VIDEO") != 13) return 3;
    if (uah_test_mode("OSENSE_ACTION_CAMERA_PREVIEW") != 12) return 4;
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            (tmp / "harness.cpp").write_text(harness)
            subprocess.run(["clang", "-c", "-DUAH_HOST_TEST", "-fPIC", "-fno-builtin",
                            str(ROOT / "native/uah-client/uah_client.c"), "-o", str(tmp / "uah.o")],
                           check=True)
            subprocess.run(["clang++", "-stdlib=libc++", str(tmp / "harness.cpp"), str(tmp / "uah.o"),
                            "-o", str(tmp / "harness"), "-ldl", "-lpthread"], check=True)
            subprocess.run([str(tmp / "harness")], check=True)


if __name__ == "__main__":
    unittest.main()
