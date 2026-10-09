"""Release archives must contain only distributable inputs, never local state."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import tempfile
import tarfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "build_release.py"
spec = importlib.util.spec_from_file_location("build_release", SCRIPT)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.output = Path(self.tmp.name) / "out"
        paths = {
            "pyproject.toml": '[project]\nversion = "1.2.3"\n',
            "backend/pyproject.toml": '[project]\nversion = "1.2.3"\n',
            "backend/app/_version.py": '__version__ = "1.2.3"\n',
            "backend/app/main.py": "# application\n",
            "backend/Dockerfile": "FROM python:3.12-slim\n",
            "backend/requirements.txt": "fastapi==0.115.0\n",
            "backend/requirements.lock.txt": "fastapi==0.115.0\n",
            "backend/.env.example": "TS3_HOST=127.0.0.1\nNAPCAT_URL=http://127.0.0.1:3000\n",
            "frontend/package.json": json.dumps({"version": "1.2.3"}),
            "frontend/pnpm-lock.yaml": "lockfileVersion: '9.0'\n",
            "frontend/Dockerfile": "FROM nginx:alpine\n",
            "frontend/nginx.conf": "server {}\n",
            "frontend/index.html": "<div id='app'></div>\n",
            "frontend/vite.config.ts": "export default {}\n",
            "frontend/tsconfig.json": "{}\n",
            "frontend/tsconfig.app.json": "{}\n",
            "frontend/tsconfig.node.json": "{}\n",
            "frontend/src/main.ts": "console.log('app')\n",
            "frontend/public/logo.svg": "<svg/>\n",
            "LICENSE": "MIT\n",
        }
        templates = Path(__file__).resolve().parents[2] / "deploy/release"
        for item in templates.iterdir():
            if item.is_file():
                paths[f"deploy/release/{item.name}"] = item.read_text(encoding="utf-8")
        paths.update({
            "backend/.env": "PASSWORD=secret\n",
            "backend/data/private.db": "database\n",
            "backend/app/__pycache__/main.pyc": "cache\n",
            "frontend/src/.env": "secret\n",
            "frontend/node_modules/private.js": "dependency\n",
            "frontend/public/private.db": "database\n",
            ".release/old.zip": "old release\n",
        })
        for name, value in paths.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
        for name in release.SOURCE_FILES:
            path = self.root / name
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("extension build fixture", encoding="utf-8")

    def test_source_archive_excludes_state_and_has_start_and_stop(self):
        artifacts = release.build_release(self.root, self.output, tag="v1.2.3")
        archive = next(path for path in artifacts if path.suffix == ".zip")
        with zipfile.ZipFile(archive) as zipped:
            names = {name.split("/", 1)[1] for name in zipped.namelist()}
            self.assertIn("backend/app/main.py", names)
            self.assertIn("frontend/src/main.ts", names)
            self.assertIn("frontend/scripts/package-watch-extension.mjs", names)
            self.assertIn("frontend/watch-extension/manifest.json", names)
            self.assertIn("frontend/watch-extension/video.js", names)
            self.assertTrue({"start.cmd", "stop.cmd", "start.sh", "stop.sh", "compose.yml", "backend.env.example"} <= names)
            self.assertFalse(any(name.endswith((".db", ".pyc")) or "node_modules" in name or name.endswith("/.env") for name in names))
            config = zipped.read("powerfults-1.2.3/backend.env.example").decode()
            self.assertIn("TS3_HOST=host.docker.internal", config)
            self.assertIn("NAPCAT_URL=\n", config)
            self.assertEqual(zipped.read("powerfults-1.2.3/.release-version"), b"1.2.3\n")
            self.assertEqual((zipped.getinfo("powerfults-1.2.3/start.sh").external_attr >> 16) & 0o777, 0o755)
        sums = (self.output / "SHA256SUMS").read_text()
        self.assertIn(f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}", sums)

    def test_prebuilt_archive_includes_images_without_source(self):
        images = self.create_images()
        artifacts = release.build_release(self.root, self.output, images=images, arch="arm64")
        archive = next(path for path in artifacts if path.suffix == ".zip")
        self.assertIn("arm64", archive.name)
        with zipfile.ZipFile(archive) as zipped:
            self.assertEqual(zipped.read("powerfults-1.2.3/images.tar"), images.read_bytes())
            self.assertEqual(zipped.read("powerfults-1.2.3/.release-arch"), b"arm64\n")
            self.assertFalse(any("/backend/app/" in name for name in zipped.namelist()))

    def create_images(self, arch="arm64", version="1.2.3"):
        images = Path(self.tmp.name) / "images.tar"
        manifest = [{"Config": "config.json", "RepoTags": [f"powerfults-{name}:{version}"], "Layers": []} for name in ("backend", "frontend")]
        with tarfile.open(images, "w") as archive:
            for name, content in {
                "manifest.json": json.dumps(manifest).encode(),
                "config.json": json.dumps({"os": "linux", "architecture": arch}).encode(),
            }.items():
                item = tarfile.TarInfo(name)
                item.size = len(content)
                archive.addfile(item, io.BytesIO(content))
        return images

    def test_prebuilt_archive_rejects_wrong_tags_and_architecture(self):
        with self.assertRaisesRegex(ValueError, "tags"):
            release.build_release(self.root, self.output, images=self.create_images(version="0.1.0"), arch="arm64")
        with self.assertRaisesRegex(ValueError, "architecture"):
            release.build_release(self.root, self.output, images=self.create_images(arch="amd64"), arch="arm64")
        self.assertFalse(self.output.exists())

    def test_prebuilt_archive_rejects_non_image_tar(self):
        images = Path(self.tmp.name) / "images.tar"
        images.write_bytes(b"not a Docker archive")
        with self.assertRaisesRegex(ValueError, "Invalid Docker"):
            release.build_release(self.root, self.output, images=images)

    def test_windows_checkout_shell_line_endings_normalized(self):
        path = self.root / "deploy/release/powerfults.sh"
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        archive = release.build_release(self.root, self.output)[0]
        with zipfile.ZipFile(archive) as zipped:
            script = zipped.read("powerfults-1.2.3/powerfults.sh")
            self.assertNotIn(b"\r", script)
            self.assertTrue(script.startswith(b"#!/bin/sh\n"))

    def test_version_drift_and_tag_mismatch_rejected_before_packaging(self):
        with self.assertRaisesRegex(ValueError, "tag"):
            release.build_release(self.root, self.output, tag="v9.0.0")
        (self.root / "backend/app/_version.py").write_text('__version__ = "1.2.4"\n')
        with self.assertRaisesRegex(ValueError, "version"):
            release.build_release(self.root, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_mandatory_input_fails(self):
        (self.root / "frontend/pnpm-lock.yaml").unlink()
        with self.assertRaises(FileNotFoundError):
            release.build_release(self.root, self.output)

    def test_invalid_arch_rejected(self):
        with self.assertRaisesRegex(ValueError, "arch"):
            release.build_release(self.root, self.output, arch="riscv64")


if __name__ == "__main__":
    unittest.main()
