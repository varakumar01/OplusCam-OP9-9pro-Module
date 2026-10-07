"""Check package ownership parsing without ADB or privileged mutations."""
import pathlib
import shlex
import subprocess
import tempfile
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "module/visibility.sh"


class OwnershipParsing(unittest.TestCase):
    def run_owner(self, listing, package="com.oplus.camera", unusual_ifs=False):
        script = ("IFS='\n'\n" if unusual_ifs else "")
        script += "cmd() { cat; }; . " + shlex.quote(str(SOURCE))
        script += '; camera_owner_uid "$1"'
        return subprocess.run(["sh", "-c", script, "test", package], input=listing,
                              text=True, check=True, capture_output=True).stdout.strip()

    def test_exact_package_not_overlays(self):
        listing = ("package:com.oplus.camera.overlay uid:10333\n"
                   "package:com.oplus.camera uid:10192\n"
                   "package:com.oplus.camera.extra uid:10444\n")
        self.assertEqual(self.run_owner(listing), "10192")

    def test_crlf_and_inherited_ifs(self):
        self.assertEqual(self.run_owner("package:com.oplus.camera uid:10192\r\n",
                                        unusual_ifs=True), "10192")

    def test_absent_package(self):
        self.assertEqual(self.run_owner("package:other.camera uid:10222\n"), "")

    def test_invalid_uid_never_invokes_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = pathlib.Path(directory) / "helper-called"
            script = "cmd() { cat; }; . " + shlex.quote(str(SOURCE))
            script += "; fake_helper() { touch " + shlex.quote(str(marker)) + "; }"
            script += "; CAMERA_VISIBILITY_TOOL=fake_helper; camera_enable_visibility com.oplus.camera"
            for uid in ("-1", "unknown", "10192\rmalformed"):
                result = subprocess.run(["sh", "-c", script],
                                        input=f"package:com.oplus.camera uid:{uid}\n",
                                        text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
