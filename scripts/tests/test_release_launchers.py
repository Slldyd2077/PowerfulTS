"""Exercise launcher initialization without requiring a Docker daemon."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[2] / "deploy/release"


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="powerful ts ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("powerfults.ps1", "powerfults.sh"):
            shutil.copyfile(TEMPLATES / name, self.root / name)
        (self.root / ".release-version").write_text("1.2.3\n")
        (self.root / "backend.env.example").write_text("TS3_QUERY_PASSWORD=\n")

    def assert_preserved_init(self, command):
        subprocess.run([*command, "init"], check=True, capture_output=True, text=True)
        self.assertTrue((self.root / "data").is_dir())
        config = self.root / "backend.env"
        self.assertEqual(config.read_text(), "TS3_QUERY_PASSWORD=\n")
        config.write_text("TS3_QUERY_PASSWORD=keep-private\n")
        marker = self.root / "data/persist.txt"
        marker.write_text("keep-data\n")
        subprocess.run([*command, "init"], check=True, capture_output=True, text=True)
        self.assertEqual(config.read_text(), "TS3_QUERY_PASSWORD=keep-private\n")
        self.assertEqual(marker.read_text(), "keep-data\n")

    def test_powershell_init_preserves_existing_config_and_data(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            self.skipTest("PowerShell not installed on this test host")
        self.assert_preserved_init([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.root / "powerfults.ps1")])

    def test_first_start_only_initializes_config(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            self.skipTest("PowerShell not installed on this test host")
        result = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.root / "powerfults.ps1"), "start"], check=True, capture_output=True, text=True)
        self.assertIn("Edit backend.env", result.stdout)
        self.assertTrue((self.root / "backend.env").is_file())

    @unittest.skipUnless(os.name == "nt", "Windows native stderr behavior")
    def test_powershell_imports_missing_images_despite_native_stderr(self):
        shell = shutil.which("powershell")
        if not shell:
            self.skipTest("Windows PowerShell not installed")
        self.assert_preserved_init([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.root / "powerfults.ps1")])
        (self.root / "images.tar").write_bytes(b"fixture")
        (self.root / ".release-arch").write_text("amd64\n")
        (self.root / "docker.cmd").write_text(
            '@echo off\n'
            'echo %*>>"%MOCK_DOCKER_LOG%"\n'
            'if "%1"=="image" (echo missing image 1>&2 & exit /b 1)\n'
            'if "%2"=="--format" echo x86_64\n'
            'exit /b 0\n'
        )
        log = self.root / "calls.log"
        env = dict(os.environ, PATH=f"{self.root}{os.pathsep}{os.environ['PATH']}", MOCK_DOCKER_LOG=str(log))
        result = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(self.root / "powerfults.ps1"), "start"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("load --input images.tar", log.read_text())

    @unittest.skipIf(os.name == "nt", "POSIX shell tested on Linux/macOS")
    def test_shell_init_preserves_existing_config_and_data(self):
        self.assert_preserved_init(["sh", str(self.root / "powerfults.sh")])

    @unittest.skipIf(os.name == "nt", "POSIX shell tested on Linux/macOS")
    def test_shell_prebuilt_start_and_stop_preserve_data(self):
        self.assert_preserved_init(["sh", str(self.root / "powerfults.sh")])
        (self.root / "images.tar").write_bytes(b"fixture")
        (self.root / ".release-arch").write_text("amd64\n")
        docker = self.root / "docker"
        docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$MOCK_DOCKER_LOG"\ncase "$*" in\n "info --format {{.Architecture}}") echo x86_64 ;;\n "image inspect "*) exit 1 ;;\nesac\n')
        docker.chmod(0o755)
        log = self.root / "calls.log"
        env = dict(os.environ, PATH=f"{self.root}{os.pathsep}{os.environ['PATH']}", MOCK_DOCKER_LOG=str(log))
        for action in ("start", "stop"):
            subprocess.run(["sh", str(self.root / "powerfults.sh"), action], env=env, check=True, capture_output=True, text=True)
        calls = log.read_text()
        self.assertIn("load --input images.tar", calls)
        self.assertIn("up -d --no-build --pull never --wait", calls)
        self.assertIn("compose --project-directory", calls)
        self.assertIn("down", calls)
        self.assertNotIn("--volumes", calls)
        self.assertTrue((self.root / "backend.env").is_file())
        self.assertTrue((self.root / "data").is_dir())


if __name__ == "__main__":
    unittest.main()
