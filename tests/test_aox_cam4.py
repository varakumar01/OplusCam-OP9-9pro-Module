"""Host checks for the aox-cam4 installer logic, build staging and uah client.

Configuration tests need the pinned fixtures:
    python scripts/prepare_aox_cam4.py --fixtures
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
CACHE = ROOT / ".cache/aox-cam4"
FIXTURES = CACHE / "fixtures"
SCRIPT = ROOT / "module/aox-cam4.sh"
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
        shutil.copytree(ROOT / "module/aox-cam4", self.modpath / "aox-cam4")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def install(self):
        script = ("ui_print() { :; }; . \"$1\"; aox_cam4_install")
        env = dict(os.environ, MODPATH=str(self.modpath), AOX_ROOT=str(self.root))
        subprocess.run([SHELL, "sh", "-c", script, "test", str(SCRIPT)], env=env, check=True)
        return (self.modpath / "aox-cam4.log").read_text()

    def device_file(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    # ----------------------------------------------------------- configs
    def fixtures(self):
        if not (FIXTURES / "base" / CONFIGS[0]).exists():
            self.skipTest("run scripts/prepare_aox_cam4.py --fixtures")
        for path in CONFIGS + [MEDIA]:
            self.device_file(path, (FIXTURES / "base" / path).read_bytes())

    def test_base_configs_become_head(self):
        self.fixtures()
        log = self.install()
        self.assertNotIn("skip", log)
        for path in CONFIGS:
            result = staged(self.modpath, path).read_bytes()
            head = (FIXTURES / "head" / path).read_bytes()
            if path.endswith("oplus_camera_config"):
                # New tags are appended rather than inserted mid-file.
                tags = lambda data: {e["VendorTag"]: e for e in json.loads(data)}
                self.assertEqual(tags(result), tags(head), path)
            else:
                self.assertEqual(result, head, path)
        media = self.modpath / "aox-cam4/media" / MEDIA
        self.assertEqual(media.read_bytes(), (FIXTURES / "head" / MEDIA).read_bytes())

    def test_second_install_is_a_no_op(self):
        self.fixtures()
        self.install()
        first = {p: staged(self.modpath, p).read_bytes() for p in CONFIGS}
        log = self.install()
        self.assertNotIn("apply odm", log)
        self.assertEqual(first, {p: staged(self.modpath, p).read_bytes() for p in CONFIGS})

    def test_head_device_needs_no_config_copy(self):
        if not (FIXTURES / "head" / CONFIGS[0]).exists():
            self.skipTest("run scripts/prepare_aox_cam4.py --fixtures")
        for path in CONFIGS + [MEDIA]:
            self.device_file(path, (FIXTURES / "head" / path).read_bytes())
        log = self.install()
        self.assertNotIn("apply", log)
        self.assertFalse(any(staged(self.modpath, p).exists() for p in CONFIGS))
        self.assertFalse((self.modpath / "aox-cam4/media").exists())

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
        old = (ROOT / "module/aox-cam4/blocks/video-120fps-rear-main.old").read_bytes()
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
        for path, rule, data, replace, needed in rows:
            target = staged(self.modpath, path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            lines.append("|".join([path, rule, hashlib.sha256(data).hexdigest(),
                                   ",".join(replace), ",".join(needed)]))
        (self.modpath / "aox-cam4/files.txt").write_text("\n".join(lines) + "\n")
        (self.modpath / "aox-cam4/edits.txt").write_text("")

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


class BuildStaging(unittest.TestCase):
    def test_module_payload_wins_and_files_list(self):
        if not (CACHE / "source.json").exists():
            self.skipTest("run scripts/prepare_aox_cam4.py")
        import build
        manifest = json.loads(build.AOX_CAM4_MANIFEST.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            stage = pathlib.Path(tmp)
            owned = stage / "system/vendor/odm/lib64/libAncHumBokeh.so"
            owned.parent.mkdir(parents=True)
            owned.write_bytes(b"module blur engine")
            build.stage_aox_cam4(stage, CACHE, None)
            self.assertEqual(owned.read_bytes(), b"module blur engine")
            source = json.loads((stage / "aox-cam4-source.json").read_text())
            self.assertIn("odm/lib64/libAncHumBokeh.so", source["module_provided"])
            for path in manifest["module_owned"]:
                self.assertFalse(build.aox_cam4_target(stage, path).exists(), path)
            rows = [line.split("|") for line in (stage / "aox-cam4/files.txt").read_text().splitlines()
                    if not line.startswith("#")]
            self.assertEqual({row[0] for row in rows}, set(source["files"]))
            for row in rows:
                data = build.aox_cam4_target(stage, row[0]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), row[2])
                if "/lib64/" in row[0]:  # elf_needed reads AArch64 libraries
                    self.assertEqual(row[4].split(","), build.elf_needed(data), row[0])
            self.assertTrue((stage / "sepolicy.rule").exists())
            self.assertTrue((stage / "aox-cam4/blocks/video-120fps-rear-main.old").exists())


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
