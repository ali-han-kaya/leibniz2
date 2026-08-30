"""Shared executable lookup for launchd's minimal PATH environments."""
import os
import shutil

KNOWN_PATHS = {
    "node": ("/opt/homebrew/bin/node", "/usr/local/bin/node", "/home/linuxbrew/.linuxbrew/bin/node"),
    "pdfinfo": ("/opt/homebrew/bin/pdfinfo", "/usr/local/bin/pdfinfo"),
    "qpdf": ("/opt/homebrew/bin/qpdf", "/usr/local/bin/qpdf"),
    "coqtop": ("/opt/homebrew/bin/coqtop", "/usr/local/bin/coqtop"),
    "coqc": ("/opt/homebrew/bin/coqc", "/usr/local/bin/coqc"),
    "lean": ("/opt/homebrew/bin/lean", "/usr/local/bin/lean", "~/.elan/bin/lean"),
    "lake": ("/opt/homebrew/bin/lake", "/usr/local/bin/lake", "~/.elan/bin/lake"),
}


def find_tool(name, known_paths=None, path_env=None):
    """Resolve *name* from PATH first, then validated known paths."""
    paths = KNOWN_PATHS.get(name, ()) if known_paths is None else known_paths
    env_path = os.environ.get("PATH")
    if path_env is not None:
        os.environ["PATH"] = path_env
    try:
        found = shutil.which(name)
    finally:
        if path_env is not None:
            if env_path is None:
                os.environ.pop("PATH", None)
            else:
                os.environ["PATH"] = env_path
    if found:
        return found
    for path in paths:
        path = os.path.expanduser(path)
        if os.path.isfile(path) and os.access(path, os.X_OK) and os.path.basename(path) == name:
            return path
    return None
