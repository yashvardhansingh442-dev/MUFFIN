# Systems

Pillar 2 of the MUFFIN.AI founding document: **Systems Engineering**, "the tools your cognitive infrastructure is actually built with."

**Rule (from the document):** a tool you have read about is not a tool you own. You own it when you have used it to build something that broke, debugged it alone, and fixed it without asking anyone. In this repo every topic ends in working, tested code or a written postmortem.

This is a learning and build track. The core package in `src/muffin/` stays zero-dependency; anything that needs Postgres, Redis, Kafka, Docker or a web stack lives here, in its own folder with its own requirements file.

## Do first: the items that connect to MUFFIN

| # | Topic | Deliverable (the document's "Build:") | Link to the repo | Status |
|---|---|---|---|---|
| 3 | Python | A typed, tested, documented agent runtime core with a decision loop, structured logging, async task management and a REST API exposing agent state; plus a one-page explanation of LangGraph's state machine in your own words | `src/muffin/` already covers the loop, tracing, types and tests. Missing: async tasks, REST API, the LangGraph write-up | [ ] partly met |
| 20 | OpenTelemetry | Trace one agent decision from perception to action across every service, with timing per component, memory state at decision time, and which safety rules were evaluated | The planned OpenTelemetry exporter (README section 9.2) | [ ] |
| 22 | Agent control panel | A browser UI with live agent state, decision log, pause/resume/kill, safety-rule editor, memory inspector, and an audit log of every human intervention. Done when a non-engineer can find a misbehaving agent and kill it with no code. Kill switch within 3 clicks | The planned human approval gates (README Stage C, ASI09) | [ ] |
| 26 | Failure-first design | A chaos session on the deployed system: kill pods, partition the network, add 500 ms latency to database calls, corrupt a queue message. Must degrade gracefully and lose no committed memory; write a postmortem per failure found | The open test gaps and limitations L15 and L12 in the README | [ ] |

Item 22's stack in the document is TypeScript, React, WebSocket and a FastAPI backend with Prometheus as a data source. It requires authentication, role-based access (observer, operator, administrator) and an immutable intervention log.

## The rest of the pillar, by layer

Durations are the document's estimates. Topic numbers match the document, which holds the topics, reading and Build for each.

| Layer | Months | Topics | Status |
|---|---|---|---|
| 0 CS foundations | n/a | Data structures, algorithms, operating-systems internals, networking. Build: 150 LeetCode problems (50 easy, 80 medium, 20 hard), one a day, for fluency | [ ] |
| 1 Environment, version control, core languages | 6 | 1 Linux (Ubuntu), 2 Git + GitHub, 3 Python, 4 C++ | [ ] |
| 2 Advanced core languages | 6 | 5 Rust, 6 Bash, 7 SQL | [ ] |
| 3 Data and memory | 9 | 8 PostgreSQL, 9 Redis, 10 Vector databases, 11 SQLAlchemy + Alembic | [ ] |
| 4 Agent and compute | 6 | 12 FastAPI, 13 gRPC, 14 Ray, 15 Kafka | [ ] |
| 5 Deployment and infrastructure | 3 | 16 Docker, 17 Kubernetes | [ ] |
| 6 Observability and safety | 6 | 18 Prometheus, 19 Grafana, 20 OpenTelemetry, 21 Experiment tracking | [ ] |
| 7 Interface and control | 3 | 22 Agent control panel | [ ] |
| 8 Architecture and systems thinking | 15 to 18 | 23 Clean architecture, 24 Distributed systems, 25 System design, 26 Failure-first design, 27 Designing data-intensive applications | [ ] |

## Where the document's memory topics meet the repo

Topics 8 and 9 describe a Postgres episodic memory (partitioned, with embeddings, tuned to 10 million records) and a Redis working memory. The repo today uses SQLite for episodic memory and leaves working memory to the agent. Topic 23's Build includes proving the database can be swapped from PostgreSQL to SQLite with no change to domain logic, which is the interface boundary `EpisodicMemory` should grow into. The memory backend choice is an open Stage C item in the README.

## Notes on order

- Layer 8 comes last and is the longest (15 to 18 months). Do not start system design before there is something to design.
- Kafka, Ray and Kubernetes (topics 14, 15, 17) are not needed until there is more than one agent process to run, which is Stage D territory in the README.
- Layers 0 to 3 are the prerequisites for everything else. The Layer 0 Linux build (hardened Ubuntu server, SSH hardening, firewall, cron backups, a process-monitor script, and diagnosing an injected failure from logs only) is the best first project.
