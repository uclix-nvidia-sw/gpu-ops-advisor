"""Bound test-owned subprocess lifetimes without stopping shared services."""

from contextlib import contextmanager
import subprocess


def stop_processes(processes):
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


@contextmanager
def process_scope(processes):
    start = len(processes)
    try:
        yield
    finally:
        stop_processes(processes[start:])
        del processes[start:]
