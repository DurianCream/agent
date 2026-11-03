"""Explicit approved-file rootfs copy; default plan only, no package or host binds."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys

PARENT = PurePosixPath("/var/lib/multi-p2/rootfs")
SOURCE_PREFIXES = (PurePosixPath("/usr/bin"), PurePosixPath("/usr/lib"))
GATE = PurePosixPath("/opt/multi-p2/runtime/p2_sandbox_gate.py")
MAX_FILES = 10000
MAX_BYTES = 512 * 1024 * 1024


def require(value, code):
    if not value: raise ValueError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "rootfs_duplicate_json_key")
        result[key] = value
    return result


def validate_manifest(value):
    require(type(value) is dict and set(value) == {"schema_version", "files"} and value["schema_version"] == "0.1.0", "rootfs_manifest_fields")
    require(type(value["files"]) is list and 1 <= len(value["files"]) <= MAX_FILES, "rootfs_manifest_count")
    seen = set()
    for row in value["files"]:
        require(type(row) is dict and set(row) == {"source", "destination", "sha256", "executable"}, "rootfs_file_fields")
        require(type(row["source"]) is str and type(row["destination"]) is str and type(row["sha256"]) is str, "rootfs_file_types")
        source = PurePosixPath(row["source"]); target = PurePosixPath(row["destination"])
        require(source.is_absolute() and ".." not in source.parts and (source == GATE or any(prefix in source.parents for prefix in SOURCE_PREFIXES)), "runtime_source_allowlist")
        require(bool(target.parts) and not target.is_absolute() and len(target.parts) <= 16 and target.as_posix() == row["destination"] and all(part not in ("", ".", "..") for part in target.parts), "rootfs_destination")
        require(target.parts[0] in ("usr", "lib", "lib64", "bin", "p2", "etc"), "rootfs_private_destination")
        require(row["destination"] not in {"etc/shadow", "etc/gshadow", "etc/gitconfig", "etc/ld.so.preload"} and not row["destination"].startswith("etc/ssh/") and target.name not in {".gitconfig", ".git-credentials"}, "rootfs_credential_destination")
        require(row["destination"] not in seen and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) is not None and type(row["executable"]) is bool, "rootfs_duplicate_or_digest")
        seen.add(row["destination"])
    require({"usr/bin/python3", "p2/sandbox_gate.py"} <= seen, "rootfs_gate_runtime_required")
    gate = next(row for row in value["files"] if row["destination"] == "p2/sandbox_gate.py")
    require(PurePosixPath(gate["source"]) == GATE, "rootfs_gate_source")
    for target in seen:
        require(not any(parent.as_posix() in seen for parent in PurePosixPath(target).parents if parent.as_posix() != "."), "rootfs_path_conflict")
    return "image-" + digest(value)


def trusted(path, directory=False):
    for part in [*reversed(path.parents), path]:
        info = part.lstat()
        require(info.st_uid == 0 and not stat.S_ISLNK(info.st_mode) and info.st_mode & 0o022 == 0, "rootfs_trusted_path")
        require(stat.S_ISDIR(info.st_mode) if part != path or directory else stat.S_ISREG(info.st_mode), "rootfs_trusted_type")


def prepare(value, *, apply=False, expected_digest=None):
    image = validate_manifest(value)
    result = {"mode": "plan", "effects_performed": False, "manifest_sha256": digest(value), "destination": str(PARENT / image),
              "file_count": len(value["files"]), "credential_free_approval_required": True, "isolation_verified": False}
    if not apply: return result
    require(sys.platform == "linux" and os.geteuid() == 0 and sys.flags.isolated and sys.flags.no_site, "rootfs_trusted_root_required")
    trusted(Path(__file__).absolute()); trusted(Path(sys.executable)); trusted(Path(PARENT), directory=True)
    require(expected_digest == digest(value), "operator_rootfs_manifest_approval_required")
    destination = Path(PARENT) / image
    require(not os.path.lexists(destination), "rootfs_destination_exists")
    captured = []; total = 0
    for row in value["files"]:
        source = Path(row["source"]); trusted(source)
        info = source.lstat(); require(info.st_nlink == 1 and not info.st_mode & 0o6000 and info.st_mode & 0o004 and info.st_size <= 64 * 1024 * 1024, "rootfs_source_type")
        require(not row["executable"] or info.st_mode & 0o111, "rootfs_source_not_executable")
        with source.open("rb") as stream: data = stream.read(64 * 1024 * 1024 + 1)
        total += len(data); require(total <= MAX_BYTES and len(data) == info.st_size, "rootfs_source_size")
        require(hashlib.sha256(data).hexdigest() == row["sha256"], "rootfs_source_changed")
        captured.append((row, data))
    destination.mkdir(mode=0o700)
    try:
        for name in ("input", "output", "tmp", "dev", "proc", "sys", "run", "home", "root", "var"):
            (destination / name).mkdir(mode=0o755)
        for row, data in captured:
            target = destination.joinpath(*PurePosixPath(row["destination"]).parts)
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(os.dup(fd), "wb") as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
                os.fchown(fd, 0, 0); os.fchmod(fd, 0o555 if row["executable"] else 0o444)
            finally: os.close(fd)
            require(hashlib.sha256(target.read_bytes()).hexdigest() == row["sha256"], "rootfs_copy_readback")
        for directory in [p for p in destination.rglob("*") if p.is_dir()]: os.chmod(directory, 0o755)
        os.chmod(destination, 0o755)
        return {**result, "mode": "copied", "effects_performed": True,
                "next_action": "Independently compute executor.rootfs_digest and approve config before any launch; copying is not isolation evidence."}
    except Exception:
        raise ValueError("partial_rootfs_preserved_for_operator") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args(argv)
    try:
        if args.apply:
            require(sys.platform == "linux" and os.geteuid() == 0 and sys.flags.isolated and sys.flags.no_site, "rootfs_trusted_root_required")
        if args.apply: trusted(args.manifest.absolute())
        with args.manifest.open("rb") as stream: data = stream.read(2 * 1024 * 1024 + 1)
        require(len(data) <= 2 * 1024 * 1024, "rootfs_manifest_limit")
        print(json.dumps(prepare(json.loads(data, object_pairs_hook=unique), apply=args.apply, expected_digest=args.expected_manifest_sha256), sort_keys=True))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"status": "blocked", "code": str(error), "isolation_verified": False}))
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
