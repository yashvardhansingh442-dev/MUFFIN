import math
import pytest

from muffin.agent import Action
from muffin.safety import Policy, SafetyLayer


@pytest.fixture
def safety():
    layer = SafetyLayer()
    layer.register("agent-1", Policy(
        allowed_actions={"search"},
        max_total_cost=10.0, strict_costs=False))
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
            Policy(allowed_actions={"search"}, max_total_cost=budget, strict_costs=False),
        )


def test_infinite_budget_is_allowed():
    layer = SafetyLayer()
    layer.register("agent-1", Policy(allowed_actions={"search"}, strict_costs=False))
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
        window_seconds=60, strict_costs=False))

    action = Action("search", {}, cost=1)
    assert layer.check("agent-1", action).allowed
    layer.commit("agent-1", action)

    assert not layer.check("agent-1", action).allowed
    now[0] += 61
    assert layer.check("agent-1", action).allowed


def test_policy_cost_overrides_a_zero_declared_cost():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x"}, max_total_cost=2, costs={"x": 1}, strict_costs=False))
    cheat = Action("x", {}, cost=0)
    for _ in range(2):
        assert layer.check("a", cheat).allowed
        layer.commit("a", cheat)
    assert not layer.check("a", cheat).allowed


@pytest.mark.parametrize("costs", [{"x": -1}, {"x": float("nan")}, {"x": True}, {"": 1}, [("x", 1)]])
def test_invalid_policy_costs_rejected(costs):
    with pytest.raises((ValueError, TypeError)):
        SafetyLayer().register("a", Policy(allowed_actions={"x"}, costs=costs, strict_costs=False))


def test_unregister_removes_agent():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x"}, strict_costs=False))
    layer.unregister("a")
    layer.unregister("a")  # idempotent
    assert not layer.check("a", Action("x", {})).allowed


def test_strict_costs_requires_a_cost_for_every_allowed_action():
    with pytest.raises(ValueError):
        SafetyLayer().register("a", Policy(allowed_actions={"x", "y"}, costs={"x": 1}, strict_costs=True))


def test_strict_costs_must_be_a_bool():
    with pytest.raises(TypeError):
        SafetyLayer().register("a", Policy(allowed_actions={"x"}, costs={"x": 1}, strict_costs="yes"))


def test_strict_costs_ignores_agent_declared_cost():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x"}, max_total_cost=2, costs={"x": 1}, strict_costs=True))
    cheat = Action("x", {}, cost=0)
    for _ in range(2):
        assert layer.check("a", cheat).allowed
        layer.commit("a", cheat)
    assert not layer.check("a", cheat).allowed


def test_policy_changes_after_register_do_not_change_what_is_enforced():
    layer = SafetyLayer()
    policy = Policy(allowed_actions={"x"}, max_total_cost=1, costs={"x": 1}, strict_costs=True)
    layer.register("a", policy)
    policy.allowed_actions.add("y")
    policy.max_total_cost = 10**9
    policy.costs["x"] = 0
    policy.constraints.append(lambda action: None)
    assert not layer.check("a", Action("y", {}, cost=0)).allowed
    spend = Action("x", {}, cost=0)
    assert layer.check("a", spend).allowed
    layer.commit("a", spend)
    assert not layer.check("a", spend).allowed  # still charged 1 of a budget of 1


def test_policy_param_rules_are_copied_on_register():
    layer = SafetyLayer()
    rule_list = [lambda params: None]
    policy = Policy(allowed_actions={"x"}, param_rules={"x": rule_list}, strict_costs=False)
    layer.register("a", policy)
    rule_list.append(lambda params: "blocked by later rule")
    assert layer.check("a", Action("x", {})).allowed


def test_non_strict_policy_still_falls_back_to_declared_cost():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x", "y"}, max_total_cost=1, costs={"x": 1}, strict_costs=False))
    big = Action("y", {}, cost=5)
    assert not layer.check("a", big).allowed


def test_update_policy_keeps_spend_and_applies_new_limits():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x"}, max_total_cost=5, costs={"x": 1}, strict_costs=False))
    spend = Action("x", {}, cost=1)
    for _ in range(3):
        layer.commit("a", spend)
    layer.update_policy("a", Policy(allowed_actions={"x"}, max_total_cost=3, costs={"x": 1}, strict_costs=False))
    assert not layer.check("a", spend).allowed  # 3 already spent, new budget is 3
    layer.update_policy("a", Policy(allowed_actions={"x"}, max_total_cost=4, costs={"x": 1}, strict_costs=False))
    assert layer.check("a", spend).allowed


def test_update_policy_rejects_invalid_policy_and_keeps_the_old_one():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x"}, strict_costs=False))
    with pytest.raises((ValueError, TypeError)):
        layer.update_policy("a", Policy(allowed_actions={"x"}, costs={"x": -1}, strict_costs=False))
    assert layer.check("a", Action("x", {})).allowed


def test_update_policy_unknown_agent_and_copy_semantics():
    layer = SafetyLayer()
    with pytest.raises(ValueError):
        layer.update_policy("nobody", Policy(allowed_actions={"x"}, strict_costs=False))
    policy = Policy(allowed_actions={"x"}, strict_costs=False)
    layer.register("a", Policy(allowed_actions={"x"}, strict_costs=False))
    layer.update_policy("a", policy)
    policy.allowed_actions.add("y")
    assert not layer.check("a", Action("y", {})).allowed


def test_update_policy_keeps_the_kill_switch():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x"}, strict_costs=False))
    layer.trip_kill_switch("a", "test")
    layer.update_policy("a", Policy(allowed_actions={"x"}, strict_costs=False))
    assert not layer.check("a", Action("x", {})).allowed


def test_policy_costs_are_strict_by_default():
    assert Policy(allowed_actions=set()).strict_costs is True
    with pytest.raises(ValueError, match="strict_costs=False"):
        SafetyLayer().register("a", Policy(allowed_actions={"x"}))


def test_default_policy_ignores_an_under_reported_cost():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x"}, max_total_cost=2, costs={"x": 1}))
    cheat = Action("x", {}, cost=0)
    for _ in range(2):
        assert layer.check("a", cheat).allowed
        layer.commit("a", cheat)
    assert not layer.check("a", cheat).allowed


def test_opting_out_of_strict_costs_trusts_the_declared_cost():
    layer = SafetyLayer()
    layer.register("a", Policy(allowed_actions={"x"}, max_total_cost=2, strict_costs=False))
    assert layer.check("a", Action("x", {}, cost=2)).allowed
