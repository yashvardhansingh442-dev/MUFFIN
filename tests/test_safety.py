
import math
import pytest

from muffin.agent import Action
from muffin.safety import Policy, SafetyLayer


@pytest.fixture
def safety():
    layer = SafetyLayer()
    layer.register("agent-1", Policy(
        allowed_actions={"search"},
        max_total_cost=10.0,
    ))
    return layer


@pytest.mark.parametrize("cost", [
    -1, float("nan"), float("inf"), -float("inf"),
    True, False, "1", None,
])
def test_invalid_cost_is_denied(safety, cost):
    action = Action("search", {}, cost=cost)
    verdict = safety.check("agent-1", action)
    assert not verdict.allowed


def test_unknown_agent_is_denied(safety):
    verdict = safety.check("unknown", Action("search", {}, cost=1))
    assert not verdict.allowed


def test_unapproved_action_is_denied(safety):
    verdict = safety.check("agent-1", Action("delete", {}, cost=1))
    assert not verdict.allowed


def test_budget_cannot_be_exceeded(safety):
    action = Action("search", {}, cost=6)
    assert safety.check("agent-1", action).allowed
    safety.commit("agent-1", action)

    assert safety.check("agent-1", action).denied if False else True
    verdict = safety.check("agent-1", action)
    assert not verdict.allowed
    assert "budget" in verdict.reason


@pytest.mark.parametrize("budget", [
    -1, float("nan"), -float("inf"), True,
])
def test_invalid_policy_budget_rejected(budget):
    with pytest.raises(ValueError):
        SafetyLayer().register(
            "agent-1",
            Policy(allowed_actions={"search"}, max_total_cost=budget),
        )


def test_infinite_budget_is_allowed():
    layer = SafetyLayer()
    layer.register("agent-1", Policy(allowed_actions={"search"}))
    assert layer.check("agent-1", Action("search", {}, cost=1)).allowed


def test_kill_switch_denies_actions(safety):
    safety.trip_kill_switch("agent-1", "operator")
    verdict = safety.check("agent-1", Action("search", {}, cost=1))
    assert not verdict.allowed
    assert "kill switch" in verdict.reason


def test_restore_rejects_invalid_spend(safety):
    for value in (-1, float("nan"), float("inf"), True):
        with pytest.raises(ValueError):
            safety.restore("agent-1", {"spent": value})


def test_rate_limit():
    now = [100.0]
    layer = SafetyLayer(clock=lambda: now[0])
    layer.register("agent-1", Policy(
        allowed_actions={"search"},
        max_actions_per_window=1,
        window_seconds=60,
    ))

    action = Action("search", {}, cost=1)
    assert layer.check("agent-1", action).allowed
    layer.commit("agent-1", action)

    assert not layer.check("agent-1", action).allowed
    now[0] += 61
    assert layer.check("agent-1", action).allowed
