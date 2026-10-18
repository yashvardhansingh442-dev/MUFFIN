"""Agent SDK: what an agent developer implements.

The developer writes perception, belief update, decision, and action logic.
Lifecycle, memory, safety, and logging are provided by the runtime.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Action:
    """An action an agent proposes. It is never executed directly:
    the runtime submits it to the safety layer first."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    cost: float = 1.0


class Agent(ABC):
    """Base class for all MUFFIN agents."""

    def perceive(self, raw_input: Any) -> Any:
        return raw_input

    def update_beliefs(self, perception: Any) -> None:
        return None

    @abstractmethod
    def decide(self) -> Action | None:
        """Return the next proposed action, or None to do nothing."""

    @abstractmethod
    def act(self, action: Action) -> Any:
        """Execute an action the safety layer has approved."""

    def explain(self) -> str | None:
        """Optional: why the agent chose its last action. Recorded in the decision trace."""
        return None

    # State capture is what makes checkpoint and rollback possible.
    def get_state(self) -> dict[str, Any]:
        return {}

    def set_state(self, state: dict[str, Any]) -> None:
        return None
