# Simulation

Pillar 3 of the MUFFIN.AI founding document: **Physics & Simulation**, "how reality constrains intelligence."

**Rule (from the document):** every physics concept must be simulated before it is trusted. If you cannot simulate it, you do not understand it well enough to build with it. In this repo that means each topic ends in a small, tested program, not notes.

This is a learning and research track, not shipped MUFFIN functionality. The runtime in `src/muffin/` does not depend on anything here, and the robotics and physical-actuator layers stay out of scope until this work justifies them (README, Stage E).

## Do first: the items that connect to MUFFIN

| # | Topic | Deliverable (the document's "Build:") | Folder | Status |
|---|---|---|---|---|
| 1 | Mathematical methods | ODE solvers from scratch (Euler, RK4, adaptive RK45); harmonic, damped and driven oscillators; phase portraits | `ode/` | [ ] |
| 16 | Discrete dynamical systems | Model the agent's reward signal as a discrete system; logistic-map bifurcation diagram; find the fixed points and the maximum stable learning rate of the agent's update rule | `discrete-dynamics/` | [ ] |
| 28 | Simulation philosophy | Written simulation audit of the chosen simulator: what it models, fidelity rating, what it does not model, a mitigation for each gap | `simulation-audit.md` | [ ] |
| 33 | Gymnasium | A custom environment where an agent allocates compute, memory and communication across sub-agents; heavy penalty for safety violations, reward for throughput; vectorized; passes the Gymnasium env checker | `envs/resource_allocation/` | [ ] |

Item 33 is the bridge to the runtime: the safety-violation count is exactly what `SafetyLayer` produces. It is also a natural testbed for research questions R1 to R3 in the main README.

## The rest of the pillar, by layer

Durations are the document's estimates. Topic numbers match the document, which holds the topics, reading and Build for each.

| Layer | Months | Topics | Status |
|---|---|---|---|
| 0 Math for physics | 3 | 1 Mathematical methods | [ ] |
| 1 Classical physics | 6 | 2 Classical mechanics, 3 Electrostatics and circuits, 4 Thermodynamics, 5 Waves and optics, 6 Electromagnetism, 7 Modern physics | [ ] |
| 2 Computational physics | 4 | 8 Numerical physics, 9 Optimization | [ ] |
| 3 Advanced mechanics | 9 | 10 Advanced mechanics, 11 Newtonian, 12 Rigid body dynamics, 13 Lagrangian and Hamiltonian, 14 Kinematics and robot geometry | [ ] |
| 4 Dynamical systems | 6 | 15 Continuous dynamics, 16 Discrete dynamics, 17 Chaos theory | [ ] |
| 5 Control theory | 9 | 18 Feedback control, 19 State-space control, 20 MPC | [ ] |
| 6 Estimation and sensors | 6 | 21 Sensor fundamentals, 22 Kalman filtering, 23 SLAM, 24 Signals and systems | [ ] |
| 7 Electronics and actuators | 4 | 25 Motors and actuators, 26 Embedded systems | [ ] |
| 8 Statistical mechanics | 3 | 27 Statistical mechanics | [ ] |
| 9 Simulation environments | 9 | 28 Simulation philosophy, 29 MuJoCo, 30 Isaac Sim, 31 PyBullet, 32 ROS 2, 33 Gymnasium | [ ] |
| 10 Sim-to-real | 4 | 34 Reality gap, 35 Domain randomization, 36 System identification | [ ] |
| 11 Physics of learning | 9 | 37 Loss landscapes, 38 Free energy principle | [ ] |
| 12 Advanced numerics | 9 | 39 Numerical physics (advanced), 40 Optimization (advanced) | [ ] |

## Notes on order

- The document marks layers 12 (and the matching advanced math tier) as year 3 onwards: "do not rush." Do not start them early.
- Items 34 to 36 (sim-to-real) need real hardware to close the loop. Skip them until there is a use case that justifies hardware.
- Pure-Python items (1, 16, 28) need no dependencies. Items 29 to 33 add simulator packages, so keep them in `envs/` with their own requirements file, not in the core package's dependencies.
