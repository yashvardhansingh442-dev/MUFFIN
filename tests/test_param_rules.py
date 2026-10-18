import pytest

from muffin import Action, Agent, Policy, Runtime, rules
from muffin.safety import SafetyLayer


class Proposer(Agent):
    """Proposes whatever action it is handed."""

    def __init__(self):
        self.next = None
        self.ran = []

    def update_beliefs(self, perception):
        self.next = perception

    def decide(self):
        return self.next

    def act(self, action):
        self.ran.append(action)
        return "ok"


def run_one(policy, action):
    rt = Runtime()
    agent = Proposer()
    aid = rt.spawn(agent, policy)
    rt.start(aid)
    return rt.step(aid, action), agent


EMAIL_POLICY = Policy(
    allowed_actions={"send_email"},
    param_rules={"send_email": [rules.only_keys("to", "body"), rules.email_domain("to", "example.com"),
                                rules.max_len("body", 200)]},
)


def test_allowed_tool_with_good_params_runs():
    r, agent = run_one(EMAIL_POLICY, Action("send_email", {"to": "ops@example.com", "body": "hi"}))
    assert r["event"] == "acted" and len(agent.ran) == 1


def test_allowed_tool_with_bad_params_is_blocked():
    r, agent = run_one(EMAIL_POLICY, Action("send_email", {"to": "attacker@evil.test", "body": "hi"}))
    assert r["event"] == "blocked" and "parameter rule violated" in r["reason"]
    assert agent.ran == []


@pytest.mark.parametrize("address", [
    "a@evil.test@example.com",          # smuggled second @
    "ops@example.com.evil.test",        # suffix trick
    "ops@sub.example.com",              # subdomain not allowed
    "ops@example.com, spy@evil.test",   # multiple recipients
    "ops@example.com\nbcc: spy@evil.test",
    "",
    None,
    123,
])
def test_email_domain_rejects_tricks(address):
    assert rules.email_domain("to", "example.com")({"to": address}) is not None


def test_email_domain_is_case_insensitive_for_the_allowed_domain():
    assert rules.email_domain("to", "Example.COM")({"to": "ops@EXAMPLE.com"}) is None


def test_unexpected_params_rejected():
    r, _ = run_one(EMAIL_POLICY, Action("send_email", {"to": "ops@example.com", "body": "hi", "bcc": "x@evil.test"}))
    assert r["event"] == "blocked" and "unexpected params" in r["reason"]


def test_missing_params_fail_closed():
    r, _ = run_one(EMAIL_POLICY, Action("send_email", {"body": "hi"}))
    assert r["event"] == "blocked"


def test_rules_apply_only_to_their_own_action():
    policy = Policy({"send_email", "ping"}, param_rules={"send_email": [rules.required("to")]})
    r, _ = run_one(policy, Action("ping", {}))
    assert r["event"] == "acted"


def test_rule_that_crashes_fails_closed():
    def broken(_params):
        raise RuntimeError("rule bug")

    r, agent = run_one(Policy({"x"}, param_rules={"x": [broken]}), Action("x", {}))
    assert r["event"] == "blocked" and "failing closed" in r["reason"]
    assert agent.ran == []


def test_number_between():
    rule = rules.number_between("amount", 0, 100)
    assert rule({"amount": 50}) is None
    assert rule({"amount": 0}) is None
    assert rule({"amount": -1}) is not None
    assert rule({"amount": 101}) is not None
    assert rule({"amount": "50"}) is not None        # strings are not numbers
    assert rule({"amount": True}) is not None        # bool is not a number here
    assert rule({"amount": float("nan")}) is not None
    assert rule({}) is not None


def test_matches_uses_fullmatch():
    rule = rules.matches("path", r"/workspace/[a-z0-9_]+\.txt")
    assert rule({"path": "/workspace/notes.txt"}) is None
    assert rule({"path": "/workspace/notes.txt/../../etc/passwd"}) is not None
    assert rule({"path": "x/workspace/notes.txt"}) is not None


def test_one_of():
    rule = rules.one_of("mode", ["read", "list"])
    assert rule({"mode": "read"}) is None
    assert rule({"mode": "write"}) is not None
    assert rule({}) is not None
