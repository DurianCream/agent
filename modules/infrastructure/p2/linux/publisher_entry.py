"""Fixed non-root publisher entry; no caller-supplied path, command or remote."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", required=True)
    parser.parse_args(argv)
    publication_started = False
    try:
        if sys.platform != "linux" or os.geteuid() == 0 or not sys.flags.isolated or not sys.flags.no_site:
            raise ValueError("isolated_nonroot_publisher_required")
        runtime = Path("/opt/multi-p2/runtime")
        for target in (Path(__file__).absolute(), runtime / "p2_broker.py"):
            for part in [*reversed(target.parents), target]:
                info = part.lstat()
                if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
                    raise ValueError("trusted_entry_path_required")
        spec = importlib.util.spec_from_file_location("multi_p2_publisher_bootstrap", runtime / "p2_broker.py")
        bootstrap = importlib.util.module_from_spec(spec); spec.loader.exec_module(bootstrap)
        bootstrap._trusted_runtime()
        sys.path.insert(0, str(runtime))
        from p2_publisher import publish_job
        publication_started = True
        print(json.dumps(publish_job("/etc/multi-p2/publication-job.json"), sort_keys=True))
        return 0
    except (OSError, ValueError, ImportError) as error:
        print(json.dumps({"status": "unknown" if publication_started else "blocked", "reason": getattr(error, "code", type(error).__name__), "published": "unverified" if publication_started else False}))
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
