import asyncio
from builtins import BaseExceptionGroup
import contextlib
import logging
import os
import time
from uuid import uuid4

import httpx

from .contracts import timestamp, validate_input
from .llm import LLM, RemoteUncertain
from .model import model_settings
from .runtime import attempt_context
from .store import Store
from .artifacts import save_artifacts

log = logging.getLogger(__name__)


class Worker:
    def __init__(self, settings, runner, store=None, http=None):
        self.settings, self.runner = settings, runner
        self.store = store or Store(settings.database_url)
        self.http = http
        self.identity = dict(
            worker_id=os.getenv("WORKER_ID", settings.kind + "-" + str(uuid4())),
            boot_id=str(uuid4()),
            kind=settings.kind,
        )

    async def post(self, path, body):
        response = await self.http.post(
            self.settings.jc_url + path, json=body, timeout=10
        )
        response.raise_for_status()
        return response.json() if response.status_code != 204 else None

    async def once(self):
        claim = await self.post("/claims", self.identity)
        if not claim:
            return False
        await self.execute(claim)
        return True

    async def execute(self, claim):
        fence = {k: claim[k] for k in ("attempt_no", "claim_token")}
        path = "/jobs/" + claim["job_id"]
        state = {"stage": "validating", "remote_call_state": "not_started"}
        cancelled = asyncio.Event()
        lease = {"expires": timestamp(claim["lease_expires_at"])}

        async def heartbeat():
            while True:
                try:
                    response = await self.post(path + "/heartbeat", {**fence, **state})
                    lease["expires"] = timestamp(response["lease_expires_at"])
                    if response.get("cancel_requested"):
                        cancelled.set()
                        return
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code < 500:
                        cancelled.set()
                        return
                except httpx.TransportError:
                    pass
                if time.time() >= lease["expires"]:
                    cancelled.set()
                    return
                await asyncio.sleep(
                    min(
                        claim["heartbeat_seconds"],
                        max(0.05, lease["expires"] - time.time()),
                    )
                )

        heartbeat_task = asyncio.create_task(heartbeat())
        cancel_task = asyncio.create_task(cancelled.wait())
        run_task = None
        code = "internal_error"
        token = None
        try:
            if claim["kind"] != self.settings.kind:
                raise ValueError("wrong worker kind")
            validate_input(claim["kind"], claim["input"])
            profile = self.settings.profile()
            deadline = time.monotonic() + min(
                profile["limits"]["deadline_seconds"],
                timestamp(claim["deadline_at"]) - time.time(),
            )
            if deadline <= time.monotonic():
                raise TimeoutError()
            async with asyncio.timeout_at(deadline):
                context = await self.store.read_context(claim)
                settings = model_settings(
                    self.settings, context.pop("model_profile", None)
                )
                llm = LLM(
                    settings,
                    deadline,
                    int(claim["budget"]["attempt_limit"]),
                    lambda value: state.update(remote_call_state=value),
                )
                token = attempt_context.set(
                    dict(
                        claim=claim,
                        profile=profile,
                        context=context,
                        llm=llm,
                        deadline=deadline,
                        settings=settings,
                    )
                )
                state["stage"] = "workflow"
                run_task = asyncio.create_task(self.runner(claim))
                done, _ = await asyncio.wait(
                    [run_task, cancel_task], return_when=asyncio.FIRST_COMPLETED
                )
                if cancel_task in done:
                    code = "cancelled"
                    raise asyncio.CancelledError()
                result, evidence = await run_task
                if state["remote_call_state"] == "unknown":
                    raise RemoteUncertain()
                state["stage"] = "saving"
                # Final lease/cancellation check closes long-calculation cancellation window.
                ack = await self.post(path + "/heartbeat", {**fence, **state})
                if ack.get("cancel_requested"):
                    code = "cancelled"
                    raise asyncio.CancelledError()
                if claim["kind"] == "report":
                    result["artifacts"] = await asyncio.to_thread(
                        save_artifacts, result, self.settings.artifact_dir
                    )
                candidate, digest = await self.store.save(claim, result, evidence)
                state["stage"] = "completing"
                body = {**fence, "candidate_id": candidate, "content_hash": digest}
                # Retry the SAME completion; never recompute or create a new candidate.
                for attempt in range(3):
                    try:
                        await self.post(path + "/complete", body)
                        return
                    except httpx.TransportError:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(0.25 * 2**attempt)
        except asyncio.CancelledError:
            code = "cancelled"
        except TimeoutError:
            code = "timeout"
        except RemoteUncertain:
            code = "timeout"
        except (ValueError, KeyError, TypeError):
            code = (
                "invalid_input" if state["stage"] == "validating" else "invalid_result"
            )
        except Exception as exc:
            log.error(
                "attempt failed job=%s type=%s", claim["job_id"], type(exc).__name__
            )
        finally:
            if run_task and not run_task.done():
                run_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await run_task
            heartbeat_task.cancel()
            cancel_task.cancel()
            await asyncio.gather(heartbeat_task, cancel_task, return_exceptions=True)
            if token is not None:
                attempt_context.reset(token)
        with contextlib.suppress(httpx.HTTPError):
            await self.post(
                path + "/fail",
                {
                    **fence,
                    "code": code,
                    "retryable": code == "timeout",
                    "remote_call_state": state["remote_call_state"],
                },
            )

    async def serve(self, once=False):
        async with httpx.AsyncClient() as client:
            self.http = self.http or client
            await self.post(
                "/workers/register",
                {
                    **self.identity,
                    "capacity_profile_id": os.getenv(
                        "CAPACITY_PROFILE_ID", self.settings.kind + "-v1"
                    ),
                },
            )
            while True:
                try:
                    worked = await self.once()
                except httpx.HTTPError:
                    worked = False
                    log.warning("JC unavailable; waiting")
                if once:
                    return
                if not worked:
                    await asyncio.sleep(2)


def transient_connection_error(exc):
    if isinstance(exc, BaseExceptionGroup):
        return all(transient_connection_error(child) for child in exc.exceptions)
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 502, 503, 504}
    return isinstance(
        exc,
        (
            httpx.NetworkError,
            httpx.TimeoutException,
            httpx.RemoteProtocolError,
            ConnectionError,
            TimeoutError,
        ),
    )


async def serve_nat(settings, once=False):
    from nat.runtime.loader import load_workflow

    delay = 2
    while True:
        async with contextlib.AsyncExitStack() as stack:
            try:
                manager = await stack.enter_async_context(
                    load_workflow(settings.nat_config_file, max_concurrency=1)
                )
            except Exception as exc:
                if not transient_connection_error(exc):
                    raise
                # Retry only initialization, before registering/claiming any JC work.
                # Do not log upstream exception bodies, which can contain credentials.
                log.warning(
                    "MCP connection unavailable during startup; retrying in %ss", delay
                )
            else:
                log.info("MCP workflow initialized; starting %s worker", settings.kind)

                async def runner(claim):
                    async with manager.run(claim) as run:
                        value = await run.result()
                        return value["result"], value["evidence"]

                await Worker(settings, runner).serve(once)
                return
        await asyncio.sleep(delay)
        delay = min(delay * 2, 30)
