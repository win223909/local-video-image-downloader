"""Run downloads and their FFmpeg children as one cancellable process tree."""

import multiprocessing
import os
import signal
import time

from video_downloader.core import DownloadCancelled, VideoDownloaderError
from video_downloader.processes import terminate_process_tree


def _download(send, cancel, resolved, selected, output_dir):
    if os.name != "nt":
        os.setsid()
    from video_downloader.resolver import download_resolved_video

    def progress(raw):
        if cancel.is_set():
            raise DownloadCancelled()
        keys = {"status", "downloaded_bytes", "total_bytes", "total_bytes_estimate", "speed", "eta"}
        send.send(("progress", {key: raw.get(key) for key in keys}))

    def message(text):
        if cancel.is_set():
            raise DownloadCancelled()
        send.send(("message", text))

    try:
        result = download_resolved_video(resolved, selected, output_dir, progress, message)
        send.send(("result", result))
    except VideoDownloaderError as exc:
        send.send(("error", (str(exc), exc.code)))
    except Exception:
        send.send(("error", ("下载失败，请重新解析后再试。", "unknown")))
    finally:
        send.close()


def run_download_worker(resolved, selected, output_dir, progress_hook, status_hook, check_cancelled):
    context = multiprocessing.get_context("spawn")
    receive, send = context.Pipe(duplex=False)
    cancel = context.Event()
    process = context.Process(target=_download, args=(send, cancel, resolved, selected, output_dir))
    process.start()
    send.close()
    try:
        started = time.monotonic()
        while True:
            check_cancelled()
            if time.monotonic() - started > 24 * 3600:
                raise VideoDownloaderError("下载任务超时。", code="network_timeout")
            if receive.poll(0.1):
                try:
                    kind, payload = receive.recv()
                except EOFError:
                    break
                if kind == "progress":
                    progress_hook(payload)
                elif kind == "message":
                    status_hook(payload)
                elif kind == "result":
                    check_cancelled()
                    return payload
                elif kind == "error":
                    if payload[1] == "download_cancelled":
                        raise DownloadCancelled()
                    raise VideoDownloaderError(payload[0], code=payload[1])
            elif not process.is_alive():
                break
        raise VideoDownloaderError("下载进程意外退出，请重试。", code="worker_failed")
    finally:
        cancel.set()
        process.join(timeout=0.3)
        if process.is_alive():
            terminate_process_tree(process)
            process.join(timeout=3)
            # The worker can exit before FFmpeg handles SIGTERM. Finish cleaning
            # its owned process group even when the worker itself is gone.
            if os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            if process.is_alive():
                process.kill()
                process.join(timeout=3)
        receive.close()
        process.close()
