"""Safety layer: default-deny, fail-closed enforcement outside the agent's control."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from .agent import Action

Constraint = Callable[[Action], "str | None"]  # returns a denial reason, or None to allow


@dataclass
class Policy:
    allowed_actions: set[str]                      # default deny: anything else is blocked
    max_total_cost: float = float("inf")           # lifetime action budget
    max_actions_per_window: int | None = None      # rate limit
    window_seconds: float = 60.0
    constraints: list[Constraint] = field(default_factory=list)


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str


class SafetyLayer:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._policies: dict[str, Policy] = {}
        self._spent: dict[str, float] = {}
        self._recent: dict[str, deque[float]] = {}
        self._killed: dict[str, str] = {}

    def register(self, agent_id: str, policy: Policy) -> None:
        self._policies[agent_id] = policy
        self._spent[agent_id] = 0.0
        self._recent[agent_id] = deque()

    # ---- kill switch -------------------------------------------------
    def trip_kill_switch(self, agent_id: str, reason: str) -> None:
        self._killed[agent_id] = reason

    def is_killed(self, agent_id: str) -> str | None:
        return self._killed.get(agent_id)

    # ---- enforcement -------------------------------------------------
    def check(self, agent_id: str, action: Action) -> Verdict:
        try:
            return self._check(agent_id, action)
        except Exception as exc:  # fail closed: no verdict means no action
            return Verdict(False, f"safety error, failing closed: {exc!r}")

    def _check(self, agent_id: str, action: Action) -> Verdict:
        if agent_id in self._killed:
            return Verdict(False, f"kill switch tripped: {self._killed[agent_id]}")
        policy = self._policies.get(agent_id)
        if policy is None:
            return Verdict(False, "no policy registered")
        if action.name not in policy.allowed_actions:
            return Verdict(False, f"action '{action.name}' not in allowed set (default deny)")
        if self._spent[agent_id] + action.cost > policy.max_total_cost:
            return Verdict(False, "total action budget exceeded")
        if policy.max_actions_per_window is not None:
            now = self._clock()
            window = self._recent[agent_id]
            while window and now - window[0] > policy.window_seconds:
                window.popleft()
            if len(window) >= policy.max_actions_per_window:
                return Verdict(False, "rate limit exceeded")
        for constraint in policy.constraints:
            reason = constraint(action)
            if reason:
                return Verdict(False, f"constraint violated: {reason}")
        return Verdict(True, "ok")

    def commit(self, agent_id: str, action: Action) -> None:
        """Record spend after an approved action actually executes."""
        self._spent[agent_id] += action.cost
        self._recent[agent_id].append(self._clock())

    # ---- checkpoint support -----------------------------------------
    def snapshot(self, agent_id: str) -> dict[str, float]:
        return {"spent": self._spent[agent_id]}

    def restore(self, agent_id: str, snap: dict[str, float]) -> None:
        self._spent[agent_id] = snap["spent"]
