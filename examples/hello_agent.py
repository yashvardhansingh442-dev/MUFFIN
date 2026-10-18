"""A tiny agent running inside the MUFFIN runtime.

Shows: allowed vs blocked actions, an action budget, checkpoint/rollback,
the kill switch, and the decision trace.
Run:  python examples/hello_agent.py
"""
from muffin import Action, Agent, Policy, Runtime


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


def main() -> None:
    rt = Runtime(trace_path="traces/hello.jsonl")
    policy = Policy(allowed_actions={"greet"}, max_total_cost=3)
    agent = Greeter()
    aid = rt.spawn(agent, policy)
    rt.start(aid)

    cp = rt.checkpoint(aid)
    rt.step(aid, "Ada")
    rt.step(aid, "delete_everything")      # blocked: default deny
    rt.step(aid, "Grace")
    print("greeted:", agent.greeted)

    rt.pause(aid)
    rt.rollback(aid, cp)                   # back to before Ada
    print("after rollback:", agent.greeted, "| memory events:", rt.memory.count(aid))

    rt.resume(aid)
    for name in ["Linus", "Margaret", "Alan", "Hedy"]:
        r = rt.step(aid, name)
        print(f"{name:9s} -> {r['event']}", r.get("reason", ""))

    rt.kill(aid, "demo over")
    print("final state:", rt.state(aid).value)
    print("\nlast memory events:")
    for e in rt.memory.recent(aid, 5):
        print(" ", e["kind"], e["data"])


if __name__ == "__main__":
    main()
