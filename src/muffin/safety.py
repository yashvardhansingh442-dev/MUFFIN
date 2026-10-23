
"""Safety layer: default-deny, fail-closed enforcement outside the agent's control."""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from numbers import Real
from typing import Callable, Any

from .agent import Action

Constraint = Callable[[Action], str | None]
ParamRule = Callable[[dict], str | None]


def _valid_cost(value: Any) -> bool:
    """Accept finite, non-negative numeric costs; bool is deliberately rejected."""
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def _valid_budget(value: Any) -> bool:
    """Budgets may be positive infinity (unlimited), but never NaN or negative."""
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and not math.isnan(value)
        and value >= 0
    )


@dataclass
class Policy:
    allowed_actions: set[str]
    max_total_cost: float = float("inf")
    max_actions_per_window: int | None = None
    window_seconds: float = 60.0
    constraints: list[Constraint] = field(default_factory=list)
    param_rules: dict[str, list[ParamRule]] = field(default_factory=dict)


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str


class SafetyLayer:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        if not callable(clock):
            raise TypeError("clock must be callable")

        self._clock = clock
        self._policies: dict[str, Policy] = {}
        self._spent: dict[str, float] = {}
        self._recent: dict[str, deque[float]] = {}
        self._killed: dict[str, str] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _validate_policy(policy: Policy) -> None:
        if not isinstance(policy, Policy):
            raise TypeError("policy must be a Policy instance")

        if not isinstance(policy.allowed_actions, set):
            raise TypeError("allowed_actions must be a set")
        if any(not isinstance(name, str) or not name for name in policy.allowed_actions):
            raise ValueError("allowed action names must be non-empty strings")

        if not _valid_budget(policy.max_total_cost):
            raise ValueError("max_total_cost must be non-negative and not NaN")

        limit = policy.max_actions_per_window
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
        ):
            raise ValueError("max_actions_per_window must be a positive integer or None")

        if (
            isinstance(policy.window_seconds, bool)
            or not isinstance(policy.window_seconds, Real)
            or not math.isfinite(policy.window_seconds)
            or policy.window_seconds <= 0
        ):
            raise ValueError("window_seconds must be finite and greater than zero")

        if not isinstance(policy.constraints, list) or any(
            not callable(rule) for rule in policy.constraints
        ):
            raise ValueError("constraints must be a list of callables")

        if not isinstance(policy.param_rules, dict):
            raise TypeError("param_rules must be a dictionary")

        for name, rules in policy.param_rules.items():
            if not isinstance(name, str) or not name:
                raise ValueError("parameter-rule action names must be non-empty strings")
            if not isinstance(rules, list) or any(not callable(rule) for rule in rules):
                raise ValueError(f"parameter rules for {name!r} must be a list of callables")

    @staticmethod
    def _validate_action(action: Any) -> str | None:
        """Return a reason if the action is malformed or has an unsafe cost."""
        try:
            name = action.name
            params = action.params
            cost = action.cost
        except Exception:
            return "malformed action"

        if not isinstance(name, str) or not name:
            return "action name must be a non-empty string"
        if not isinstance(params, dict):
            return "action params must be a dictionary"
        if not _valid_cost(cost):
            return "action cost must be a finite, non-negative number"

        return None

    def register(self, agent_id: str, policy: Policy) -> None:
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("agent_id must be a non-empty string")
        self._validate_policy(policy)

        with self._lock:
            self._policies[agent_id] = policy
            self._spent[agent_id] = 0.0
            self._recent[agent_id] = deque()
            self._killed.pop(agent_id, None)

    # ---- kill switch -------------------------------------------------

    def trip_kill_switch(self, agent_id: str, reason: str) -> None:
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("agent_id must be a non-empty string")
        if not isinstance(reason, str) or not reason:
            raise ValueError("kill-switch reason must be a non-empty string")

        with self._lock:
            self._killed[agent_id] = reason

    def is_killed(self, agent_id: str) -> str | None:
        with self._lock:
            return self._killed.get(agent_id)

    # ---- enforcement -------------------------------------------------

    def check(self, agent_id: str, action: Action) -> Verdict:
        """Fail closed: any malformed state or rule error denies the action."""
        try:
            with self._lock:
                return self._check(agent_id, action)
        except Exception:
            # Avoid leaking exception details from constraints or internal state.
            return Verdict(False, "safety error, failing closed")

    def _check(self, agent_id: str, action: Action) -> Verdict:
        if not isinstance(agent_id, str) or not agent_id:
            return Verdict(False, "invalid agent id")

        if agent_id in self._killed:
            return Verdict(False, f"kill switch tripped: {self._killed[agent_id]}")

        policy = self._policies.get(agent_id)
        if policy is None:
            return Verdict(False, "no policy registered")

        invalid = self._validate_action(action)
        if invalid:
            return Verdict(False, invalid)

        if action.name not in policy.allowed_actions:
            return Verdict(False, f"action {action.name!r} not in allowed set (default deny)")

        # Validate mutable policy state again in case it was changed after registration.
        self._validate_policy(policy)

        if self._spent[agent_id] + action.cost > policy.max_total_cost:
            return Verdict(False, "total action budget exceeded")

        if policy.max_actions_per_window is not None:
            now = self._clock()
            if not isinstance(now, Real) or not math.isfinite(now):
                return Verdict(False, "invalid safety clock, failing closed")

            window = self._recent[agent_id]
            while window and now - window[0] >= policy.window_seconds:
                window.popleft()

            if len(window) >= policy.max_actions_per_window:
                return Verdict(False, "rate limit exceeded")

        for rule in policy.param_rules.get(action.name, []):
            reason = rule(action.params)
            if reason:
                return Verdict(False, f"parameter rule violated: {reason}")

        for constraint in policy.constraints:
            reason = constraint(action)
            if reason:
                return Verdict(False, f"constraint violated: {reason}")

        return Verdict(True, "ok")

    def commit(self, agent_id: str, action: Action) -> None:
        """Record spend after an approved action actually executes.

        Call only after check() allows the action and execution has occurred.
        check() + execution + commit() is NOT an atomic reservation.
        """
        with self._lock:
            if not isinstance(agent_id, str) or agent_id not in self._policies:
                raise ValueError("cannot commit for an unregistered agent")

            invalid = self._validate_action(action)
            if invalid:
                raise ValueError(f"cannot commit invalid action: {invalid}")

            now = self._clock()
            if not isinstance(now, Real) or not math.isfinite(now):
                raise ValueError("invalid safety clock")

            policy = self._policies[agent_id]
            new_spent = self._spent[agent_id] + action.cost
            if not math.isfinite(new_spent) or new_spent > policy.max_total_cost:
                raise ValueError("commit would exceed the action budget")

            self._spent[agent_id] = new_spent
            self._recent[agent_id].append(float(now))

    # ---- checkpoint support -----------------------------------------

    def snapshot(self, agent_id: str) -> dict[str, float]:
        with self._lock:
            if agent_id not in self._policies:
                raise ValueError("no policy registered for agent")
            return {"spent": self._spent[agent_id]}

    def restore(self, agent_id: str, snap: dict[str, float]) -> None:
        """Restore budget spend only; rate limits and kill switches are not rolled back."""
        if not isinstance(snap, dict) or "spent" not in snap:
            raise ValueError("snapshot must contain 'spent'")

        spent = snap["spent"]
        if not _valid_budget(spent) or not math.isfinite(spent):
            raise ValueError("snapshot spend must be finite and non-negative")

        with self._lock:
            if agent_id not in self._policies:
                raise ValueError("no policy registered for agent")
            if spent > self._policies[agent_id].max_total_cost:
                raise ValueError("snapshot spend exceeds the current budget")
            self._spent[agent_id] = float(spent)
