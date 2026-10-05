import ctypes
import json
import os
import signal
import sys
import threading
import time

PARENT_CHECK_SECONDS = 5
KEEPALIVE_SECONDS = 30
PR_SET_PDEATHSIG = 1
OUTPUT_LOCK = threading.Lock()
TERMINATION_SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)


def log(reason):
    try:
        sys.stderr.write(f"creality-bridge[{os.getpid()}]: {reason}\n")
        sys.stderr.flush()
    except (OSError, ValueError):
        return


def exit_now(reason):
    log(f"exiting: {reason}")
    os._exit(0)


def write_raw(text):
    with OUTPUT_LOCK:
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except (BrokenPipeError, ValueError, OSError) as error:
            exit_now(f"stdout closed ({error.__class__.__name__})")


def write_line(view):
    write_raw(json.dumps(view) + "\n")


def request_parent_death_signal():
    try:
        ctypes.CDLL(None).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)
    except Exception:
        return


def supervise(initial_parent):
    last_keepalive = time.monotonic()
    while True:
        time.sleep(PARENT_CHECK_SECONDS)
        if os.getppid() != initial_parent:
            exit_now(f"parent changed from {initial_parent} to {os.getppid()}")
        if time.monotonic() - last_keepalive >= KEEPALIVE_SECONDS:
            last_keepalive = time.monotonic()
            write_raw("\n")


def install_parent_guard():
    initial_parent = os.getppid()
    if initial_parent == 1:
        exit_now("started without a parent (ppid 1)")
    request_parent_death_signal()
    if os.getppid() != initial_parent:
        exit_now("parent exited during startup")
    install_diagnostics(initial_parent)
    threading.Thread(target=supervise, args=(initial_parent,), daemon=True).start()


def handle_termination(signal_number, frame):
    log(f"exiting: received {signal.Signals(signal_number).name} (parent pid {os.getppid()})")
    sys.exit(0)


def log_thread_failure(arguments):
    log(f"thread {arguments.thread.name} crashed: {arguments.exc_type.__name__}: {arguments.exc_value}")


def install_diagnostics(initial_parent):
    for signal_number in TERMINATION_SIGNALS:
        signal.signal(signal_number, handle_termination)
    threading.excepthook = log_thread_failure
    log(f"started (parent pid {initial_parent})")
