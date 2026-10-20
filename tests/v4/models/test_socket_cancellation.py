"""Cancellation shuts down the active socket before either watcher closes it."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from contextlib import closing
from typing import Any

import httpx
import pytest
from agent.test_dispatcher_http import quiet_server

from mingjing_core.models.errors import ModelCancelled
from mingjing_core.models.openai_compat import OpenAICompat
from mingjing_core.models.transport import close_on_cancel, shutdown_response


class SocketProbe:
    def __init__(self, connection: socket.socket, events: list[str]) -> None:
        self.connection, self.events = connection, events

    def shutdown(self, how: int) -> None:
        self.events.append("shutdown")
        self.connection.shutdown(how)


class NetworkInfo:
    def __init__(self, value: Any) -> None:
        self.value = value

    def get_extra_info(self, name: str) -> Any:
        assert name == "socket"
        return self.value


class Body(httpx.SyncByteStream):
    def __init__(self, events: list[str]) -> None:
        self.events, self.closed = events, threading.Event()

    def __iter__(self) -> Iterator[bytes]:
        yield b"synthetic"

    def close(self) -> None:
        self.events.append("close")
        self.closed.set()


@pytest.mark.parametrize("deadline", [False, True])
def test_cancel_or_deadline_shuts_down_active_response_before_client_close(deadline: bool) -> None:
    events: list[str] = []
    cancel = threading.Event()
    left, right = socket.socketpair()
    with closing(left), closing(right):
        body = Body(events)
        response = httpx.Response(
            200, stream=body, extensions={"network_stream": NetworkInfo(SocketProbe(left, events))}
        )

        class Client:
            def close(self) -> None:
                events.append("client_close")
                response.close()

        limit = time.monotonic() - 1 if deadline else time.monotonic() + 5
        with close_on_cancel(Client(), cancel, limit, active=lambda: response) as expired:
            if not deadline:
                cancel.set()
            assert body.closed.wait(1) and expired.is_set()
            right.settimeout(0.5)
            assert right.recv(1) == b""
        assert events.index("shutdown") < events.index("client_close") < events.index("close")


def test_normal_completion_closes_without_aborting_socket() -> None:
    events: list[str] = []
    left, right = socket.socketpair()
    with closing(left), closing(right):
        body = Body(events)
        response = httpx.Response(
            200, stream=body, extensions={"network_stream": NetworkInfo(SocketProbe(left, events))}
        )
        with close_on_cancel(response, threading.Event(), time.monotonic() + 5) as expired:
            assert not expired.is_set()
        assert events == ["close"]
        right.sendall(b"x")
        assert left.recv(1) == b"x"


@pytest.mark.parametrize("metadata", [None, {}, {"network_stream": object()}])
def test_streams_without_socket_extension_keep_ordinary_close(metadata: Any) -> None:
    body, cancel = Body([]), threading.Event()
    response = httpx.Response(200, stream=body, extensions=metadata)
    with close_on_cancel(response, cancel, time.monotonic() + 5) as expired:
        cancel.set()
        assert body.closed.wait(1) and expired.is_set()
    assert body.events == ["close"]


@pytest.mark.parametrize("failure", [OSError, RuntimeError, TypeError, AttributeError, httpx.ReadError])
def test_shutdown_metadata_failures_do_not_escape_or_skip_close(failure: Any, capsys: Any) -> None:
    class BrokenInfo:
        def get_extra_info(self, name: str) -> Any:
            raise failure("synthetic-private-transport-detail")

    body, cancel = Body([]), threading.Event()
    response = httpx.Response(200, stream=body, extensions={"network_stream": BrokenInfo()})
    with close_on_cancel(response, cancel, time.monotonic() + 5):
        cancel.set()
        assert body.closed.wait(1)
    assert body.events == ["close"] and "synthetic-private" not in capsys.readouterr().err


def test_repeated_shutdown_of_already_closed_socket_is_safe() -> None:
    left, right = socket.socketpair()
    left.close()
    right.close()
    response = httpx.Response(200, extensions={"network_stream": NetworkInfo(left)})
    shutdown_response(response)
    shutdown_response(response)
    response.close()


def test_two_watchers_both_abort_before_closing_the_shared_response() -> None:
    events: list[str] = []
    left, right = socket.socketpair()
    with closing(left), closing(right):
        body, cancel = Body(events), threading.Event()
        response = httpx.Response(
            200, stream=body, extensions={"network_stream": NetworkInfo(SocketProbe(left, events))}
        )

        class Client:
            def close(self) -> None:
                assert "shutdown" in events
                response.close()

        with (
            close_on_cancel(Client(), cancel, time.monotonic() + 5, active=lambda: response),
            close_on_cancel(response, cancel, time.monotonic() + 5),
        ):
            cancel.set()
            assert body.closed.wait(1)
        assert events.index("shutdown") < events.index("close")


def test_real_quiet_http_cancel_finishes_before_server_releases_next_bytes() -> None:
    cancelled, fragment, done = threading.Event(), threading.Event(), threading.Event()
    errors: list[BaseException] = []
    with quiet_server() as (base, started, release):
        model = OpenAICompat(
            base_url=base,
            api_key="local-synthetic",
            model="scripted",
            provider="scripted",
            max_retries=0,
            transport=httpx.HTTPTransport(retries=0),
            settings={"first_byte_timeout": 5, "total_timeout": 10},
        )

        def consume() -> None:
            try:
                for event in model.stream([], cancel_event=cancelled):
                    if event.type == "text":
                        fragment.set()
            except BaseException as error:
                errors.append(error)
            finally:
                done.set()

        worker = threading.Thread(target=consume, daemon=True)
        worker.start()
        try:
            assert started.wait(3) and fragment.wait(3)
            stamp = time.monotonic()
            cancelled.set()
            assert done.wait(2), "actual quiet HTTP cancellation exceeded two seconds"
            assert time.monotonic() - stamp < 2 and not release.is_set()
            assert len(errors) == 1 and isinstance(errors[0], ModelCancelled) and model.request_count == 1
        finally:
            release.set()
            worker.join(timeout=2)
