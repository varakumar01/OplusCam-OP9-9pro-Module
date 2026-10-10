"""Profile versions 3 and 4 against a stand-in for the kernel's get/set rules."""
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("cc"), "no host C compiler")
class ProfileVersions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.binary = pathlib.Path(cls.directory.name) / "fake-kernel"
        subprocess.run(["cc", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function",
                        str(ROOT / "tests/visibility_fake_kernel.c"), "-o", str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def run_case(self, version, state):
        return subprocess.run([str(self.binary), str(version), state], capture_output=True, text=True)

    def test_supported_versions(self):
        for version in (3, 4):
            for state in ("absent", "present"):
                result = self.run_case(version, state)
                self.assertEqual(result.returncode, 0, f"v{version} {state}: {result.stderr}")

    def test_unknown_version_changes_nothing(self):
        # A profile the helper cannot read, or a kernel that refuses 3 and 4.
        for state in ("absent", "present"):
            result = self.run_case(5, state)
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertNotIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
