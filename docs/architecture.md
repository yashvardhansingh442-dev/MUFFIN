# MUFFIN.AI: Architecture

This document describes the layered architecture of MUFFIN.AI: what each layer is responsible for, how the layers connect, and the rules that keep the whole system testable and safe.

> **Implemented in v0.1 (see `src/muffin/`):** agent lifecycle (spawn, start, pause, resume, checkpoint, rollback, kill), episodic memory, a default-deny safety layer (allowed actions, budgets, rate limits, constraints, parameter rules, kill switch), decision traces, and an LLM-driven agent. **Not yet built:** semantic and procedural memory, the learning engine, planning services, multi-agent coordination, metrics/dashboards, and the control panel.
>
> **Status:** design-stage. The layer structure and responsibilities come from the MUFFIN roadmap. Concrete interfaces, schemas, and tooling choices in this document are **proposed designs** and will change as prototypes teach us what works.
>
> **Known gaps in v0.1:** see the README's [known limitations](../README.md#15-known-limitations-v01) and the README's [threat model](../README.md#72-threat-model). Where this document states a design goal that v0.1 does not yet meet, a note says so.

---

## Table of Contents

1. [Architectural Principles](#1-architectural-principles)
2. [System Overview](#2-system-overview)
3. [Layer-by-Layer Specification](#3-layer-by-layer-specification)
4. [The Agent Loop](#4-the-agent-loop)
5. [Agent Lifecycle State Machine](#5-agent-lifecycle-state-machine)
6. [Memory Architecture](#6-memory-architecture)
7. [Safety Architecture](#7-safety-architecture)
8. [Observability Architecture](#8-observability-architecture)
9. [Interfaces and APIs](#9-interfaces-and-apis)
10. [Failure Handling](#10-failure-handling)
11. [Data Flow Examples](#11-data-flow-examples)
12. [Technology Mapping](#12-technology-mapping)
13. [Build Order](#13-build-order)
14. [Testing Strategy](#14-testing-strategy)
15. [Open Design Questions](#15-open-design-questions)

---

## 1. Architectural Principles

| # | Principle | What it means in practice |
|---|---|---|
| 1 | **Layered, bottom-up** | Each layer is built and tested before the one above it |
| 2 | **Adjacent-only knowledge** | A layer talks only to the layer directly above and below; no layer knows implementation details of non-adjacent layers |
| 3 | **Independently testable** | Every layer can be tested alone with mocks of its neighbors |
| 4 | **Defined interfaces** | Every boundary has an explicit contract (API, schema, or protocol) |
| 5 | **Every component maps to a cognitive function** | If we cannot name the cognitive role a component plays, we do not build it yet |
| 6 | **Explainability over performance** | If we cannot trace what an agent did and why it was allowed, the work is unfinished. An agent's own explanation is evidence, not proof |
| 7 | **Failure-first design** | Failure modes are designed for before happy paths |
| 8 | **Model-agnostic** | MUFFIN manages cognition; it does not depend on any one model |
| 9 | **Observable by default** | Every layer emits structured events, metrics, and traces |
| 10 | **Stoppable by default** | Any agent can be paused, rolled back, or killed at any time |

---

## 2. System Overview

```
┌──────────────────────────────────────────────────────────────┐
│  L10  EXTERNAL INTERFACE      Public API · SDK · Docs        │
├──────────────────────────────────────────────────────────────┤
│  L9   HUMAN INTERFACE         Control panel · Overrides      │
│                               HITL feedback · Audit trail    │
├──────────────────────────────────────────────────────────────┤
│  L8   OBSERVABILITY           Metrics · Logs · Traces        │
│                               Dashboards · Alerting          │
├──────────────────────────────────────────────────────────────┤
│  L7   MULTI-AGENT COORD.      Population mgmt · Protocols    │
│                               Emergent behavior detection    │
├──────────────────────────────────────────────────────────────┤
│  L6   SAFETY                  Constraints · Action budgets   │
│                               Kill switches · Alignment      │
├──────────────────────────────────────────────────────────────┤
│  L5   PLANNING SERVICES       World model · Planners         │
│                               Goals · Subgoal decomposition  │
├──────────────────────────────────────────────────────────────┤
│  L4   LEARNING ENGINE         Training loops · Experiments   │
│                               Model versioning · Continual   │
├──────────────────────────────────────────────────────────────┤
│  L3   MEMORY SERVICES         Working · Episodic             │
│                               Semantic · Procedural          │
├──────────────────────────────────────────────────────────────┤
│  L2   COGNITIVE RUNTIME       Lifecycle · Resources          │
│                               Service provision · Recovery   │
├──────────────────────────────────────────────────────────────┤
│  L1   OPERATING ENVIRONMENT   Linux · Containers · Network   │
├──────────────────────────────────────────────────────────────┤
│  L0   PHYSICAL SUBSTRATE      Hardware · Sensors · Actuators │
└──────────────────────────────────────────────────────────────┘
```

**Reading the diagram:** lower layers provide capabilities; upper layers govern, observe, and expose them. Safety (L6) and Observability (L8) deliberately sit high in the stack so they can see and constrain everything beneath them, but they are *implemented* as cross-cutting concerns (see sections 7 and 8).

---

## 3. Layer-by-Layer Specification

### L0: Physical Substrate
**Cognitive role:** connection to physical reality.
- Hardware, compute (CPU/GPU), sensors, actuators
- For robotics: motors, embedded controllers, sensor interfaces
- **Interface up:** raw sensor streams, actuator command channels
- **Note:** for pure-software agents this layer is just compute

### L1: Operating Environment
**Cognitive role:** the host organism.
- Linux, containerization, networking
- Process isolation, resource limits (cgroups), network policy
- **Interface up:** isolated, resource-limited execution contexts

### L2: Cognitive Runtime
**Cognitive role:** the operating system for intelligence. *The core product.*
- Agent lifecycle management (spawn, run, pause, resume, checkpoint, rollback, kill)
- Resource management (memory allocation, compute scheduling, storage, bandwidth)
- Service provision to agents (memory, world model, messaging, logging, monitoring)
- Failure handling (crash recovery, corruption detection, graceful degradation)
- **Interface up:** Agent SDK, Admin API

### L3: Memory Services
**Cognitive role:** experience and knowledge.
- Four memory types (see [section 6](#6-memory-architecture))
- **Interface up:** uniform memory API (create, read, update, delete, search, consolidate)

### L4: Learning Engine
**Cognitive role:** improving behavior over time, *safely*.
- Training loop management and experiment tracking
- Model versioning and registry
- Continual learning services with drift detection
- **Interface up:** learning jobs, model versions, evaluation reports

### L5: Planning Services
**Cognitive role:** deciding what to do.
- World model service (query and update)
- Planning algorithm library
- Goal management and subgoal decomposition
- **Interface up:** plan generation and evaluation APIs

### L6: Safety Layer
**Cognitive role:** keeping behavior within bounds.
- Constraint enforcement, action budgets, kill switches
- Behavior monitoring, alignment verification
- **Interface up:** Safety API (policy definition, verdicts, overrides)

### L7: Multi-Agent Coordination
**Cognitive role:** many minds working together.
- Agent population management
- Communication protocols and coordination mechanisms
- Emergent behavior detection
- **Interface up:** agent registry, messaging, group-level controls

### L8: Observability Layer
**Cognitive role:** self-awareness for the whole system.
- Metrics, structured logging, distributed tracing, dashboards, alerting
- **Interface up:** Monitoring API

### L9: Human Interface
**Cognitive role:** keeping humans in command.
- Control panel, override mechanisms
- Human-in-the-loop feedback collection
- Audit trail
- **Interface up:** operator UI, approval workflows

### L10: External Interface
**Cognitive role:** how the world integrates with MUFFIN.
- Public API, SDK distribution, documentation, developer tools

---

## 4. The Agent Loop

The runtime hosts a standard cognitive loop. **The agent developer implements only the four creative steps; the runtime owns everything around them.**

```
        ┌────────────────────────────────────────────┐
        │                                            │
        ▼                                            │
   ┌─────────┐    ┌────────────┐    ┌──────────┐    │
   │ PERCEIVE│ ─▶ │BELIEF UPDATE│ ─▶ │  DECIDE  │    │
   └─────────┘    └────────────┘    └────┬─────┘    │
        ▲                                │          │
        │                                ▼          │
        │                       ┌────────────────┐  │
        │                       │ SAFETY CHECK   │  │  (runtime-owned)
        │                       │ budget · policy│  │
        │                       └───────┬────────┘  │
        │                               │ allowed   │
        │                               ▼           │
   ┌─────────┐                    ┌──────────┐      │
   │ OBSERVE │ ◀───────────────── │   ACT    │      │
   │ OUTCOME │                    └──────────┘      │
   └────┬────┘                                      │
        │                                           │
        └──▶ LOG · MEMORY WRITE · LEARNING SIGNAL ──┘
```

| Step | Owner | Runtime support |
|---|---|---|
| Perceive | Agent developer | Sensor/input adapters, world-model queries |
| Belief update | Agent developer | Memory reads, uncertainty utilities |
| Decide | Agent developer | Planning library, goal manager |
| **Safety check** | **Runtime (L6)** | Constraints, budgets, policy verdicts |
| Act | Agent developer | Tool/actuator adapters, rate limits |
| Observe and record | **Runtime** | Logging, memory writes, metrics, learning signals |

**Key rule:** an agent must not be able to bypass the safety check. Actions are submitted *to* the runtime and executed only if approved.

> **v0.1 enforces this only for actions routed through the runtime.** `act()` is the agent's own code, so it can still perform side effects directly, and there is no process isolation yet (README limitation L5). Moving tool execution into the runtime is the planned fix.

---

## 5. Agent Lifecycle State Machine

```
              ┌───────────┐
   spawn ───▶ │ CREATED   │
              └─────┬─────┘
                    │ configure
                    ▼
              ┌───────────┐
              │CONFIGURED │
              └─────┬─────┘
                    │ run
                    ▼
   ┌─────────▶ ┌───────────┐ ──pause──▶ ┌──────────┐
   │ resume    │ RUNNING   │            │ PAUSED   │
   └────────── └──┬──┬──┬──┘ ◀─resume── └──────────┘
                  │  │  │
        checkpoint│  │  │crash / violation
                  ▼  │  ▼
        ┌──────────┐ │ ┌───────────┐  recover   ┌───────────┐
        │CHECKPOINT│ │ │ FAILED    │ ─────────▶ │ ROLLED    │
        │ SAVED    │ │ └─────┬─────┘            │ BACK      │
        └──────────┘ │       │                  └─────┬─────┘
                     │       │ kill                   │
                     │ kill  ▼                        ▼
                     └─▶ ┌───────────┐          (back to RUNNING
                         │ TERMINATED│           or TERMINATED)
                         └───────────┘
                         (state preserved)
```

| Operation | Guarantee |
|---|---|
| **Spawn** | Creates an isolated agent instance with a unique ID |
| **Configure** | Sets goals, constraints, parameters; validated by L6 before run |
| **Run** | Executes the agent loop under resource and safety limits |
| **Pause** | Suspends without losing state |
| **Resume** | Continues from the exact suspension point |
| **Checkpoint** | Persists full recoverable state (beliefs, memory pointers, goals, loop position) |
| **Rollback** | Restores a previous checkpoint |
| **Kill** | Terminates with state preserved for post-mortem. Trips the kill switch at once (no further action is approved); an action already running finishes and is recorded (README L15) |

> **v0.1 differs from this design.** The implemented states are `configured`, `running`, `paused`, `failed` and `terminated`. `spawn` already configures the agent (there is no separate `CREATED` state), the operation is `start`, and checkpoint is an operation, not a state. `rollback` leaves the agent `paused`. Rollback is refused from `failed` and `terminated`. Checkpoints live in process memory and are lost on restart, agents are not isolated from each other, and rollback does not restore the rate-limit window or undo external side effects (README sections 5.2, 10 and 15).

---

## 6. Memory Architecture

Memory is modeled on four functionally distinct types, each with its own storage characteristics.

| Memory type | Cognitive function | Characteristics | Proposed backend |
|---|---|---|---|
| **Working** | What the agent is holding in mind *right now* | Small, fast, short-lived | Redis |
| **Episodic** | What happened: events, actions, outcomes, in order | Append-heavy, time-indexed, queryable | PostgreSQL |
| **Semantic** | What the agent knows: facts, concepts, relations | Similarity search and graph traversal | Vector DB + knowledge graph |
| **Procedural** | How to do things: skills, policies, models | Versioned artifacts | Model registry |

### Memory flow

```
 Perception ──▶ WORKING ──┬──▶ (decay / expire)
                          │
                          ├──▶ EPISODIC  ──consolidation──▶ SEMANTIC
                          │                                    │
                          └──────────── retrieval ◀────────────┘
                                                               
 LEARNING ENGINE ──▶ PROCEDURAL (new skills / model versions) ──▶ Agent behavior
```

### Memory service contract (proposed)

- `write(agent_id, type, record, metadata)`
- `read(agent_id, type, query, limit)`
- `search(agent_id, embedding_or_query, filters)`
- `consolidate(agent_id)`: episodic → semantic summarization
- `forget(agent_id, selector, reason)`: explicit, audited deletion
- `snapshot(agent_id)` / `restore(agent_id, snapshot_id)`: used by checkpoint and rollback

### Memory integrity

- Every write is tagged with source, timestamp, and confidence
- Corruption detection through checksums and consistency checks
- Memory is **versioned** so rollback is exact
- Deletions are logged; "forget" is a policy event, not a silent operation

> **v0.1:** only episodic memory exists, in SQLite (not the proposed backends above). Each record has an agent id, timestamp, kind and JSON data. There is no source or confidence tag, no checksum, and no versioning: rollback deletes events newer than the checkpoint. The runtime does not feed memory back into the agent's prompt.

---

## 7. Safety Architecture

Safety is **engineering**: feedback loops, limits, monitoring, and control. It is enforced by the runtime, not requested from the agent.

### 7.1 Five mechanisms

| Mechanism | Purpose | Example |
|---|---|---|
| **Constraint enforcement** | Hard rules on what actions are permitted | "Never write outside this directory"; "never exceed this joint torque" |
| **Action budgets** | Bound the *amount* of consequential activity | Max API calls, spend, or movement per time window |
| **Kill switches and shutdown** | Immediate, reliable stopping | Operator override; automatic trip on violation |
| **Behavior monitors** | Detect drift and anomalies | Statistical deviation from baseline behavior |
| **Parameter rules** | Constrain *how* an allowed action may be used | `send_email` only to `@example.com`, no extra arguments, body under 200 characters |

### 7.2 Enforcement path

```
 Agent proposes action
        │
        ▼
 ┌───────────────────┐   deny    ┌─────────────────────┐
 │ Constraint check  │ ────────▶ │ Block + log + notify│
 └─────────┬─────────┘           └─────────────────────┘
           │ pass
           ▼
 ┌───────────────────┐   exceeded
 │  Budget check     │ ────────▶ throttle / block
 └─────────┬─────────┘
           │ pass
           ▼
 ┌───────────────────┐   anomalous
 │ Behavior monitor  │ ────────▶ flag / pause / escalate to human
 └─────────┬─────────┘
           │ pass
           ▼
       Execute
```

### 7.3 Safety rules

1. **Default deny** for new or unknown action types
2. **Safety runs outside the agent's control**: the agent must not be able to disable, modify, or bypass it (in v0.1 this holds for routed actions only; see the key rule in section 4)
3. **Kill switches are tested regularly**, not assumed to work
4. **Fail safe:** if the safety layer cannot reach a verdict, the action is blocked
5. **Every override is audited**

### 7.4 Implemented in v0.1

The v0.1 safety layer (`safety.py`, `rules.py`) checks every proposed action in this order and stops at the first denial:

1. **Kill switch:** tripped agents are denied everything
2. **Policy registered:** an agent with no policy is denied
3. **Action well-formed:** non-empty name, `params` is a dict, `cost` is a finite non-negative number (not a bool)
4. **Allowed set:** action name must be on the policy's allowlist (default deny)
5. **Total budget:** lifetime cost cap, charged at the policy-owned cost (`Policy.costs`); with the default `strict_costs=True` the agent's declared cost is never used
6. **Rate limit:** maximum actions per time window
7. **Parameter rules:** per-action argument checks (`muffin.rules`)
8. **Constraints:** custom functions that can veto an action

Any exception raised during a check is converted into a denial (**fail closed**).

**Remaining gap:** a policy that opts out with `strict_costs=False` still charges the agent's declared cost for any action missing from `Policy.costs` (README limitation L1).

**Parameter rule helpers** (`muffin.rules`): `required`, `only_keys`, `one_of`, `matches` (full-match regex), `max_len`, `number_between`, `email_domain`. They are written to resist common tricks: smuggled `@` signs, domain-suffix tricks, subdomains, multiple recipients, newline injection, path traversal, and wrong types (strings, booleans, NaN passed as numbers).

```python
Policy(
    allowed_actions={"send_email"},
    max_total_cost=10,
    costs={"send_email": 5},
    param_rules={"send_email": [
        rules.only_keys("to", "body"),
        rules.email_domain("to", "example.com"),
        rules.max_len("body", 200),
    ]},
)
```

**Known limits:** rules are stateless, so each sees a single call. They cannot catch a pattern across calls (for example many small emails that together leak data, or "read a secret, then send"). History-aware rules are future work. A tool with no rules accepts any arguments, so put `only_keys` on every tool.

---

## 8. Observability Architecture

> If you can't observe it, you can't trust it.

### 8.1 Five dimensions

Standard systems observability tells you if a service is *up*. Cognitive observability tells you if a mind is *behaving*.

| Dimension | Question it answers |
|---|---|
| **Belief observability** | What does the agent currently believe, and how confident is it? |
| **Decision observability** | Why did it choose this action over the alternatives? |
| **Learning observability** | What is it learning, and is it drifting? |
| **Behavioral observability** | Is it acting within its normal pattern? |
| **System observability** | Is the underlying infrastructure healthy? (CPU, memory, latency, errors) |

### 8.2 Signals

| Signal | Content | Proposed tooling |
|---|---|---|
| **Metrics** | Counters, gauges, histograms | Prometheus |
| **Logs** | Structured event records | Structured logging + Loki |
| **Traces** | End-to-end decision traces across layers | OpenTelemetry |
| **Dashboards** | Fleet and per-agent views | Grafana |
| **Alerts** | Threshold and anomaly triggers | Alertmanager or equivalent |

### 8.3 The decision trace

The most important artifact in the system. For every action, we record:

```
decision_id · agent_id · timestamp
inputs        (perceptions, retrieved memories)
beliefs       (relevant state + confidence)
goals         (active goal and subgoal)
candidates    (options considered + scores)
chosen        (action selected + why)
safety        (constraints, budgets, verdicts)
outcome       (result observed afterward)
explanation   (the agent's own stated reason, via Agent.explain())
```

This is what makes an agent's behavior **traceable and auditable**. The `explanation` field is the agent's own claim: evidence for debugging, not proof of the real reason.

> **v0.1 records a subset:** `decision_id`, `agent_id`, `ts` and `event` on every entry, plus `step`, `perception`, `action`, `params`, `verdict`, `outcome`, `explanation` and (for blocked actions) `reason`, depending on the event. There are no `beliefs`, `goals` or `candidates` fields yet, and params and outcomes are stored verbatim with no redaction (README limitation L8).

---

## 9. Interfaces and APIs

| Interface | Audience | Purpose | Layer |
|---|---|---|---|
| **Agent SDK** | Agent developers | Implement perception, belief update, decision, action | L2 / L10 |
| **Admin API** | Operators | Spawn, configure, pause, roll back, kill; manage fleets | L2 / L9 |
| **Monitoring API** | Observability tools | Export metrics, logs, traces | L8 |
| **Safety API** | Safety layer and auditors | Define policies, query verdicts, trigger overrides | L6 |
| **Public API** | External integrators | Stable, versioned external surface | L10 |

### Agent SDK shape (Python, as in v0.1)

```python
from muffin import Action, Agent

class MyAgent(Agent):
    def perceive(self, raw_input): ...                 # optional (default: identity)
    def update_beliefs(self, perception) -> None: ...  # optional
    def decide(self) -> Action | None: ...             # required
    def act(self, action: Action): ...                 # required; the return value is the outcome

# Everything else (memory, logging, safety, lifecycle) is provided by the runtime.
```

### Implemented SDK additions (v0.1)

- **`Agent.explain()`** is an optional hook. Whatever it returns is recorded as `explanation` in the decision trace for acted, blocked, and no-action steps.
- **`LLMAgent`** (`llm_agent.py`) uses a language model as the `decide` step. Each turn the model returns JSON `{"action", "params", "reason"}`. Untrusted input is delimited in `<input>` tags and the system prompt instructs the model to treat it as data. `<`, `>` and `&` in that input and in the history are escaped so it cannot close or forge the tag, but delimiters are still only a hint to the model (README limitation L2). Unknown or hallucinated tool names are passed through on purpose so the **safety layer, not the agent, says no**. Unparseable replies and model outages become safe no-actions.
- **Providers** (`providers.py`): an agent needs only a function `complete(system, prompt) -> str`. `AnthropicCompleter` is the bundled implementation (optional dependency `muffin-ai[llm]`). It follows the public SDK interface but is not exercised against the live API in the test suite.

**Security stance:** assume the model can be fully compromised by prompt injection. Containment comes from the policy enforced outside the model, not from the model behaving well.

### API design rules

- Versioned from day one
- Every endpoint authenticated and authorized
- Every state-changing call produces an audit record
- Idempotent where possible

---

## 10. Failure Handling

We enumerate failures by category and design a response for each.

| Failure category | Example | Response |
|---|---|---|
| **Perception** | Bad or missing sensor/input data | Confidence downgrade, fallback behavior, alert |
| **Belief** | Corrupted or contradictory beliefs | Consistency check, rollback to checkpoint |
| **Memory** | Corrupted or lost records | Checksums, replication, restore from snapshot |
| **Decision** | Confident wrong action | Safety layer veto, human escalation |
| **Learning** | Drift, runaway feedback | Drift detection, freeze learning, revert model version |
| **Safety** | Safety layer unreachable | **Fail closed**: block actions |
| **Infrastructure** | Node crash, network partition | Restart from checkpoint, graceful degradation |
| **Multi-agent** | Deadlock, conflicting actions, emergent behavior | Coordination timeouts, arbitration, population-level kill |

### Graceful degradation ladder

```
 Full capability
      │  resource pressure / partial failure
      ▼
 Reduced capability (non-essential services shed)
      │
      ▼
 Safe mode (minimal, conservative behavior)
      │
      ▼
 Pause and wait for human
      │
      ▼
 Terminate with state preserved
```

---

## 11. Data Flow Examples

### 11.1 A single agent decision

1. **L0/L1:** a sensor reading or user input arrives
2. **L2:** the runtime delivers it to the agent's `perceive`
3. **L3:** working memory updated; episodic and semantic memory queried
4. **L5:** world model and planner consulted
5. **Agent:** `decide` returns a proposed action
6. **L6:** constraints, budgets, and monitors evaluated
7. **L2 → L0/L1:** approved action executed
8. **L3 / L4:** outcome written to episodic memory; learning signal emitted
9. **L8:** decision trace, metrics, and logs emitted

### 11.2 Operator emergency stop

1. Operator presses kill in the **L9** control panel
2. **L9** calls the Admin API → **L2** runtime
3. **L6** kill switch fires; pending actions are blocked
4. **L2** terminates the agent, preserving state
5. **L8** logs the event; alerts fire
6. **L9** audit trail records who, when, and why

### 11.3 Drift detected

1. **L8** behavior monitor flags deviation from baseline
2. **L6** raises severity; policy says "pause on high drift"
3. **L2** pauses the agent and takes a checkpoint
4. **L9** notifies an operator with the decision traces
5. Operator chooses: resume, roll back, retrain, or kill

---

## 12. Technology Mapping

Proposed, not final. Tools are chosen per layer and can be swapped behind the interface.

| Layer | Candidate technologies |
|---|---|
| L0 | Embedded controllers, ROS 2 (robotics), GPUs |
| L1 | Linux, Docker, Kubernetes |
| L2 | Python (core), Rust/C++ for performance-critical paths, FastAPI, gRPC |
| L3 | Redis, PostgreSQL (SQLAlchemy + Alembic), vector database, graph store, model registry |
| L4 | Experiment tracking, Ray for distributed compute |
| L5 | Planning library, simulation (MuJoCo, PyBullet, Isaac Sim, Gymnasium) |
| L6 | Policy engine, constraint checker |
| L7 | Kafka or gRPC messaging, coordination protocols |
| L8 | Prometheus, Grafana, Loki, OpenTelemetry |
| L9 | Web control panel (FastAPI + frontend) |
| L10 | Versioned REST/gRPC API, Python SDK, docs site |

---

## 13. Build Order

Built bottom-up, with a **minimal vertical slice first** so that value is demonstrable early.

| Stage | Deliverable | Layers touched |
|---|---|---|
| **0** | Architecture and interface specs (this document) | all |
| **1** | Runtime skeleton: spawn, run, kill a trivial agent | L1, L2 |
| **2** | Checkpoint and rollback | L2, L3 |
| **3** | Working and episodic memory services | L3 |
| **4** | Structured logging and basic metrics | L8 |
| **5** | Safety v0: constraints, action budgets, kill switch | L6 |
| **6** | Decision traces and a simple dashboard | L8, L9 |
| **7** | Semantic memory and consolidation | L3 |
| **8** | Learning engine: experiment tracking, model versioning | L4 |
| **9** | Planning services and world model | L5 |
| **10** | Multi-agent coordination | L7 |
| **11** | Public API and SDK | L10 |

**Status against this plan (v0.1):** stage 1 is done. Stage 2 is partly done (in-process checkpoints and a partial rollback; see README limitations L3 and L4). The episodic part of stage 3 and the structured-logging part of stage 4 are done. Stage 5 has its initial controls (constraints, budgets, kill switch, parameter rules), with known holes tracked as README limitations L1, L2 and L14. The decision-trace half of stage 6 is done; metrics and the dashboard are not. Stages 7 to 11 are not started.

**First vertical slice (recommended wedge):** a runtime that can run a simple agent with persistent episodic memory, a hard kill switch, action budgets, and a decision-trace log. That alone demonstrates the core promise: *an agent you can remember, control, and explain.*

---

## 14. Testing Strategy

| Level | What is tested |
|---|---|
| **Unit** | Each component in isolation |
| **Layer contract** | Each layer against mocks of its neighbors; interface conformance |
| **Integration** | Adjacent layers together |
| **Fault injection** | Crash agents, corrupt memory, drop the network, delay the safety layer |
| **Safety verification** | Kill switches, budgets, and constraints tested adversarially |
| **Long-horizon soak** | Run agents for extended periods to find drift and leaks |
| **Simulation** | Physical-world behavior validated in simulation before hardware |

**Rule:** a safety mechanism that has not been tested to fail is assumed broken.

---

## 15. Open Design Questions

| Question | Why it matters |
|---|---|
| What is the minimal Agent SDK that is still useful? | Adoption depends on low friction |
| How are checkpoints defined for agents with external side effects? | Rolling back memory cannot un-send an email |
| What is the right consistency model for multi-agent shared memory? | Affects correctness and performance |
| How do we measure "drift" rigorously? | Safety monitoring needs concrete metrics |
| How should action budgets be expressed? | Must be expressive without being brittle |
| How do we keep the safety layer unbypassable by a capable agent? | Isolation and trust boundaries are critical |
| Single-tenant or multi-tenant first? | Shapes isolation, security, and cost |
| Build vs. integrate for each backing store? | Reduces scope but adds dependencies |

---

*This document is a living design. When a prototype contradicts it, update the document.*
