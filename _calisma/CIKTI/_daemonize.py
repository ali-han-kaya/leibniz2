#!/usr/bin/env python3
"""Double-fork daemonizer for preview_server.py — full detach from terminal
session. macOS'ta `setsid` yok; Python ile yaparız.

Pattern (Stevens'in Advanced Programming in the UNIX Environment kitabından):
  1. fork
  2. setsid (yeni session)
  3. fork (artık session leader değiliz, terminal geri alma riski yok)
  4. chdir / (umount gerekmiyor)
  5. close std fds
  6. exec preview_server.py

Log: ~/Library/Logs/com.freebuff/preview-daemon.log (debug için).
"""
import os
import sys
import time

LOG_PATH = os.path.expanduser("~/Library/Logs/com.freebuff/preview-daemon.log")


def log(msg):
    try:
        with open(LOG_PATH, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] PID={os.getpid()} PGID={os.getpgrp()} SID={os.getsid(0) if hasattr(os, 'getsid') else '?'}: {msg}\n")
    except OSError:
        pass


log(f"daemonize start, argv={sys.argv}")

# First fork
pid = os.fork()
log(f"after fork 1: pid={pid}")
if pid > 0:
    sys.exit(0)  # parent exits

# New session
os.setsid()
log(f"after setsid: PID={os.getpid()}")

# Second fork
pid = os.fork()
log(f"after fork 2: pid={pid}")
if pid > 0:
    sys.exit(0)  # session leader exits

# Now we're in a daemon session
log(f"daemon init: PID={os.getpid()}")

os.chdir("/")
try:
    os.umask(0)
except OSError:
    pass

# Close std fds
for fd in (0, 1, 2):
    try:
        os.close(fd)
    except OSError:
        pass

# Redirect stdin to /dev/null, stdout+stderr to log file
devnull = os.open(os.devnull, os.O_RDWR)
os.dup2(devnull, 0)
os.dup2(devnull, 1)
log_path = os.path.expanduser("~/Library/Logs/com.freebuff/preview-server.log")
log_fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
os.dup2(log_fd, 1)
os.dup2(log_fd, 2)

log(f"exec preview_server.py: {sys.argv[1:]}")

# Exec the real server
os.execvp(sys.executable,
          [sys.executable] + sys.argv[1:])
