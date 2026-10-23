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
    the runtime submits it to the safety layer first.

    Attributes:
        name: which action is requested. It must be on the policy's allowed list.
        params: the arguments, as plain JSON-style data. The safety layer reads
            them and the trace records them. Treat them as read-only: `frozen=True`
            protects the fields, not the contents of this dict (README limitation L6).
        cost: a finite number >= 0 that is counted against the agent's budget.
            The agent declares it and the safety layer is meant to validate it
            (README limitation L1). Take costs from trusted code, such as a tool table.
    """

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    cost: float = 1.0


class Agent(ABC):
    """Base class for all MUFFIN agents.

    Override `decide` and `act`. Everything else has a default.
    """

    def perceive(self, raw_input: Any) -> Any:
        """Turn raw input into a perception. Default: return it unchanged."""
        return raw_input

    def update_beliefs(self, perception: Any) -> None:
        """Update the agent's internal state from the perception. Default: do nothing."""
        return None

    @abstractmethod
    def decide(self) -> Action | None:
        """Return the next proposed action, or None to do nothing."""

    @abstractmethod
    def act(self, action: Action) -> Any:
        """Execute an action the safety layer has approved.

        The return value is recorded as the outcome. This is your own code: in v0.1
        nothing stops it from doing more than the approved action (README limitation L5),
        so keep every side effect inside actions that go through the runtime.
        """

    def explain(self) -> str | None:
        """Optional: why the agent chose its last action.

        Recorded in the decision trace as `explanation`. It is the agent's own claim,
        so treat it as evidence for debugging, not proof of the real reason.
        """
        return None

    # State capture is what makes checkpoint and rollback possible.
    def get_state(self) -> dict[str, Any]:
        """Return everything about this agent that a rollback must restore.

        Use a JSON-friendly dict, and copy lists and dicts instead of returning your
        own references. The default returns an empty dict, which means rollback
        restores nothing about your agent unless you override this.
        """
        return {}

    def set_state(self, state: dict[str, Any]) -> None:
        """Restore this agent from a dict that `get_state` produced.

        Copy mutable values (lists, dicts) rather than keeping references to `state`.
        """
        return None
