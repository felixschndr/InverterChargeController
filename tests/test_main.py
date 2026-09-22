import os
import pathlib
import signal
import subprocess  # nosec B404
import sys

import pytest

from source import main

HOLD_THE_LOCK_UNTIL_KILLED = """
import fcntl, sys, time
lock_file = open(sys.argv[1], "w")
fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
print("locked", flush=True)
time.sleep(60)
"""


@pytest.fixture
def lock_file_path(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = str(tmp_path / "inverter_charge_controller.lock")
    monkeypatch.setattr(main, "LOCK_FILE_PATH", path)
    return path


@pytest.fixture
def other_instance_holding_the_lock(lock_file_path):
    other_instance = subprocess.Popen(  # nosec B603
        [sys.executable, "-c", HOLD_THE_LOCK_UNTIL_KILLED, lock_file_path],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert other_instance.stdout.readline().strip() == "locked"
    yield other_instance

    if other_instance.poll() is None:
        other_instance.kill()
    other_instance.wait()


def test_the_lock_is_granted_when_no_other_instance_holds_it(lock_file_path):
    lock_file = main.acquire_lock()

    assert lock_file is not None
    assert pathlib.Path(lock_file_path).read_text() == str(os.getpid())


def test_the_lock_is_refused_while_another_instance_holds_it(other_instance_holding_the_lock):
    assert main.acquire_lock() is None


def test_the_lock_is_released_when_the_holding_instance_is_killed(other_instance_holding_the_lock):
    assert main.acquire_lock() is None

    other_instance_holding_the_lock.send_signal(signal.SIGKILL)
    other_instance_holding_the_lock.wait()

    assert main.acquire_lock() is not None


def test_releasing_the_lock_file_lets_the_next_instance_acquire_it(lock_file_path):
    first_lock_file = main.acquire_lock()
    assert first_lock_file is not None
    assert main.acquire_lock() is None

    first_lock_file.close()

    assert main.acquire_lock() is not None
