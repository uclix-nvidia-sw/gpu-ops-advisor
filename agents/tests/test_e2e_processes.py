import subprocess
import sys
from unittest.mock import Mock

import pytest

from e2e_processes import process_scope, stop_processes


@pytest.mark.parametrize("fails", [False, True])
def test_scope_reaps_children_but_preserves_shared_services(fails):
    shared = Mock()
    processes = [shared]
    child = None
    try:
        with process_scope(processes):
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(60)"]
            )
            processes.append(child)
            if fails:
                raise ValueError("test failure")
    except ValueError:
        assert fails
    assert child.poll() is not None
    assert processes == [shared]
    shared.terminate.assert_not_called()


def test_cleanup_kills_and_reaps_a_process_that_ignores_termination():
    child = Mock()
    child.poll.return_value = None
    child.wait.side_effect = [subprocess.TimeoutExpired("child", 5), 0]
    stop_processes([child])
    child.terminate.assert_called_once()
    child.kill.assert_called_once()
    assert child.wait.call_count == 2
