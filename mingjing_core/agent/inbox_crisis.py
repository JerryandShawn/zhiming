"""A newly adopted crisis original closes tools before the next model request."""

from dataclasses import replace

from mingjing_core.application.agent_crisis_sources import turn_has_crisis
from mingjing_core.application.agent_runtime_state import RuntimeState
from mingjing_core.models.port import ChatMessage

from .prompts import load_prompts


def refresh_crisis(cycle):
    if cycle.crisis or not turn_has_crisis(cycle.registry.service.repo, cycle.run, cycle.current_sources):
        return
    cycle.crisis = True
    cycle.policy = replace(cycle.policy, text_only=True, only_tool=None)
    cycle.control.no_text_seconds, cycle.control.has_text = 20, False
    instruction = ChatMessage("system", load_prompts().render("crisis"))
    if instruction not in cycle.messages:
        cycle.messages.append(instruction)
    RuntimeState(cycle.registry.service.repo).metadata(cycle.run, inbox_crisis=True)
