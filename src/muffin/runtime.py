
"""Cognitive runtime: lifecycle, safety, memory, and decision tracing."""
from __future__ import annotations

import copy
import threading
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
    """An invalid runtime operation or runtime-level failure."""


@dataclass
class _Handle:
    agent: Agent
    state: State
    step: int = 0
    checkpoints: dict[str, dict[str, Any]] = field(default_factory=dict)
    lock: threading.RLock = field(default_factory=threading.RLock)


class Runtime:
    def __init__(
        self,
        db_path: str = ":memory:",
        trace_path: str | None = None,
        safety: SafetyLayer | None = None,
    ) -> None:
        self.memory = EpisodicMemory(db_path)
        self.safety = safety or SafetyLayer()
        self.trace = TraceLog(trace_path)
        self._agents: dict[str, _Handle] = {}
        self._lock = threading.RLock()
        self._closed = False

    # ---- lifecycle ---------------------------------------------------

    def spawn(self, agent: Agent, policy: Policy) -> str:
        with self._lock:
            self._ensure_open()
            # Avoid unnecessarily short IDs.
            agent_id = uuid.uuid4().hex

            self.safety.register(agent_id, policy)
            handle = _Handle(agent=agent, state=State.CONFIGURED)

            try:
                self.trace.record(
                    agent_id,
                    "spawned",
                    state=State.CONFIGURED.value,
                )
            except Exception:
                # Do not leave a registered agent if initialization fails.
                self._agents.pop(agent_id, None)
                raise

            self._agents[agent_id] = handle
            return agent_id

    def start(self, agent_id: str) -> None:
        self._transition(
            agent_id, {State.CONFIGURED}, State.RUNNING, "started"
        )

    def pause(self, agent_id: str) -> None:
        self._transition(
            agent_id, {State.RUNNING}, State.PAUSED, "paused"
        )

    def resume(self, agent_id: str) -> None:
        self._transition(
            agent_id, {State.PAUSED}, State.RUNNING, "resumed"
        )

    def kill(self, agent_id: str, reason: str = "operator") -> None:
        """Terminate an agent and preserve its memory for post-mortem review."""
        handle = self._handle(agent_id)

        with handle.lock:
            if handle.state == State.TERMINATED:
                return

            # Engage the safety mechanism before changing visible state.
            self.safety.trip_kill_switch(agent_id, reason)
            handle.state = State.TERMINATED

            self.trace.record(
                agent_id,
                "killed",
                reason=reason,
                step=handle.step,
            )

    def state(self, agent_id: str) -> State:
        handle = self._handle(agent_id)
        with handle.lock:
            return handle.state

    # ---- checkpoint / rollback --------------------------------------

    def checkpoint(self, agent_id: str) -> str:
        handle = self._handle(agent_id)

        with handle.lock:
            if handle.state in {State.TERMINATED, State.FAILED}:
                raise MuffinRuntimeError(
                    f"cannot checkpoint an agent in {handle.state.value} state"
                )

            checkpoint_id = uuid.uuid4().hex
            snapshot = {
                "agent_state": copy.deepcopy(handle.agent.get_state()),
                "memory_marker": self.memory.last_id(agent_id),
                "safety": copy.deepcopy(self.safety.snapshot(agent_id)),
                "step": handle.step,
                "state": handle.state,
            }

            # Save the checkpoint only after its trace entry is persisted.
            self.trace.record(
                agent_id,
                "checkpoint",
                checkpoint_id=checkpoint_id,
                step=handle.step,
            )
            handle.checkpoints[checkpoint_id] = snapshot

            return checkpoint_id

    def rollback(self, agent_id: str, checkpoint_id: str) -> None:
        """Restore a checkpoint and leave the agent paused.

        External side effects cannot generally be undone. Memory truncation
        is destructive; the trace log is intentionally not truncated.
        """
        handle = self._handle(agent_id)

        with handle.lock:
            if handle.state in {State.TERMINATED, State.FAILED}:
                raise MuffinRuntimeError(
                    f"cannot roll back an agent in {handle.state.value} state"
                )

            checkpoint = handle.checkpoints.get(checkpoint_id)
            if checkpoint is None:
                raise MuffinRuntimeError(
                    f"unknown checkpoint {checkpoint_id}"
                )

            # Capture a recovery snapshot before mutating any component.
            try:
                old_agent_state = copy.deepcopy(handle.agent.get_state())
                old_safety_state = copy.deepcopy(
                    self.safety.snapshot(agent_id)
                )
                old_step = handle.step
                old_state = handle.state

                target_agent_state = copy.deepcopy(
                    checkpoint["agent_state"]
                )
                target_safety_state = copy.deepcopy(checkpoint["safety"])
                target_step = checkpoint["step"]
                target_memory_marker = checkpoint["memory_marker"]

                # Validate the checkpoint against the agent's state contract.
                handle.agent.set_state(copy.deepcopy(target_agent_state))
                self.safety.restore(agent_id, target_safety_state)

            except Exception as exc:
                # Best-effort recovery if restoring the checkpoint fails.
                try:
                    handle.agent.set_state(old_agent_state)
                    self.safety.restore(agent_id, old_safety_state)
                    handle.step = old_step
                    handle.state = old_state
                except Exception:
                    handle.state = State.FAILED

                raise MuffinRuntimeError(
                    "checkpoint restoration failed"
                ) from None

            try:
                removed = self.memory.truncate_after(
                    agent_id, target_memory_marker
                )
            except Exception:
                # Restore component state if memory rollback could not run.
                try:
                    handle.agent.set_state(old_agent_state)
                    self.safety.restore(agent_id, old_safety_state)
                    handle.step = old_step
                    handle.state = old_state
                except Exception:
                    handle.state = State.FAILED

                raise MuffinRuntimeError(
                    "memory rollback failed; runtime recovery was attempted"
                ) from None

            handle.step = target_step
            handle.state = State.PAUSED

            # This record describes rollback; it is not part of rolled-back
            # episodic memory and must remain in the trace history.
            self.trace.record(
                agent_id,
                "rollback",
                checkpoint_id=checkpoint_id,
                memory_events_removed=removed,
                step=handle.step,
                state=handle.state.value,
            )

    # ---- the agent loop ---------------------------------------------

    def step(
        self,
        agent_id: str,
        raw_input: Any = None,
    ) -> dict[str, Any]:
        handle = self._handle(agent_id)

        # Serialize steps and lifecycle changes for this agent.
        with handle.lock:
            if handle.state != State.RUNNING:
                raise MuffinRuntimeError(
                    f"agent is {handle.state.value}, not running"
                )

            killed = self.safety.is_killed(agent_id)
            if killed:
                handle.state = State.TERMINATED
                return self.trace.record(
                    agent_id,
                    "killed",
                    reason="kill switch active",
                    step=handle.step,
                )

            handle.step += 1

            try:
                perception = handle.agent.perceive(raw_input)
                handle.agent.update_beliefs(perception)
                action = handle.agent.decide()
                explanation = handle.agent.explain()
            except Exception:
                return self._fail(
                    agent_id, handle, "agent error during perceive/decide"
                )

            if action is None:
                return self.trace.record(
                    agent_id,
                    "no_action",
                    step=handle.step,
                    perception=perception,
                    explanation=explanation,
                )

            try:
                verdict = self.safety.check(agent_id, action)
            except Exception:
                return self._fail(
                    agent_id, handle, "safety check failed"
                )

            if not verdict.allowed:
                try:
                    self.memory.write(
                        agent_id,
                        "blocked",
                        {
                            "action": action.name,
                            "reason": verdict.reason,
                        },
                    )
                    return self.trace.record(
                        agent_id,
                        "blocked",
                        step=handle.step,
                        action=action.name,
                        params=action.params,
                        reason=verdict.reason,
                        explanation=explanation,
                    )
                except Exception:
                    return self._fail(
                        agent_id, handle, "failed to record blocked action"
                    )

            # Persist the intent before attempting the external operation.
            # If this fails, the action must not execute.
            try:
                self.trace.record(
                    agent_id,
                    "action_started",
                    step=handle.step,
                    action=action.name,
                    params=action.params,
                    explanation=explanation,
                )
            except Exception:
                return self._fail(
                    agent_id, handle, "failed to record action intent"
                )

            try:
                outcome = handle.agent.act(action)
            except Exception:
                # The tool may have performed an external side effect before
                # raising, so do not claim the action definitely failed.
                try:
                    self.trace.record(
                        agent_id,
                        "outcome_unknown",
                        step=handle.step,
                        action=action.name,
                    )
                except Exception:
                    pass

                return self._fail(
                    agent_id, handle, "action execution raised an exception"
                )

            try:
                self.safety.commit(agent_id, action)

                self.memory.write(
                    agent_id,
                    "action",
                    {
                        "action": action.name,
                        "params": action.params,
                        "outcome": outcome,
                    },
                )

                return self.trace.record(
                    agent_id,
                    "acted",
                    step=handle.step,
                    action=action.name,
                    params=action.params,
                    verdict=verdict.reason,
                    outcome=outcome,
                    explanation=explanation,
                )
            except Exception:
                # The external action has returned, but accounting or
                # persistence may have failed. Its outcome is not undone.
                try:
                    self.trace.record(
                        agent_id,
                        "outcome_recording_failed",
                        step=handle.step,
                        action=action.name,
                    )
                except Exception:
                    pass

                return self._fail(
                    agent_id,
                    handle,
                    "failed to commit or record action outcome",
                )

    def run(
        self,
        agent_id: str,
        inputs: Iterable[Any],
    ) -> list[dict[str, Any]]:
        results = []

        for item in inputs:
            if self.state(agent_id) != State.RUNNING:
                break
            results.append(self.step(agent_id, item))

        return results

    # ---- internals ---------------------------------------------------

    def _handle(self, agent_id: str) -> _Handle:
        with self._lock:
            self._ensure_open()
            try:
                return self._agents[agent_id]
            except KeyError:
                raise MuffinRuntimeError(
                    f"unknown agent {agent_id}"
                ) from None

    def _transition(
        self,
        agent_id: str,
        allowed_from: set[State],
        to: State,
        event: str,
    ) -> None:
        handle = self._handle(agent_id)

        with handle.lock:
            if handle.state not in allowed_from:
                raise MuffinRuntimeError(
                    f"cannot {event}: agent is {handle.state.value}"
                )

            # Persist the event before publishing the new state.
            self.trace.record(agent_id, event, state=to.value)
            handle.state = to

    def _fail(
        self,
        agent_id: str,
        handle: _Handle,
        message: str,
    ) -> dict[str, Any]:
        handle.state = State.FAILED

        # Do not persist raw exception details; they may contain secrets.
        try:
            self.memory.write(
                agent_id,
                "failure",
                {"message": message},
            )
        except Exception:
            pass

        try:
            return self.trace.record(
                agent_id,
                "failed",
                step=handle.step,
                message=message,
            )
        except Exception:
            # Preserve a useful result if the trace backend is unavailable.
            return {
                "event": "failed",
                "agent_id": agent_id,
                "step": handle.step,
                "message": message,
                "trace_persisted": False,
            }

    def _ensure_open(self) -> None:
        if self._closed:
            raise MuffinRuntimeError("runtime is closed")

    def close(self) -> None:
        """Release owned resources. The runtime cannot be reused afterward."""
        with self._lock:
            if self._closed:
                return

            for handle in self._agents.values():
                with handle.lock:
                    if handle.state == State.RUNNING:
                        handle.state = State.PAUSED

            self.memory.close()
            self._closed = True

    def __enter__(self) -> Runtime:
        with self._lock:
            self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
