"""MUFFIN.AI: cognitive infrastructure for AI agents.

The agent proposes; the runtime decides. A minimal run::

    from muffin import Action, Agent, Policy, Runtime

    class Greeter(Agent):
        def decide(self):
            return Action("greet", {"name": "Ada"})

        def act(self, action):
            return f"Hello, {action.params['name']}!"

    rt = Runtime()
    aid = rt.spawn(Greeter(), Policy(allowed_actions={"greet"}, max_total_cost=3, costs={"greet": 1}))
    rt.start(aid)
    print(rt.step(aid)["outcome"])      # Hello, Ada!

See the README for the safety model and its known limitations.
"""
from . import rules
from .agent import Action, Agent
from .llm_agent import LLMAgent, Tool
from .memory import EpisodicMemory
from .providers import AnthropicCompleter, Completer
from .runtime import MuffinRuntimeError, Runtime, State
from .safety import Policy, SafetyLayer, Verdict
from .trace import TraceLog

__all__ = [
    "Action",
    "Agent",
    "AnthropicCompleter",
    "Completer",
    "EpisodicMemory",
    "LLMAgent",
    "MuffinRuntimeError",
    "Policy",
    "Runtime",
    "SafetyLayer",
    "State",
    "Tool",
    "TraceLog",
    "Verdict",
    "rules",
]

# Keep in sync with `version` in pyproject.toml.
__version__ = "0.1.0"
