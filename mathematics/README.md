# Mathematics

Pillar 1 of the MUFFIN.AI founding document: **Mathematics**, "from first principles to AGI-grade systems."

**Rule (from the document):** you do not move to the next topic until you have implemented the current one in code. Math that does not become code within two weeks of learning it is math you have read, not learned. Every item below ends in a small, tested program.

This is a learning track, not part of the MUFFIN runtime. Code from here that the runtime needs (for example a bound checker) graduates into `src/muffin/` only through a normal, tested change.

## Existing work

| Topic | Where it lives | The document's Build |
|---|---|---|
| 1 Algebra | your `ALGEBRA-` repo | Symbolic expression simplifier with polynomial expansion, factoring and linear-system solving, no SymPy; then use it on a real optimization problem. That matches the repo's planned symbolic-engine and Lagrange-multiplier phases |
| 7 Linear algebra | your `linear-algebra-playground` repo | Every matrix operation from scratch without built-in decompositions; PCA on a real dataset; SVD from scratch for image compression. Check the repo against these three items |

## The curriculum, in order

Durations are the document's estimates. Topic numbers match the document, which holds the topic lists, books and full Build for each.

| Tier | Months | # | Topic | Build (short form) | Status |
|---|---|---|---|---|---|
| 0 Absolute foundation | 6 | 1 | Algebra (2) | Symbolic simplifier, no SymPy | [ ] in progress |
| | | 2 | Geometry (2) | 2D transformation engine by matrix multiplication; perspective projection 3D to 2D | [ ] |
| | | 3 | Number theory (2) | Euclid, modular exponentiation, RSA from scratch; a hash function and collision test | [ ] |
| | | 4 | Calculus (2) | Gradient descent with no libraries; 3D loss surface; automatic differentiation on a small graph | [ ] |
| | | 5 | Combinatorics (2) | Enumeration and backtracking search applied to agent task allocation | [ ] |
| | | 6 | Inequalities (2) | Jensen's inequality numerically; a Chebyshev-based bound checker for agent behavior, verified by simulation | [ ] |
| 1 Core machinery | 9 | 7 | Linear algebra (4) | Matrix operations, PCA and SVD from scratch | [ ] in progress |
| | | 8 | Numerical methods (3) | Newton-Raphson; stable vs naive backprop; LU-based inversion; document where the naive version breaks | [ ] |
| | | 9 | Probability theory (2) | Bayesian belief updater, then multiple competing hypotheses | [ ] |
| | | 10 | Statistics (2) | Behavior evaluator: did a policy change help or was it noise (MLE, bootstrap, hypothesis test) | [ ] |
| 2 Optimization and information | 4 | 11 | Information theory (2) | Memory compression by mutual information; KL divergence of belief shift; entropy over time | [ ] |
| | | 12 | Optimization theory (2) | SGD, Adam, RMSProp from scratch; adversarial loss landscape with saddle points | [ ] |
| 3 Systems and agent math | 12 to 15 | 13 | Dynamical systems (2) | Inverted pendulum fixed points; stability of the agent's learning update rule | [ ] |
| | | 14 | Control theory (3) | PID vs LQR vs a basic MPC on the pendulum | [ ] |
| | | 15 | Kalman filters (3) | Kalman filter and EKF fusing noisy GPS and IMU | [ ] |
| | | 16 | Markov decision processes (2) | Value and policy iteration on a gridworld; extend to a POMDP | [ ] |
| | | 17 | RL mathematics (6) | Q-learning, SARSA and REINFORCE from scratch, compared | [ ] |
| 4 Advanced systems math | 6 | 18 | Monte Carlo methods (2) | MCTS on Connect Four; rollout planning with your own agent | [ ] |
| | | 19 | Graph theory (4) | Knowledge graph for agent memory; BFS and A* retrieval; spectral clustering | [ ] |
| | | 20 | Game theory (3) | Multi-agent resource competition converging to Nash equilibrium; cooperative variant | [ ] |
| 5 Foundations | 18 to 20 | 21 | Real analysis (5) | Epsilon-delta verifier; Riemann integration vs numerical methods | [ ] |
| | | 22 | Abstract algebra (4) | Symmetric group axioms; finite fields and an error-correcting code; SO(3) for orientation | [ ] |
| | | 23 | Topology (5) | Simplicial complexes and persistent homology on agent logs; UMAP or t-SNE | [ ] |
| | | 24 | Advanced control theory (6) | Lyapunov stability proof and a Control Barrier Function that guarantees the agent never enters a forbidden region | [ ] |

## Where this feeds MUFFIN

These topics map onto open items in the main README. They are not a reason to jump the order above.

| Topic | MUFFIN question it informs |
|---|---|
| 6 Inequalities, 10 Statistics | Measuring whether a policy change helped (research agenda R1 and R2) |
| 13 Dynamical systems | Stability of an agent's update rule; the same analysis as simulation topic 16 |
| 11 Information theory, 19 Graph theory | Which memories to keep, and semantic memory retrieval (Stage D) |
| 24 Advanced control theory | A Control Barrier Function is a stronger form of what `SafetyLayer` does today: a hard guarantee that actions stay inside an allowed region, not just a rule list |

## Notes on order

- Tiers 4 and 5 are year 3 onwards in the document: "do not rush here."
- Topics 13 to 15 reappear in `simulation/` (Pillar 3). Build them once, in whichever folder you reach first, and link from the other.
