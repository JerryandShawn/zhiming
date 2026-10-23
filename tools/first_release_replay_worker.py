"""Standalone read-only local worker: standard-library bootstrap, then reviewed candidate imports."""

from __future__ import annotations

import hashlib
import importlib
import importlib.abc
import importlib.machinery
import importlib.metadata
import json
import os
import sys
import sysconfig
from pathlib import Path


class Blocked(RuntimeError):
    """Only finite non-secret codes cross the process boundary."""


def require(value, code):
    if not value:
        raise Blocked(code)


def verified(path, root, files):
    path = Path(path)
    require(path.is_absolute() and path.suffix == ".py" and path.is_file(), "PREFLIGHT_IMPORT_ORIGIN")
    require(not any(item.is_symlink() for item in (path, *path.parents)), "PREFLIGHT_IMPORT_ORIGIN")
    try:
        name = path.relative_to(root).as_posix()
    except ValueError:
        raise Blocked("PREFLIGHT_IMPORT_ORIGIN") from None
    require(name in files, "PREFLIGHT_IMPORT_ORIGIN")
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == files[name]["sha256"], "PREFLIGHT_SOURCE_CHANGED")
    require(
        hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == files[name]["git_blob_sha1"],
        "PREFLIGHT_SOURCE_CHANGED",
    )


class CandidateFinder(importlib.abc.MetaPathFinder):
    def __init__(self, root, files):
        self.root, self.files = root, files

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] not in {"tools", "mingjing_core"}:
            return None
        folder = self.root.joinpath(*fullname.split(".")[:-1])
        spec = importlib.machinery.PathFinder.find_spec(fullname, [str(folder)])
        require(spec is not None, "PREFLIGHT_IMPORT_ORIGIN")
        if spec.origin is None:
            namespace = self.root.joinpath(*fullname.split("."))
            require(
                namespace.is_dir()
                and any(name.startswith(namespace.relative_to(self.root).as_posix() + "/") for name in self.files),
                "PREFLIGHT_IMPORT_ORIGIN",
            )
            spec.submodule_search_locations = [str(namespace)]
        else:
            verified(spec.origin, self.root, self.files)
            require(isinstance(spec.loader, importlib.machinery.SourceFileLoader), "PREFLIGHT_IMPORT_ORIGIN")
        return spec


def business_origins(root, files):
    count = 0
    for name, module in tuple(sys.modules.items()):
        if name.split(".")[0] not in {"tools", "mingjing_core"}:
            continue
        spec = getattr(module, "__spec__", None)
        require(spec is not None and spec.name == name, "PREFLIGHT_IMPORT_ORIGIN")
        if spec.origin is None:
            expected = [str(root.joinpath(*name.split(".")))]
            require(
                list(module.__path__) == list(spec.submodule_search_locations) == expected, "PREFLIGHT_IMPORT_ORIGIN"
            )
        else:
            verified(module.__file__, root, files)
            require(Path(module.__file__) == Path(spec.origin), "PREFLIGHT_IMPORT_ORIGIN")
            if spec.submodule_search_locations is not None:
                expected = [str(Path(spec.origin).parent)]
                require(
                    list(module.__path__) == list(spec.submodule_search_locations) == expected,
                    "PREFLIGHT_IMPORT_ORIGIN",
                )
        count += 1
    return count


def runtime(value, root):
    require(sys.version_info[:2] == (3, 11) and sys.prefix != sys.base_prefix, "PREFLIGHT_RUNTIME")
    require(Path(sys.executable).resolve() == Path(value["python"]).resolve(), "PREFLIGHT_RUNTIME")
    require(
        hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest() == value["pin"]["python_sha256"],
        "PREFLIGHT_RUNTIME",
    )
    require(
        sys.flags.isolated and sys.dont_write_bytecode and sys.pycache_prefix == os.path.abspath(os.devnull),
        "PREFLIGHT_RUNTIME",
    )
    sites = {Path(sysconfig.get_path(key)).resolve() for key in ("purelib", "platlib")}
    require(
        all(site.is_relative_to(Path(sys.prefix).resolve()) and site.is_dir() for site in sites), "PREFLIGHT_RUNTIME"
    )
    source = (root / "requirements-core.lock").read_bytes()
    require(hashlib.sha256(source).hexdigest() == value["core_lock_sha256"], "PREFLIGHT_CORE_LOCK")
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    pins, extras, environment = {}, {}, default_environment()
    for line in source.decode().splitlines():
        if not line or line[0].isspace() or line.startswith("#"):
            continue
        requirement = Requirement(line.rstrip(" \\"))
        if requirement.marker and not requirement.marker.evaluate(environment):
            continue
        name = canonicalize_name(requirement.name)
        versions = list(requirement.specifier)
        require(not requirement.url and len(versions) == 1 and versions[0].operator == "==", "PREFLIGHT_CORE_LOCK")
        version = versions[0].version
        require(name not in pins or pins[name] == version, "PREFLIGHT_CORE_LOCK")
        pins[name] = version
        extras.setdefault(name, set()).update(requirement.extras)
    require(pins, "PREFLIGHT_CORE_LOCK")
    for name, version in pins.items():
        distribution = importlib.metadata.distribution(name)
        require(
            distribution.version == version
            and any(Path(distribution.locate_file("")).resolve().is_relative_to(site) for site in sites),
            "PREFLIGHT_DEPENDENCY",
        )
    edges = dependency_edges(pins, extras, environment, Requirement, canonicalize_name)
    return sites, {
        "active_core_pins": len(pins),
        "active_dependency_edges": edges,
        "python_version": sys.version.split()[0],
    }


def dependency_edges(pins, extras, environment, requirement_class, canonicalize):
    queue, visited, edges = list(pins), set(), 0
    while queue:
        name = queue.pop()
        enabled = extras.setdefault(name, set())
        signature = name, tuple(sorted(enabled))
        if signature in visited:
            continue
        visited.add(signature)
        for raw in importlib.metadata.requires(name) or []:
            requirement = requirement_class(raw)
            if requirement.marker and not any(
                requirement.marker.evaluate(dict(environment, extra=extra)) for extra in ("", *enabled)
            ):
                continue
            child_name = canonicalize(requirement.name)
            require(
                not requirement.url and child_name in pins and pins[child_name] in requirement.specifier,
                "PREFLIGHT_DEPENDENCY",
            )
            edges += 1
            child = extras.setdefault(child_name, set())
            if requirement.extras - child:
                child.update(requirement.extras)
                queue.append(child_name)
    return edges


def third_party_origins(sites):
    for name in (
        "packaging",
        "psycopg",
        "psycopg_pool",
        "pydantic",
        "langgraph",
        "langgraph.graph",
        "langgraph.checkpoint",
        "langgraph.checkpoint.postgres",
    ):
        module = importlib.import_module(name)
        spec = module.__spec__
        require(spec is not None and spec.name == name, "PREFLIGHT_IMPORT_ORIGIN")
        if spec.origin is not None:
            actual = Path(module.__file__).resolve()
            require(
                actual == Path(spec.origin).resolve() and any(actual.is_relative_to(site) for site in sites),
                "PREFLIGHT_IMPORT_ORIGIN",
            )
        if spec.submodule_search_locations is not None:
            require(list(module.__path__) == list(spec.submodule_search_locations), "PREFLIGHT_IMPORT_ORIGIN")
            require(
                all(any(Path(path).resolve().is_relative_to(site) for site in sites) for path in module.__path__),
                "PREFLIGHT_IMPORT_ORIGIN",
            )


def target(value, repository):
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    dsn = os.environ.get("FIRST_RELEASE_CANDIDATE_OWNER_DSN", "")
    fields = conninfo_to_dict(dsn)
    require(not any(key.startswith("PG") and item for key, item in os.environ.items()), "PREFLIGHT_TARGET")
    allowed = {"host", "hostaddr", "port", "dbname", "user", "password", "passfile", "connect_timeout"}
    require(
        set(fields) <= allowed
        and fields.get("host") in {"127.0.0.1", "::1"}
        and fields.get("port") in {"55480", "55481"},
        "PREFLIGHT_TARGET",
    )
    require(
        fields.get("dbname") == value["database"] and fields.get("user") == value["database"] + "_owner",
        "PREFLIGHT_TARGET",
    )
    require(
        fields.get("hostaddr", fields["host"]) == fields["host"] and fields.get("passfile", os.devnull) == os.devnull,
        "PREFLIGHT_TARGET",
    )
    readonly = make_conninfo(dsn, options="-c default_transaction_read_only=on -c search_path=pg_catalog")
    repo = repository.PostgresRepository(readonly, initialize=False, max_size=1)
    try:
        with repo.transaction() as connection:
            row = connection.execute(
                "SELECT current_database() AS database,current_user AS role,session_user AS session_role,"
                "host(inet_server_addr()) AS host,inet_server_port() AS port,"
                "current_setting('server_version_num')::int AS version,"
                "current_setting('transaction_read_only') AS readonly,"
                "current_setting('search_path') AS path"
            ).fetchone()
            require(
                (row["database"], row["role"], row["session_role"], row["host"], row["port"])
                == (value["database"], fields["user"], fields["user"], fields["host"], int(fields["port"])),
                "PREFLIGHT_TARGET",
            )
            require(
                150000 <= row["version"] < 160000 and row["readonly"] == "on" and row["path"] == "pg_catalog",
                "PREFLIGHT_TARGET",
            )
            require(repo.verify_schema()["checksums"] == value["migrations"], "PREFLIGHT_TARGET")
            owners = sorted(row["id"] for row in connection.execute("SELECT id FROM mingjing_core.core_owners"))
            require(owners == value["owners"], "PREFLIGHT_OWNER_SET")
            counts = connection.execute(
                "SELECT count(*) FILTER(WHERE status IN ('queued','running')) AS active,"
                "count(*) FILTER(WHERE lease_until>now()) AS leased FROM mingjing_core.core_runs"
            ).fetchone()
            require(counts == {"active": 0, "leased": 0}, "PREFLIGHT_ACTIVE_RUN")
            for table in ("core_model_accounts", "core_model_batches", "core_model_authorizations", "core_model_usage"):
                require(
                    connection.execute("SELECT count(*) AS n FROM mingjing_core." + table).fetchone()["n"] == 0,
                    "PREFLIGHT_CENTRAL_NOT_EMPTY",
                )
            connection.execute("SELECT last_value,is_called FROM mingjing_core.core_model_usage_id_seq").fetchone()
        return {"owners_checked": len(owners), "active_runs": 0, "live_leases": 0, "central_tables_empty": True}
    finally:
        repo.close()


def run(value):
    require(
        not any(name.split(".")[0] in {"tools", "mingjing_core"} for name in sys.modules),
        "PREFLIGHT_PRELOADED_BUSINESS",
    )
    root = Path(value["root"])
    raw = (root / "__release_manifest__.json").read_bytes()
    require(hashlib.sha256(raw).hexdigest() == value["pin"]["manifest_sha256"], "PREFLIGHT_SOURCE_CHANGED")
    manifest = json.loads(raw)
    require(manifest["commit"] == value["pin"]["candidate"], "PREFLIGHT_SOURCE_CHANGED")
    files = manifest["files"]
    sys.meta_path.insert(0, CandidateFinder(root, files))
    sys.path.insert(0, str(root))
    sites, installed = runtime(value, root)
    repository = importlib.import_module("mingjing_core.repositories.postgres")
    deployment = importlib.import_module("tools.deploy_core")
    importlib.import_module("mingjing_core.application.memory")
    importlib.import_module("mingjing_core.runtime")
    importlib.import_module("tools.deploy_core_withdrawals")
    for function in (
        deployment.apply_withdrawals,
        deployment.export_withdrawals,
        repository.PostgresRepository.verify_schema,
    ):
        verified(function.__code__.co_filename, root, files)
    third_party_origins(sites)
    business_origins(root, files)
    observed = target(value, repository)
    third_party_origins(sites)
    modules = business_origins(root, files)
    return {
        "schema": "first-release-local-candidate-preflight-v1",
        "candidate": value["pin"]["candidate"],
        "database": value["database"],
        "manifest_sha256": value["pin"]["manifest_sha256"],
        "python_sha256": value["pin"]["python_sha256"],
        "worker_sha256": value["pin"]["worker_sha256"],
        "ledger_sha256": value["pin"]["ledger_sha256"],
        "core_lock_sha256": value["core_lock_sha256"],
        **installed,
        **observed,
        "candidate_modules_checked": modules,
        "database_connections": 1,
        "read_only": True,
        "mutations": 0,
        "local_preflight_completed": True,
        "latest_withdrawals_replayed": False,
        "runtime_verified": False,
        "native_restore_completed": False,
        "linux_attestation": False,
        "publication": False,
        "model_calls": 0,
        "external_sends": 0,
    }


if __name__ == "__main__":
    try:
        result = run(globals().get("_PREFLIGHT_INPUT"))  # Supplied only by the reviewed stdlib bootstrap.
    except Blocked as error:
        result = {"status": "blocked", "code": str(error)}
    except importlib.metadata.PackageNotFoundError:
        result = {"status": "blocked", "code": "PREFLIGHT_DEPENDENCY"}
    except Exception:
        result = {"status": "blocked", "code": "LOCAL_CANDIDATE_PREFLIGHT_FAILED"}
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(2 if result.get("status") == "blocked" else 0)
