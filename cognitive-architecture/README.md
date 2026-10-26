# Cognitive architecture

Pillar 4 of the MUFFIN.AI founding document: **Cognitive Architecture**, "how you make systems intelligent, stable, and safe."

**Rule (from the document):** every component you build must map to a specific cognitive function. If you cannot name the cognitive role a component plays, you do not need it yet. Every topic ends in a small, tested program.

This is the pillar closest to the repo: `src/muffin/` is a first slice of topics 2, 21 and 28. It is a learning and build track, so work here stays outside the zero-dependency core until a piece earns its way in through a normal, tested change.

## Do first: where the repo already has a head start

| # | Topic | Deliverable (the document's "Build:") | Where the repo stands | Status |
|---|---|---|---|---|
| 2 | Perception-belief-decision-action loop | The full loop as clean architecture: each stage a separate module with a defined interface, swappable without touching the others, every stage transition logged with timing and content | `Runtime.step` runs perceive, update_beliefs, decide, safety check, act and trace, but the stages are methods on one `Agent` class, not swappable modules, and the trace has no per-stage timing | [ ] partly met |
| 21 | Safety engineering layer | A stack that wraps any agent: hard constraints at the action level, action budgets, a shutdown handler that safely serializes state, a behavior monitor that fires alerts per anomaly type; tested by trying to make the agent violate each constraint | `SafetyLayer` covers constraints, budgets and the kill switch, and the tests try to break them. Missing: a behavior monitor with alerts (README, ASI10) | [ ] partly met |
| 25 | Human-in-the-loop control | The agent runs autonomously but flags low-confidence decisions for human review; the human can approve, modify or reject; every intervention is logged and used to improve the agent | Planned approval gates (README Stage C, ASI09). Nothing built | [ ] |
| 27 | Failure mode taxonomy | A failure-injection framework: for each failure mode a reliable test case, a detection mechanism and a recovery procedure, all run before every deployment | The README's test gaps and limitations L7, L12 and L15 are the starting list | [ ] |

Topic 28 (cognitive runtime as a standalone service that runs any agent built on the SDK) is the document's "core product." v0.1 is an in-process library, so a standalone service is a later step, after Stage B validation.

## The curriculum, in order

Durations are the document's estimates. Topic numbers match the document, which holds the topic lists and full Build for each. Layer 9 is in the document twice, original and expanded, and I used the expanded version's topics.

| Layer | Months | Topics and Build (short form) | Status |
|---|---|---|---|
| 1 Agent theory | 4 | 1 What an agent is: all five agent types on one grid-world task. 2 PDBA loop (above). 3 Architecture patterns: a hybrid deliberative (1 Hz) and reactive (1 kHz) agent where the reactive layer overrides on safety | [ ] |
| 2 Perception and world modeling | 6 | 4 World models: a learned next-state model used for planning. 5 Representation learning: a VAE on the observation space, and whether it helps sample efficiency | [ ] |
| 2.5 Modern ML stack | n/a | A transformer from scratch, from the paper | [ ] |
| 3 Memory systems | 6 | 6 Memory taxonomy: all four memory types as separate subsystems. 7 Episodic: prioritized and hindsight experience replay. 8 Semantic: a knowledge graph that grows as the agent explores. 9 Integration: working to episodic in real time, a nightly consolidation job, fused queries | [ ] |
| 4 Learning and adaptation | 12 | 10 RL foundations: PPO from scratch on a MuJoCo task. 11 Continual learning: EWC and replay against catastrophic forgetting. 12 Meta-learning: MAML on a navigation task family | [ ] |
| 5 Planning | 6 | 13 Classical planning: A* with an admissible heuristic. 14 Hierarchical planning: a manager and worker on a long-horizon task. 15 Decisions under uncertainty: a POMDP agent with Bayes-filter beliefs. 16 MCTS: UCB1 on a small board game, then a learned value network | [ ] |
| 6 Multi-agent | 9 | 17 Fundamentals: 10 cooperating agents with no coordinator, only a message bus. 18 MARL: QMIX vs independent Q-learning. 19 Communication: an uncertainty-sharing protocol, and detecting and isolating a malfunctioning agent | [ ] |
| 7 Safety and alignment | 6 | 20 The alignment problem: reproduce each failure mode in a simple environment, then detect it. 21 Safety layer (above). 22 Interpretability: SHAP explanations per decision with a dashboard. 23 Robustness: an adversary that perturbs observations, adversarial training, and an input sanitizer | [ ] |
| 8 Observability and control | 9 | 24 Cognitive observability: instrument every cognitive function and find one non-obvious pattern in 10,000 steps. 25 Human-in-the-loop (above) | [ ] |
| 9 Human cognition and biology | 12 | 26 Cognitive science foundations: map each cognitive bias to an analogous agent failure and mitigate it; a spiking neural network with leaky integrate-and-fire neurons and STDP. 27 Failure mode taxonomy (above) | [ ] |
| 10 Cognitive infrastructure design | 12 | 28 Cognitive runtime design: the runtime as a standalone service. 29 The infrastructure stack: draw the 11-layer stack and build it bottom-up over years 1 to 3, every layer independently testable | [ ] |

## How this maps to the repo's own architecture

The document's Layer 10 stack is the same 11-layer design as `docs/architecture.md` (L0 physical substrate up to L10 external interface). The mapping in that file's status notes is the current answer to topic 29: L2 runtime, L6 safety and part of L3 and L8 exist; the rest is planned.

## Notes on order

- The document's own flow is: agent theory, perception, memory, learning, planning, multi-agent, safety, observability, human cognition, then infrastructure design. The "do first" items above are the exception because they extend code that already exists.
- Topics 10 to 12 (RL, continual and meta-learning) and 17 to 19 (multi-agent) depend on the math and simulation tracks: see `mathematics/` topics 16 and 17 and `simulation/` topic 33.
- Layer 9's biology material and topic 29 are last. Do not start them early.
