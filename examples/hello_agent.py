"""A tiny agent running inside the MUFFIN runtime.

Shows: allowed vs blocked actions, an action budget, checkpoint/rollback,
the kill switch, and the decision trace.
Run:  python examples/hello_agent.py
"""
from pathlib import Path

from muffin import Action, Agent, Policy, Runtime

TRACE_PATH = Path("traces/hello.jsonl")


class Greeter(Agent):
    def __init__(self) -> None:
        self.greeted: list[str] = []
        self._pending: str | None = None

    def perceive(self, raw_input):
        return raw_input

    def update_beliefs(self, perception) -> None:
        self._pending = perception

    def decide(self):
        if self._pending is None:
            return None
        if self._pending == "delete_everything":
            return Action("delete_files", {"path": "/"}, cost=5)   # not in the allowed set
        return Action("greet", {"name": self._pending})

    def act(self, action):
        self.greeted.append(action.params["name"])
        return f"Hello, {action.params['name']}!"

    def get_state(self):
        return {"greeted": list(self.greeted)}

    def set_state(self, state) -> None:
        self.greeted = list(state["greeted"])


def show(label: str, result: dict) -> None:
    """Print one step: what happened, and the outcome or the reason it was blocked."""
    detail = result.get("outcome") or result.get("reason") or ""
    print(f"{label:18s} -> {result['event']:8s} {detail}")


def main() -> None:
    TRACE_PATH.unlink(missing_ok=True)     # start every run with a fresh trace file
    rt = Runtime(trace_path=str(TRACE_PATH))
    policy = Policy(allowed_actions={"greet"}, max_total_cost=3)
    agent = Greeter()
    aid = rt.spawn(agent, policy)
    rt.start(aid)

    cp = rt.checkpoint(aid)
    print("== allowed and blocked actions ==")
    for name in ["Ada", "delete_everything", "Grace"]:   # the middle one is blocked: default deny
        show(name, rt.step(aid, name))
    print("greeted:", agent.greeted)

    print("\n== rollback ==")
    rt.pause(aid)
    rt.rollback(aid, cp)                   # back to before Ada
    print("after rollback:", agent.greeted, "| memory events:", rt.memory.count(aid))

    print("\n== budget (max_total_cost=3) ==")
    rt.resume(aid)
    for name in ["Linus", "Margaret", "Alan", "Hedy"]:
        show(name, rt.step(aid, name))

    rt.kill(aid, "demo over")
    print("\nfinal state:", rt.state(aid).value)

    print("\nlast memory events:")
    for e in rt.memory.recent(aid, 5):
        print(" ", e["kind"], e["data"])

    print("\ndecision trace:", ", ".join(e["event"] for e in rt.trace.for_agent(aid)))


if __name__ == "__main__":
    main()
