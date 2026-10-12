"""Remove explicitly deleted reports from the Ops-owned artifact volume."""

import asyncio
import contextlib
import logging
import os
from pathlib import Path
import shutil
import stat
from uuid import UUID

import psycopg

log = logging.getLogger(__name__)


def remove_artifacts(directory, job_id):
    if str(UUID(job_id)) != job_id:
        raise ValueError("canonical report job ID required")
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("artifact root must be a directory")
    folder = root / job_id
    try:
        info = folder.lstat()
    except FileNotFoundError:
        info = None
    if info is not None:
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("report artifact directory must not be a symlink")
        if stat.S_ISDIR(info.st_mode):
            shutil.rmtree(folder)
        elif not (stat.S_ISREG(info.st_mode) and info.st_size == 0):
            raise ValueError("unexpected report artifact path")
    # A file at the old directory path also fences late, cancelled artifact writers.
    try:
        fd = os.open(folder, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        info = folder.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != 0:
            raise
        fd = os.open(folder, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != 0:
            raise ValueError("invalid artifact deletion barrier")
        os.fsync(fd)
    finally:
        os.close(fd)
    # Persist the removed directory and replacement name before acknowledging in DB.
    if os.name != "nt":
        parent_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)


async def cleanup_once(settings):
    async with await psycopg.AsyncConnection.connect(
        settings.database_url, connect_timeout=5
    ) as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL statement_timeout='15s'")
            row = await (
                await conn.execute(
                    "SELECT d.job_id::text FROM report_deletions d JOIN jobs j ON j.id=d.job_id "
                    "WHERE d.artifact_cleanup_state IN ('pending','failed') AND j.kind='report' "
                    "AND j.status IN ('succeeded','failed','cancelled','expired') "
                    "ORDER BY COALESCE(d.artifact_cleanup_at,d.deleted_at), d.job_id "
                    "LIMIT 1 FOR UPDATE OF d SKIP LOCKED"
                )
            ).fetchone()
            if not row:
                return False
            job_id = row[0]
            task = asyncio.create_task(
                asyncio.to_thread(remove_artifacts, settings.artifact_dir, job_id)
            )
            error = None
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                # Keep the row lock until filesystem work has stopped.
                while not task.done():
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await asyncio.shield(task)
                if not task.cancelled():
                    task.exception()
                raise
            except Exception as exc:
                error = type(exc).__name__
                log.warning(
                    "report artifact cleanup failed job=%s type=%s", job_id, error
                )
            await conn.execute(
                "UPDATE report_deletions SET artifact_cleanup_state=%s, "
                "artifact_cleanup_at=clock_timestamp(), artifact_cleanup_error=%s WHERE job_id=%s",
                ("failed" if error else "complete", error, job_id),
            )
            return True


async def cleanup(settings, once=False):
    while True:
        try:
            await cleanup_once(settings)
        except Exception as exc:
            # A rolling upgrade may start Ops before JC installs the deletion table.
            log.warning(
                "report artifact cleanup unavailable type=%s", type(exc).__name__
            )
        if once:
            return
        await asyncio.sleep(30)
