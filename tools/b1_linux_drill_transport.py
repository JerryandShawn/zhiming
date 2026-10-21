"""Docker transport restricted to one labelled local Linux PostgreSQL drill."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from collections.abc import Callable
from typing import Any

CONTEXT = "desktop-linux"
PIPE = "npipe:////./pipe/dockerDesktopLinuxEngine"
CONTAINER = "zhiming-b1-linux-20261021"
LABEL = "com.zhiming.b1.drill"
OWNER = "20261021-main"
IMAGE = "postgres:15"
PORT = 55481
VOLUMES = ("zhiming-b1-linux-20261021-pgdata", "zhiming-b1-linux-20261021-work")


class DrillBlocked(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def require(value: object, code: str) -> None:
    if not value:
        raise DrillBlocked(code)


class LocalDocker:
    """Private command output is returned to the caller, never embedded in errors."""

    def __init__(self, runner: Callable[..., Any] = subprocess.run) -> None:
        self.runner = runner
        self.ready = False

    def call(
        self, args: list[str], *, stdin: bytes | None = None, timeout: int = 60
    ) -> bytes:
        environment = {
            key: value
            for key, value in os.environ.items()
            if not re.search(
                r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|DSN|DATABASE_URL", key, re.I
            )
        }
        environment.update(
            LANGSMITH_TRACING="false",
            LANGCHAIN_TRACING_V2="false",
            OTEL_SDK_DISABLED="true",
        )
        try:
            result = self.runner(
                ["docker", "--host", PIPE, *args],
                input=stdin,
                capture_output=True,
                check=False,
                timeout=timeout,
                env=environment,
            )
        except subprocess.TimeoutExpired:
            raise DrillBlocked("DOCKER_COMMAND_TIMEOUT") from None
        except OSError:
            raise DrillBlocked("DOCKER_CLIENT_UNAVAILABLE") from None
        require(result.returncode == 0, "DOCKER_COMMAND_FAILED")
        return result.stdout

    def json(self, args: list[str], *, timeout: int = 30) -> Any:
        try:
            return json.loads(self.call(args, timeout=timeout))
        except (ValueError, UnicodeError):
            raise DrillBlocked("DOCKER_INVALID_JSON") from None

    def verify_local(self) -> dict[str, str]:
        endpoint = self.json(["context", "inspect", CONTEXT])[0]["Endpoints"]["docker"][
            "Host"
        ]
        require(endpoint == PIPE, "DOCKER_CONTEXT_NOT_LOCAL")
        server = self.json(["version", "--format", "{{json .Server}}"])
        require(
            isinstance(server, dict) and server.get("Os") == "linux",
            "LINUX_ENGINE_REQUIRED",
        )
        self.ready = True
        return {
            "context": CONTEXT,
            "os": server["Os"],
            "version": str(server["Version"]),
        }

    def image(self, *, pull: bool) -> dict[str, str]:
        require(self.ready, "LOCAL_DOCKER_NOT_VERIFIED")
        if pull:
            self.call(["pull", IMAGE], timeout=600)
        value = self.json(["image", "inspect", IMAGE])[0]
        digest = next(
            (
                item
                for item in value.get("RepoDigests", [])
                if item.startswith("postgres@sha256:")
            ),
            None,
        )
        require(
            digest is not None
            and re.fullmatch(r"postgres@sha256:[a-f0-9]{64}", digest),
            "POSTGRES_IMAGE_DIGEST_REQUIRED",
        )
        require(value.get("Os") == "linux", "LINUX_IMAGE_REQUIRED")
        return {"reference": IMAGE, "digest": digest, "id": value["Id"]}

    def inspect_optional(self, kind: str, name: str) -> dict[str, Any] | None:
        require(kind in {"container", "volume"}, "RESOURCE_KIND")
        require(
            name == CONTAINER if kind == "container" else name in VOLUMES,
            "DRILL_RESOURCE_NAME",
        )
        listing = (
            self.call(
                [kind, "ls", "--all", "--format", "{{.Names}}"]
                if kind == "container"
                else [kind, "ls", "--format", "{{.Name}}"]
            )
            .decode()
            .splitlines()
        )
        if name not in listing:
            return None
        value = self.json([kind, "inspect", name])[0]
        labels = (
            value.get("Labels", {})
            if kind == "volume"
            else value.get("Config", {}).get("Labels", {})
        )
        require(labels.get(LABEL) == OWNER, "EXISTING_RESOURCE_NOT_OWNED")
        return value

    def create_container(self, image: dict[str, str]) -> dict[str, Any]:
        require(self.ready, "LOCAL_DOCKER_NOT_VERIFIED")
        volumes = {
            volume: self.inspect_optional("volume", volume) for volume in VOLUMES
        }
        existing = self.inspect_optional("container", CONTAINER)
        if existing is not None:
            self.validate_container(existing, image)
        for volume, value in volumes.items():
            if value is None:
                self.call(["volume", "create", "--label", LABEL + "=" + OWNER, volume])
        if existing is None:
            self.call(
                [
                    "run",
                    "--detach",
                    "--name",
                    CONTAINER,
                    "--label",
                    LABEL + "=" + OWNER,
                    "--publish",
                    f"127.0.0.1:{PORT}:5432",
                    "--env",
                    "POSTGRES_HOST_AUTH_METHOD=trust",
                    "--env",
                    "POSTGRES_USER=b1_drill_admin",
                    "--env",
                    "POSTGRES_DB=b1_drill_control",
                    "--volume",
                    VOLUMES[0] + ":/var/lib/postgresql/data",
                    "--volume",
                    VOLUMES[1] + ":/b1",
                    image["digest"],
                ],
                timeout=120,
            )
        value = self.inspect_optional("container", CONTAINER)
        self.validate_container(value, image)
        return {
            "name": CONTAINER,
            "volumes": list(VOLUMES),
            "loopback_port": PORT,
            "retained": True,
        }

    @staticmethod
    def validate_container(value: dict[str, Any] | None, image: dict[str, str]) -> None:
        require(
            value is not None and value["State"]["Running"],
            "DRILL_CONTAINER_NOT_RUNNING",
        )
        require(value.get("Image") == image["id"], "DRILL_CONTAINER_IMAGE_CHANGED")
        bindings = value["HostConfig"]["PortBindings"]
        require(
            bindings == {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]},
            "LOOPBACK_PORT_REQUIRED",
        )
        mounts = {
            (item["Type"], item.get("Name"), item["Destination"])
            for item in value["Mounts"]
        }
        require(
            mounts
            == {
                ("volume", VOLUMES[0], "/var/lib/postgresql/data"),
                ("volume", VOLUMES[1], "/b1"),
            },
            "DRILL_VOLUME_MOUNTS_CHANGED",
        )
        require(
            value["HostConfig"].get("Privileged") is False, "DRILL_CONTAINER_PRIVILEGED"
        )
        require(
            value["HostConfig"].get("NetworkMode") in {"default", "bridge"},
            "DRILL_CONTAINER_NETWORK",
        )

    def execute(
        self, arguments: list[str], *, stdin: bytes | None = None, user: str = "root"
    ) -> bytes:
        require(self.ready, "LOCAL_DOCKER_NOT_VERIFIED")
        require(user in {"root", "postgres"}, "DRILL_OS_USER")
        return self.call(
            ["exec", "--interactive", "--user", user, CONTAINER, *arguments],
            stdin=stdin,
            timeout=120,
        )

    def wait_postgres(self, sleeper: Callable[[float], Any] = time.sleep) -> None:
        require(self.ready, "LOCAL_DOCKER_NOT_VERIFIED")
        for attempt in range(10):
            try:
                self.call(
                    [
                        "exec",
                        CONTAINER,
                        "pg_isready",
                        "--host=127.0.0.1",
                        "--port=5432",
                        "--username=b1_drill_admin",
                    ],
                    timeout=3,
                )
                return
            except DrillBlocked as error:
                if error.code != "DOCKER_COMMAND_FAILED":
                    raise
                if attempt < 9:
                    sleeper(1)
        raise DrillBlocked("POSTGRES_STARTUP_NOT_READY")

    def sql(
        self, database: str, statement: str, *, role: str = "b1_drill_admin"
    ) -> str:
        require(
            database
            in {
                "b1_drill_control",
                "zhiming_core_stage",
                "zhiming_core_b1_restore",
                "core_test_b1",
                "zhiming_core_b1_web",
                "b1_drill_rollback",
                "b1_drill_ledger",
            },
            "DRILL_DATABASE_NAME",
        )
        require(
            re.fullmatch(
                r"b1_drill_admin|zhiming_core_(?:stage|b1_restore|b1_web)_(?:owner|writer)",
                role,
            ),
            "DRILL_ROLE_NAME",
        )
        result = self.execute(
            [
                "psql",
                "--host=127.0.0.1",
                "--port=5432",
                "--no-psqlrc",
                "--quiet",
                "--tuples-only",
                "--no-align",
                "--set=ON_ERROR_STOP=1",
                "--username=" + role,
                "--dbname=" + database,
            ],
            stdin=statement.encode("utf-8"),
        )
        return result.decode("utf-8").strip()
