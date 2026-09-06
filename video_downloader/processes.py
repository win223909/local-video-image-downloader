"""Bounded process output and cancellation for local media jobs."""

from collections import deque
import os
import queue
import signal
import subprocess
import threading
import time


def terminate_process_tree(process) -> None:
    pid = process.pid
    if not pid:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=10)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            try:
                process.terminate()
            except ProcessLookupError:
                pass


def stop_process(process) -> None:
    terminate_process_tree(process)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=3)
    finally:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def run_media_process(command, *, check_cancelled, on_line=None, on_process=None, timeout=6 * 3600):
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
        start_new_session=os.name != "nt",
    )
    lines = queue.Queue(maxsize=128)
    finished = threading.Event()
    stop_reader = threading.Event()
    recent = deque(maxlen=40)

    def read_output():
        try:
            for line in process.stdout:
                while not stop_reader.is_set():
                    try:
                        lines.put(line[-4096:].strip(), timeout=0.1)
                        break
                    except queue.Full:
                        continue
                if stop_reader.is_set():
                    break
        finally:
            finished.set()

    reader = threading.Thread(target=read_output, daemon=True)
    try:
        if on_process:
            on_process(process)
        reader.start()
        started = time.monotonic()
        while not finished.is_set() or not lines.empty():
            check_cancelled()
            if time.monotonic() - started > timeout:
                raise TimeoutError("Media process exceeded its time limit")
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                continue
            if line:
                recent.append(line)
                if on_line:
                    on_line(line)
        check_cancelled()
        return process.wait(timeout=3), "\n".join(recent)
    except BaseException:
        stop_process(process)
        raise
    finally:
        stop_reader.set()
        if reader.ident:
            reader.join(timeout=3)
        if process.stdout:
            process.stdout.close()
        if on_process:
            on_process(None)
