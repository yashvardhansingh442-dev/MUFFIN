"""Cognitive runtime: an OS for agents. Owns lifecycle, memory, safety, and tracing."""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from .agent import Agent
from .memory import EpisodicMemory
from .safety import Policy, SafetyLayer
from .trace import TraceLog


class State(str, Enum):
    CONFIGURED = "configured"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    TERMINATED = "terminated"


class MuffinRuntimeError(Exception):
    pass


@dataclass
class _Handle:
    agent: Agent
    state: State
    step: int = 0
    checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict)


class Runtime:
    def __init__(self, db_path: str = ":memory:", trace_path: str | None = None,
                 safety: SafetyLayer | None = None) -> None:
        self.memory = EpisodicMemory(db_path)
        self.safety = safety or SafetyLayer()
        self.trace = TraceLog(trace_path)
        self._agents: dict[str, _Handle] = {}

    # ---- lifecycle ---------------------------------------------------
    def spawn(self, agent: Agent, policy: Policy) -> str:
        agent_id = uuid.uuid4().hex[:8]
        self.safety.register(agent_id, policy)
        self._agents[agent_id] = _Handle(agent=agent, state=State.CONFIGURED)
        self.trace.record(agent_id, "spawned", state=State.CONFIGURED.value)
        return agent_id

    def start(self, agent_id: str) -> None:
        self._transition(agent_id, {State.CONFIGURED}, State.RUNNING, "started")

    def pause(self, agent_id: str) -> None:
        self._transition(agent_id, {State.RUNNING}, State.PAUSED, "paused")

    def resume(self, agent_id: str) -> None:
        self._transition(agent_id, {State.PAUSED}, State.RUNNING, "resumed")

    def kill(self, agent_id: str, reason: str = "operator") -> None:
        """Terminate; state and memory are preserved for post-mortem."""
        h = self._handle(agent_id)
        self.safety.trip_kill_switch(agent_id, reason)
        h.state = State.TERMINATED
        self.trace.record(agent_id, "killed", reason=reason)

    def state(self, agent_id: str) -> State:
        return self._handle(agent_id).state

    # ---- checkpoint / rollback --------------------------------------
    def checkpoint(self, agent_id: str) -> str:
        h = self._handle(agent_id)
        if h.state == State.TERMINATED:
            raise MuffinRuntimeError("cannot checkpoint a terminated agent")
        cp_id = uuid.uuid4().hex[:8]
        h.checkpoints[cp_id] = {
            "agent_state": copy.deepcopy(h.agent.get_state()),
            "memory_marker": self.memory.last_id(agent_id),
            "safety": self.safety.snapshot(agent_id),
            "step": h.step,
        }
        self.trace.record(agent_id, "checkpoint", checkpoint_id=cp_id, step=h.step)
        return cp_id

    def rollback(self, agent_id: str, checkpoint_id: str) -> None:
        """Restore agent state, safety counters, and episodic memory. Agent ends PAUSED.
        Note: this cannot undo side effects the agent already had on the outside world."""
        h = self._handle(agent_id)
        if h.state == State.TERMINATED:
            raise MuffinRuntimeError("cannot roll back a terminated agent")
        cp = h.checkpoints.get(checkpoint_id)
        if cp is None:
            raise MuffinRuntimeError(f"unknown checkpoint {checkpoint_id}")
        h.agent.set_state(copy.deepcopy(cp["agent_state"]))
        removed = self.memory.truncate_after(agent_id, cp["memory_marker"])
        self.safety.restore(agent_id, cp["safety"])
        h.step = cp["step"]
        h.state = State.PAUSED
        # The trace log is never truncated, so rollbacks stay auditable.
        self.trace.record(agent_id, "rollback", checkpoint_id=checkpoint_id, memory_events_removed=removed)

    # ---- the agent loop ---------------------------------------------
    def step(self, agent_id: str, raw_input: Any = None) -> dict[str, Any]:
        h = self._handle(agent_id)
        if h.state != State.RUNNING:
            raise MuffinRuntimeError(f"agent is {h.state.value}, not running")
        killed = self.safety.is_killed(agent_id)
        if killed:
            h.state = State.TERMINATED
            return self.trace.record(agent_id, "killed", reason=killed)

        h.step += 1
        try:
            perception = h.agent.perceive(raw_input)
            h.agent.update_beliefs(perception)
            action = h.agent.decide()
        except Exception as exc:
            return self._fail(agent_id, h, "agent error during perceive/decide", exc)

        why = h.agent.explain()
        if action is None:
            return self.trace.record(agent_id, "no_action", step=h.step, perception=perception, explanation=why)

        verdict = self.safety.check(agent_id, action)
        if not verdict.allowed:
            self.memory.write(agent_id, "blocked", {"action": action.name, "reason": verdict.reason})
            return self.trace.record(agent_id, "blocked", step=h.step, action=action.name,
                                     params=action.params, reason=verdict.reason, explanation=why)
        try:
            outcome = h.agent.act(action)
        except Exception as exc:
            return self._fail(agent_id, h, f"agent error during act({action.name})", exc)

        self.safety.commit(agent_id, action)
        self.memory.write(agent_id, "action", {"action": action.name, "params": action.params, "outcome": outcome})
        return self.trace.record(agent_id, "acted", step=h.step, perception=perception, action=action.name,
                                 params=action.params, verdict=verdict.reason, outcome=outcome, explanation=why)

    def run(self, agent_id: str, inputs: Iterable[Any]) -> list[dict[str, Any]]:
        results = []
        for item in inputs:
            if self.state(agent_id) != State.RUNNING:
                break
            results.append(self.step(agent_id, item))
        return results

    # ---- internals ---------------------------------------------------
    def _handle(self, agent_id: str) -> _Handle:
        try:
            return self._agents[agent_id]
        except KeyError:
            raise MuffinRuntimeError(f"unknown agent {agent_id}") from None

    def _transition(self, agent_id: str, allowed_from: set[State], to: State, event: str) -> None:
        h = self._handle(agent_id)
        if h.state not in allowed_from:
            raise MuffinRuntimeError(f"cannot {event}: agent is {h.state.value}")
        h.state = to
        self.trace.record(agent_id, event, state=to.value)

    def _fail(self, agent_id: str, h: _Handle, msg: str, exc: Exception) -> dict[str, Any]:
        h.state = State.FAILED
        self.memory.write(agent_id, "failure", {"message": msg, "error": repr(exc)})
        return self.trace.record(agent_id, "failed", step=h.step, message=msg, error=repr(exc))
