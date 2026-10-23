"""Exercise P3's actual running stream through a disconnect and numeric resume."""

from __future__ import annotations

import copy
import re
import threading
import time
from contextvars import copy_context
from typing import Any

import httpx

from tools.eval.providers.scripted import ScriptedProvider

from .base import TurnResult
from .v4_scripted import ScriptedModelPort
from .v4_sse_http import event_listener, frames
from .v4_sse_proof import RELATED, check_complete, persisted


def partition_script(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(actions) != 1 or set(actions[0]) != {"text"}:
        raise ValueError("Offline reconnect requires one original model text action")
    text = actions[0]["text"]
    if not isinstance(text, str) or not 2 <= len(text) <= 200_000:
        raise ValueError("Offline reconnect model text cannot be divided safely")
    cut = len(text) // 2
    return [{"text": text, "text_chunks": [text[:cut], text[cut:]]}]


def disconnect_index(target: Any, turn: dict[str, Any]) -> int:
    controls = target.seed.get("controls", {})
    cut = controls.get("disconnect_after_event_id")
    last = controls.get("last_event_id")
    if not isinstance(cut, str) or cut != last or last != turn["action"].get("last_event_id"):
        raise ValueError("Offline reconnect requires one consistent declared logical cursor")
    match = re.fullmatch(r"event-([1-9][0-9]*)", cut)
    if not match or not 1 <= int(match[1]) <= 2:
        raise ValueError("Offline reconnect cursor is outside its two model chunks")
    return int(match[1])


class Producer:
    def __init__(self, target: Any, run: dict[str, Any], cut: int) -> None:
        self.target, self.run, self.cut = target, run, cut
        self.paused, self.release = threading.Event(), threading.Event()
        self.result: dict[str, Any] = {}
        self.error: BaseException | None = None
        context = copy_context()
        self.thread = threading.Thread(target=context.run, args=(self.execute,), daemon=True)

    def barrier(self, index: int) -> None:
        if index == self.cut:
            self.paused.set()
            if not self.release.wait(10):
                raise TimeoutError("Offline producer did not receive its bounded resume signal")

    def execute(self) -> None:
        try:
            self.result = self.target.runtime.execute(
                self.target.service, self.target.owner, self.run["id"], self.run["lease_token"]
            )
        except BaseException as exc:
            self.error = exc

    def finish(self) -> None:
        self.release.set()
        self.thread.join(timeout=12)
        if self.thread.is_alive():
            raise TimeoutError("Offline producer did not stop")
        if self.error is not None:
            raise self.error


def cut_state(target: Any, producer: Producer, initial: list[dict[str, Any]]) -> dict[str, Any]:
    if not producer.paused.wait(2):
        raise ValueError("Offline stream did not pause at the actual model boundary")
    current = target.repo.fetch_run(target.owner, producer.run["id"])
    pg = persisted(target.repo, target.owner, producer.run["id"])
    if current["status"] != "running" or pg != initial or any(event["type"] == "final" for event in pg):
        raise ValueError("Offline first connection was not closed during the actual running producer")
    return {"status": current["status"], "native_ids": [event["data"]["seq"] for event in pg]}


def exchange(target: Any, producer: Producer, base: str) -> tuple[list[dict], list[dict], dict]:
    initial, replay = [], []
    url = f"{base}/api/runs/{producer.run['id']}/events"
    headers = {"X-Eval-Owner": target.owner}
    with httpx.Client(trust_env=False, timeout=8, transport=httpx.HTTPTransport(retries=0)) as client:
        with client.stream("GET", url, headers=headers) as response:
            for event in frames(response, producer.run["id"]):
                initial.append(event)
                if sum(item["type"] in RELATED for item in initial) == producer.cut:
                    break
        # The first socket is closed before either finalization or producer release.
        cut = cut_state(target, producer, initial)
        cursor = initial[-1]["data"]["seq"]
        with client.stream("GET", url, headers=dict(headers, **{"Last-Event-ID": str(cursor)})) as response:
            if cut_state(target, producer, initial) != cut:
                raise ValueError("Offline native stream drifted before the resume socket opened")
            producer.release.set()
            replay.extend(frames(response, producer.run["id"]))
    return initial, replay, cut


def reconnect(target: Any, turn: dict[str, Any]) -> TurnResult:
    started = time.perf_counter()
    if target.protocol or target.critic or target.runtime.offline is not True:
        raise ValueError("Offline reconnect cannot use protocol, critic or live ports")
    cut = disconnect_index(target, turn)
    actions = partition_script(target.provider.replay(turn["_index"]))
    original = target.port
    port = ScriptedModelPort()
    run = target._request(dict(copy.deepcopy(turn), kind="chat", action={}))
    target.run_ids.append(run["id"])
    port.start(ScriptedProvider([{"turn": turn["_index"], "model": actions}]), turn["_index"], target.bindings)
    producer = Producer(target, run, cut)
    port.text_chunk_hook = producer.barrier
    target.port = target.runtime.port = port
    try:
        with event_listener(target.service, target.owner) as base:
            producer.thread.start()
            try:
                initial, replay, paused = exchange(target, producer, base)
            finally:
                producer.finish()
        pg = persisted(target.repo, target.owner, run["id"])
        proof = check_complete(pg, initial, replay, initial[-1]["data"]["seq"])
        current = target.repo.fetch_run(target.owner, run["id"])
        if current["status"] != "succeeded" or current["result"] != producer.result:
            raise ValueError("Offline stream finalization did not match its actual committed envelope")
        target.stream = dict(proof, run_id=run["id"], owner=target.owner, disconnect_state=paused)
        return TurnResult(
            text=producer.result["text"],
            events=proof["events"],
            model_calls=port.calls,
            elapsed_seconds=time.perf_counter() - started,
            metadata={"offline": True, "physical_model_requests": 0, "run_id": run["id"]},
        )
    finally:
        target.port = target.runtime.port = original
