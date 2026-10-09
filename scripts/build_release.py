#!/usr/bin/env python3
"""Build allowlisted Docker release archives using only the Python standard library."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import shutil
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = (
    "compose.yml", "powerfults.ps1", "powerfults.sh", "start.cmd", "stop.cmd",
    "start.sh", "stop.sh", "README.md",
)
SOURCE_FILES = (
    "backend/Dockerfile", "backend/requirements.txt", "backend/requirements.lock.txt", "frontend/Dockerfile",
    "frontend/package.json", "frontend/pnpm-lock.yaml", "frontend/nginx.conf",
    "frontend/index.html", "frontend/vite.config.ts", "frontend/tsconfig.json",
    "frontend/tsconfig.app.json", "frontend/tsconfig.node.json",
    "frontend/scripts/package-watch-extension.mjs",
    "frontend/watch-extension/manifest.json", "frontend/watch-extension/popup.html",
    "frontend/watch-extension/popup.js", "frontend/watch-extension/background.js",
    "frontend/watch-extension/dashboard.js", "frontend/watch-extension/identity.js",
    "frontend/watch-extension/video.js",
)
SOURCE_TREES = {
    "backend/app": {".py"},
    "frontend/src": {".ts", ".vue", ".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".woff", ".woff2"},
    "frontend/public": {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff", ".woff2"},
}


def read_version(root: Path, tag: str | None) -> str:
    versions = []
    for name in ("pyproject.toml", "backend/pyproject.toml", "backend/app/_version.py"):
        pattern = r'^(?:version|__version__)\s*=\s*"([^"]+)"'
        match = re.search(pattern, (root / name).read_text(encoding="utf-8"), re.MULTILINE)
        if not match:
            raise ValueError(f"Missing version in {name}")
        versions.append(match.group(1))
    versions.append(json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))["version"])
    if len(set(versions)) != 1 or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", versions[0]):
        raise ValueError(f"Invalid or inconsistent version: {versions}")
    if tag and tag != f"v{versions[0]}":
        raise ValueError(f"Release tag {tag!r} must equal v{versions[0]}")
    return versions[0]


def checked_file(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError(f"Symlinks are not distributable: {path}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def validate_images(path: Path, version: str, arch: str) -> None:
    expected = {f"powerfults-{service}:{version}" for service in ("backend", "frontend")}
    try:
        with tarfile.open(path, "r:") as archive:
            manifest = archive.extractfile("manifest.json")
            if manifest is None:
                raise ValueError("Missing Docker manifest.json")
            entries = json.loads(manifest.read(1024 * 1024))
            if not isinstance(entries, list):
                raise ValueError("Docker manifest must be a list")
            found = set()
            for entry in entries:
                tags = set(entry.get("RepoTags") or [])
                matched = tags & expected
                if not matched:
                    continue
                config_file = archive.extractfile(entry["Config"])
                if config_file is None:
                    raise ValueError("Missing Docker image config")
                config = json.loads(config_file.read(1024 * 1024))
                if config.get("os") != "linux" or config.get("architecture") != arch:
                    raise ValueError(f"Image architecture must be linux/{arch}: {matched}")
                found |= matched
            if found != expected:
                raise ValueError(f"Missing image tags: {sorted(expected - found)}")
    except (tarfile.TarError, KeyError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid Docker image archive: {path}") from exc


def payload(root: Path, version: str, images: Path | None, arch: str) -> dict[str, bytes | Path]:
    files: dict[str, bytes | Path] = {
        name: checked_file(root / "deploy/release" / name) for name in TEMPLATES
    }
    for name in TEMPLATES:
        if name.endswith(".sh"):
            files[name] = (root / "deploy/release" / name).read_bytes().replace(b"\r\n", b"\n")
    files["LICENSE"] = checked_file(root / "LICENSE")
    files[".release-version"] = f"{version}\n".encode()
    files[".release-arch"] = f"{arch if images else 'any'}\n".encode()
    config = checked_file(root / "backend/.env.example").read_text(encoding="utf-8")
    defaults = {
        "TS3_HOST": "host.docker.internal", "TSMUSIC_URL": "http://host.docker.internal:3000",
        "NETEASE_API_URL": "http://host.docker.internal:3001", "NAPCAT_URL": "",
        "CORS_ORIGINS": "http://localhost:8080,http://127.0.0.1:8080",
    }
    for key, value in defaults.items():
        config = re.sub(rf"^{key}=.*$", f"{key}={value}", config, flags=re.MULTILINE)
    files["backend.env.example"] = config.replace("\r\n", "\n").encode()
    if images:
        files["images.tar"] = checked_file(images)
        validate_images(images, version, arch)
        return files
    files.update({name: checked_file(root / name) for name in SOURCE_FILES})
    for name in ("backend/.dockerignore", "frontend/.dockerignore"):
        if (root / name).exists():
            files[name] = checked_file(root / name)
    for directory, extensions in SOURCE_TREES.items():
        for path in sorted((root / directory).rglob("*")):
            relative = path.relative_to(root)
            if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
                continue
            if path.suffix.lower() in extensions:
                files[relative.as_posix()] = checked_file(path)
    return files


def _input(value: bytes | Path):
    return io.BytesIO(value) if isinstance(value, bytes) else value.open("rb")


def write_archives(output: Path, name: str, prefix: str, files: dict[str, bytes | Path]) -> list[Path]:
    zipped, tarred = output / f"{name}.zip", output / f"{name}.tar.gz"
    with zipfile.ZipFile(zipped, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, value in sorted(files.items()):
            entry = zipfile.ZipInfo(f"{prefix}/{name}")
            entry.create_system = 3
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
            with _input(value) as source, archive.open(entry, "w", force_zip64=True) as target:
                shutil.copyfileobj(source, target)
    with tarred.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as archive:
            for name, value in sorted(files.items()):
                entry = tarfile.TarInfo(f"{prefix}/{name}")
                entry.size = len(value) if isinstance(value, bytes) else value.stat().st_size
                entry.mode = 0o755 if name.endswith(".sh") else 0o644
                with _input(value) as source:
                    archive.addfile(entry, source)
    return [zipped, tarred]


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build_release(root: Path, output: Path, *, images: Path | None = None, arch: str = "amd64", tag: str | None = None) -> list[Path]:
    if arch not in {"amd64", "arm64"}:
        raise ValueError(f"Unsupported arch: {arch}")
    version = read_version(root, tag)
    files = payload(root, version, images, arch)
    output.mkdir(parents=True, exist_ok=True)
    flavor = arch if images else "source"
    archives = write_archives(output, f"powerfults-v{version}-docker-{flavor}", f"powerfults-{version}", files)
    sums = output / "SHA256SUMS"
    sums.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sorted(output.glob("powerfults-*.zip")) + sorted(output.glob("powerfults-*.tar.gz"))), encoding="utf-8")
    return [*archives, sums]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / ".release")
    parser.add_argument("--images", type=Path, help="docker save archive with both version-tagged images")
    parser.add_argument("--arch", choices=("amd64", "arm64"), default="amd64")
    parser.add_argument("--tag", help="CI tag; must match all four application versions")
    args = parser.parse_args()
    try:
        for path in build_release(args.root, args.output, images=args.images, arch=args.arch, tag=args.tag):
            print(path)
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(1, f"release: {exc}\n")


if __name__ == "__main__":
    main()
