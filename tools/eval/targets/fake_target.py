"""Framework-only action replay; no simulated v4 business implementation."""

from copy import deepcopy
from typing import Any

from tools.eval.providers.scripted import ScriptedProvider
from tools.eval.targets.base import TurnResult


class FakeTarget:
    """Interpret independent scripted observations, never the expect block."""

    def __init__(self) -> None:
        self._db: dict[str, Any] = {}
        self._provider = ScriptedProvider([])

    def reset(self, seed: dict[str, Any]) -> None:
        self._db = {"entities": deepcopy(seed.get("entities", []))}
        for fact in seed.get("facts", []):
            data = {key: value for key, value in fact.items() if key not in {"id", "status", "data"}}
            data.update(fact.get("data", {}))
            self._db["entities"].append(
                {
                    "id": fact["id"],
                    "kind": "fact",
                    "status": fact.get("status", "active"),
                    "data": data,
                }
            )
        self._db.setdefault("thread", deepcopy(seed.get("thread", [])))
        for key in ("settings", "context", "controls"):
            self._db[key] = deepcopy(seed.get(key, {}))
        self._provider = ScriptedProvider(seed.get("_scripted", []))

    def send(self, turn: dict[str, Any]) -> TurnResult:
        actions = self._provider.replay(turn["_index"])
        result = TurnResult(model_calls=1)
        for action in actions:
            self._apply(action, result)
        result.db = self.inspect_db()
        return result

    def _apply(self, action: dict[str, Any], result: TurnResult) -> None:
        if "text" in action:
            result.text += action["text"]
        call = action.get("tool_call")
        if call:
            result.tools_called.append(call["name"])
        if "tool" in action:
            result.tools_called.append(action["tool"])
        if "receipt" in action:
            result.receipts.append(deepcopy(action["receipt"]))
        returned = action.get("result", {})
        if isinstance(returned, dict) and "receipt" in returned:
            result.receipts.append(deepcopy(returned["receipt"]))
        if "db" in action:
            self._db.update(deepcopy(action["db"]))
        if "event" in action:
            event = action["event"]
            result.events.append(event if isinstance(event, str) else event["type"])
        if "error" in action:
            result.error = action["error"]
        if "meta" in action:
            result.metadata.update(deepcopy(action["meta"]))

    def inspect_db(self) -> dict[str, Any]:
        return deepcopy(self._db)

    def close(self) -> None:
        self._db.clear()
