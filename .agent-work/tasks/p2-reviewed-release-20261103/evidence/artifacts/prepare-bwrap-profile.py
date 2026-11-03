"""One-off root-operated P2 bubblewrap AppArmor exception preparation.

No sysctl, executor configuration, service start, or existing resource changes.
Run only from independently approved root-protected staging with -I -S -B.
"""
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

CONFIG = Path('/etc/multi-p2/executor.json')
BIN_DIR = Path('/opt/multi-p2/bin')
BINARY = BIN_DIR / 'bwrap'
PROFILE = Path('/etc/apparmor.d/multi-p2-bwrap')
PARSER = Path('/usr/sbin/apparmor_parser')
PROFILE_BYTES = b'''abi <abi/4.0>,
include <tunables/global>

# Application-specific user namespace exception, not a complete sandbox.
profile multi-p2-bwrap /opt/multi-p2/bin/bwrap flags=(unconfined) {
  userns,
}
'''


def require(value, code):
    if not value:
        raise ValueError(code)


def trusted(path):
    require(path.is_absolute(), 'absolute_path_required')
    for part in [*reversed(path.parents), path]:
        info = part.lstat()
        require(info.st_uid == 0 and not info.st_mode & 0o022 and not stat.S_ISLNK(info.st_mode), 'untrusted_path')


def read_regular(path, limit):
    trusted(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= limit, 'source_type_or_size')
        require(not info.st_mode & 0o6000, 'privileged_source')
        data = stream.read(limit + 1)
        require(len(data) <= limit, 'source_size')
        return data


def absent(path):
    require(not os.path.lexists(path), 'existing_resource_refused:' + str(path))


def new_file(path, data, mode, gid):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchown(stream.fileno(), 0, gid)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
    except Exception:
        path.unlink()
        raise


def parser(*args):
    result = subprocess.run([str(PARSER), *args, str(PROFILE)], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30,
                            env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'}, cwd='/')
    require(result.returncode == 0, 'apparmor_parser_failed:' + str(result.returncode) + ':' + result.stderr[:4096].decode('utf-8', 'replace'))


def main():
    created_dir = False
    created_binary = False
    created_profile = False
    attempted_load = False
    try:
        require(sys.platform == 'linux' and os.geteuid() == 0 and sys.flags.isolated and sys.flags.no_site,
                'trusted_root_linux_I_S_required')
        trusted(Path(__file__).absolute())
        trusted(BIN_DIR.parent)
        trusted(PROFILE.parent)
        trusted(PARSER)
        absent(BIN_DIR)
        absent(PROFILE)
        profiles = Path('/sys/kernel/security/apparmor/profiles').read_text()
        require(not any(line.startswith('multi-p2-bwrap ') for line in profiles.splitlines()), 'profile_already_loaded')
        config = json.loads(read_regular(CONFIG, 65536))
        source = Path(config['bwrap_path'])
        require(source != BINARY, 'source_is_destination')
        gid = config['worker_gid']
        require(type(gid) is int and gid > 0, 'dedicated_worker_group_required')
        data = read_regular(source, 8 * 1024 * 1024)
        digest = 'sha256:' + hashlib.sha256(data).hexdigest()
        require(digest == config['bwrap_sha256'], 'source_pin_mismatch')
        try:
            capabilities = os.getxattr(source, 'security.capability', follow_symlinks=False)
        except OSError as error:
            require(error.errno in {errno.ENODATA, errno.ENOTSUP, errno.EOPNOTSUPP}, 'capability_check_failed')
            capabilities = b''
        require(not capabilities, 'source_capabilities_refused')
        # Directory stays root-only until its complete binary is installed.
        BIN_DIR.mkdir(mode=0o700)
        created_dir = True
        new_file(BINARY, data, 0o550, gid)
        created_binary = True
        os.chown(BIN_DIR, 0, gid)
        os.chmod(BIN_DIR, 0o750)
        new_file(PROFILE, PROFILE_BYTES, 0o644, 0)
        created_profile = True
        require(read_regular(BINARY, 8 * 1024 * 1024) == data, 'copy_readback_failed')
        parser('-Q', '-T')  # Syntax/compile only, no kernel load, no cache read.
        attempted_load = True
        parser('-a', '-T')  # Add only this new profile; never replace a profile.
        profiles = Path('/sys/kernel/security/apparmor/profiles').read_text()
        require(any(line.startswith('multi-p2-bwrap ') for line in profiles.splitlines()), 'profile_load_readback_failed')
        print(json.dumps({'status': 'profile_prepared_not_execution_verified', 'binary': str(BINARY),
                          'binary_sha256': digest, 'profile': str(PROFILE),
                          'profile_sha256': hashlib.sha256(PROFILE_BYTES).hexdigest(),
                          'sysctl_changed': False, 'executor_config_changed': False}))
        return 0
    except Exception as error:
        rollback = 'not_needed'
        safe_cleanup = True
        if attempted_load:
            try:
                parser('-R')
                require(not any(line.startswith('multi-p2-bwrap ') for line in Path('/sys/kernel/security/apparmor/profiles').read_text().splitlines()), 'profile_unload_readback_failed')
                rollback = 'new_profile_unloaded'
            except Exception:
                safe_cleanup = False
                rollback = 'unload_unverified_preserved_new_resources'
        if safe_cleanup:
            if created_profile: PROFILE.unlink()
            if created_binary: BINARY.unlink()
            if created_dir: BIN_DIR.rmdir()
        print(json.dumps({'status': 'blocked', 'reason': str(error), 'rollback': rollback,
                          'sysctl_changed': False, 'executor_config_changed': False}))
        return 78


if __name__ == '__main__':
    raise SystemExit(main())
