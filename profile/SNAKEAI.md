# SnakeAI-MLOps — Interview Reference

---

## Index

1. [What It Is — One Paragraph](#1-what-it-is)
2. [Architecture — The Full Stack](#2-architecture)
3. [The Four Algorithms — Concepts and Results](#3-the-four-algorithms)
4. [Key Engineering Decisions](#4-key-engineering-decisions)
5. [The Hard Problems — Stories](#5-the-hard-problems)
6. [Follow-Up Q&A](#6-follow-up-qa)

---

## 1. What It Is

SnakeAI-MLOps is an end-to-end reinforcement learning system — not a notebook, not a demo. It's three things at once: a C++ game engine running agents in real time, a Python training pipeline producing model artifacts across four RL algorithms, and a production integration layer connecting them. The interesting work wasn't the ML — it was the integration: getting trained PyTorch weights running inside a C++ game loop, with a proper artifact contract, CI/CD, and a diagnostic layer that surfaces failures early.

**Why I built it**: I wanted to force myself into a real C++ systems problem — specifically the kind where you're managing memory manually and integrating with a runtime that doesn't hold your hand. The Snake game was the vehicle; the integration was the point.

---

## 2. Architecture

```
Python Training Layer
  └── 4 trainers: Q-Learning, DQN, PPO, Actor-Critic
  └── Unified evaluator — apples-to-apples comparison
  └── TorchScript conversion pipeline (.pth → .pt)

Artifact Layer
  └── Q-Learning:   JSON Q-table (no ML runtime needed)
  └── Neural nets:  .pt TorchScript (C++ loadable)

C++ Runtime
  └── SFML game engine (loop, rendering, collision)
  └── MLAgents.cpp: agent abstraction over all types
  └── TorchInference.cpp: LibTorch integration
  └── ModelDebugger.cpp: standalone diagnostic tool
  └── TORCH_AVAILABLE compile flag: graceful degradation

CI/CD
  └── GitHub Actions: builds with TORCH_AVAILABLE=OFF
  └── Docker image, versioned releases, GitHub Pages
```

The Python/C++ split is intentional. Same split every production HFT and game AI system uses — Python for research and iteration, C++ for runtime. Doing everything in Python would have been faster to build but wouldn't have forced the real integration problem.

---

## 3. The Four Algorithms

### Numbers to know cold

```
Q-Learning:     Avg 8.5,  Best 15, Consistency 0.75  ← most consistent
DQN (Balanced): Avg 12.3, Best 22, Consistency 0.68  ← highest average
Actor-Critic:   Avg 11.5, Best 20, Consistency 0.73  ← best balance
PPO:            Avg 10.8, Best 18, Consistency 0.71  ← weakest, not for this task
```

### Q-Learning — tabular, no neural network

The simplest form of RL. Maintains a lookup table: for every possible state, store the expected value of each action. Update that table as the agent experiences outcomes.

```
Q(s, a) ← Q(s, a) + α [reward + γ max Q(s', a') - Q(s, a)]
                         ^target             ^current estimate
                         ←────── TD error ──────────────────→
```

The TD error is "how wrong was my estimate?" — you nudge the estimate toward reality by α (learning rate).

State space: 9-bit binary encoding → 512 discrete states. Every combination of danger-ahead/left/right, current direction, food direction. The table is small enough to fully cover — every state gets visited enough times to have a reliable Q-value. This is why Q-learning has the highest consistency (0.75 stddev) despite the lowest mean.

**When it fails**: when the state space is too large to enumerate. A more complex game with continuous positions would have infinite states — you can't build a table.

### DQN — neural network approximates the Q-table

Same Bellman update, but instead of a lookup table, a neural network approximates Q(s, a) for any input state.

```
Network: 20D input → [256, 128] shared → value stream + advantage stream
Output: 4 Q-values (one per direction)
```

**Dueling DQN**: splits the output into two streams — V(s) (how good is this state regardless of action?) and A(s,a) (how much better is this action than average?). Combined: Q(s,a) = V(s) + A(s,a) - mean(A). Learns which states are inherently bad (trap configurations) separately from which actions are bad in those states.

**Double DQN**: standard DQN always takes max Q to compute the target value, which compounds estimation errors upward over time (overestimation bias). Double DQN decouples: the online network selects which action to evaluate, the target network evaluates it. Less overestimation, more stable training.

**Experience replay**: transitions stored in a 10,000-entry ring buffer. Training samples random minibatches rather than consecutive frames. Why: consecutive game frames are highly correlated — training on them causes the network to overfit to local patterns and destabilize. Random sampling from the buffer breaks that correlation.

**Target network**: a frozen copy of the network updated every 100 steps. Used to compute the target value in the Bellman update. Without it, you're chasing a moving target (the very network you're updating) — unstable. With it, the target is stable for 100 steps at a time.

### PPO — directly optimizes the policy

Q-learning and DQN are value-based: estimate action values, pick the best. PPO is policy-based: directly learn a probability distribution over actions — "in this state, go left 60%, right 40%."

**The clip**: vanilla policy gradient (REINFORCE) updates the policy proportional to how good the action was. Large updates → unstable. PPO clips the ratio between new and old policy to [1-ε, 1+ε]. If the new policy deviates too much from where you started, the gradient is clipped to zero — you can't take catastrophically large steps.

```
L = min(ratio × advantage, clip(ratio, 1-0.2, 1+0.2) × advantage)
```

**Why it underperformed here (Avg 10.8)**: PPO's conservatism pays off in continuous, long-horizon tasks where stable policy updates over many steps matter. Snake is episodic and short — episodes end in < 200 steps and reset. The conservatism was more hindrance than help. PPO's benefit requires a longer timescale to manifest.

### Actor-Critic — value and policy together

Two networks: Actor learns the policy π(a|s). Critic learns the value function V(s).

```
TD error (δ) = reward + γ V(s') - V(s)   ← how wrong was the critic's estimate

Actor update:  policy gradient weighted by δ
Critic update: minimize (δ)²
```

The critic's value estimate gives the actor better gradient signal — instead of using raw returns (noisy), you use advantage = return - V(s) (lower variance). This is why Actor-Critic outperforms plain policy gradient.

**Why it hits the best balance (Avg 11.5, Consistency 0.73)**: the advantage function reduces gradient variance compared to DQN's Q-value estimation, producing more stable learning curves while still achieving competitive average scores.

---

## 4. Key Engineering Decisions

### State representation: 20D not 8D

Early: 8 binary features (danger in 3 directions, current direction 4-bit, food direction 4-bit). Switched to 20D: continuous distance to walls, body proximity as continuous values, food angle and distance as floats, momentum indicators.

Why: neural agents' advantage functions benefit from richer state — more information = better credit assignment. Q-learning stayed at 8-bit discrete because tabular Q requires a bounded discrete state space. The 512-state table only works if the space is finite and small.

### Artifact contract: one format per model type

12 model artifacts (4 algorithms × 3 training profiles). Early approach: ad-hoc loading logic scattered per algorithm. Problem: adding a new algorithm type required tracing multiple files.

Fixed: `convert_models_to_torchscript.py` is the single conversion gate for all neural models. It takes `.pth`, traces it to `.pt` TorchScript, validates by running a test forward pass with a known input shape. Shape mismatches caught at conversion time, not runtime.

Q-learning serializes to JSON — it's a lookup table, not a net. No ML runtime needed. Fully portable.

### Graceful degradation: TORCH_AVAILABLE flag

LibTorch is a heavy dependency — CI environments don't always have it, target machines may not. CMake flag `TORCH_AVAILABLE=OFF` makes neural agents fall back to heuristic behavior. Q-learning stays fully functional via JSON. The system is always usable with reduced capability rather than broken.

This made CI deterministic — build and test on any runner without LibTorch install issues.

### ModelDebugger as first-class tool

Rather than debugging model loading inside the full game loop (rendering + input + game state all running), built a standalone tool that: scans model files, checks LibTorch install health, instantiates each agent, runs test inference with synthetic input, logs everything structured.

Failures surface at startup with specific error messages, not mid-session as weird behavior.

---

## 5. The Hard Problems — Stories

### The LibTorch memory corruption

Models trained fine in Python. Loaded into C++ via LibTorch, they worked correctly for a few minutes then started producing garbage outputs. No crash, no exception — just gradual degradation. Looked like training instability but training was already done.

**Investigation path**:
1. First hypothesis: state encoding drift between Python and C++. Verified feature computation was identical. Ruled out.
2. Stripped to bare minimum — model loading and inference only, no rendering, no game loop, fixed synthetic inputs. Degradation still appeared.
3. Added logging: tensor allocation counts, weight tensor memory addresses, GPU memory usage at each inference call. After a few thousand iterations: GPU memory growing linearly, weight tensor addresses changing between calls — tensors being recreated rather than reused.

**Root cause**: creating new tensor objects for input encoding at every inference call. Python's GC handles this silently — reference counts drop, memory reclaimed. C++ doesn't. Tensors went out of scope, their destructors didn't properly release GPU memory (missed explicit cleanup calls), new allocations landed in partially freed space.

**Fix**: RAII pattern. Input tensor created once during agent initialization, reused across all inference calls — write new values into the existing GPU buffer, don't allocate. Explicit cleanup in destructor.

**Validation**: soak test — fixed seed, fixed input sequence, 50,000 iterations. Before: GPU memory grew linearly, outputs diverged around iteration 3,000. After: GPU memory flat, outputs deterministic all 50,000 iterations.

### The model artifact contract

Ad-hoc loading was fine at one algorithm. At four algorithms with three profiles each, adding a new type meant tracing five files to understand the loading conventions. Standardized the contract:

- All neural models through one conversion script, one validation step, one output format
- All Q-table models through one serializer/deserializer
- C++ loaders: check file exists, check file size is plausible (catches truncated saves), test inference with synthetic input, verify output shape

Moved failure mode from "game crashes weirdly mid-session" to "clear error at startup."

---

## 6. Follow-Up Q&A

**What is TorchScript and why does C++ need it?**

Python PyTorch models are subclasses of `nn.Module` with Python state and a Python `forward` method. LibTorch in C++ can't load that — it doesn't know about the Python class definition. TorchScript compiles the model's computation graph into a serialized format dependent only on the graph, not the Python class. You load a `.pt` file in C++ and get a `torch::jit::script::Module` you can call `forward()` on with no Python runtime.

**Tracing vs scripting in TorchScript?**

Tracing runs the model once with a sample input, records all tensor operations. It's simpler but misses control flow that depends on data values (if/else on tensor values, variable-length loops). Scripting compiles the Python code itself — captures control flow but requires TorchScript-compatible Python (no arbitrary Python constructs). For standard feedforward nets with fixed architecture, tracing is sufficient — the computation graph is identical regardless of input values.

**Why LibTorch over ONNX Runtime?**

LibTorch is the native C++ PyTorch backend — TorchScript export is direct, no intermediate format, no format conversion risk. ONNX export occasionally loses PyTorch-specific ops or has shape inference issues, adding a debugging surface. For a project already managing Python-to-C++ complexity, adding ONNX as another layer makes debugging harder.

In production optimizing specifically for inference latency, ONNX Runtime is a legitimate choice — better quantization support, highly optimized kernels, runtime-agnostic. I'd benchmark both on target hardware and choose empirically.

**Walk me through inference end-to-end in C++**

Game loop calls `agent->get_action(game_state)`. State encoder (C++, matches Python training encoder) converts the game struct to a 20-element float array, writes into pre-allocated input tensor. LibTorch `module.forward({input_tensor})` runs the graph. Output tensor: 4 Q-values or action logits. Agent applies argmax (DQN/Q-learning) or softmax sampling (PPO/AC), returns integer action. Game loop applies it.

Median inference time on mid-range GPU: ~140 microseconds. Most of that is LibTorch overhead — the actual network computation for [20→256→128→4] is trivially fast.

**Why did PPO underperform?**

PPO's clipped surrogate objective is designed to be conservative — it prevents large policy updates, which stabilizes training in continuous long-horizon tasks. Snake is episodic and short (< 200 steps, then reset). The conservatism that protects PPO in long tasks is a hindrance here — by the time the policy update would have destabilized, the episode is already over. The task doesn't give PPO enough runway to show its advantage.

**What is experience replay and why does DQN need it?**

Neural networks learn poorly on correlated sequential data. Consecutive game frames are highly correlated — the snake's position changes by one cell. Training on them causes overfitting to local temporal patterns and unstable Q-estimates. Experience replay stores transitions in a buffer (10K here) and samples random minibatches. Random sampling breaks the temporal correlation. Secondary benefit: rare important transitions (the step before dying) stay in the buffer and get replayed multiple times rather than seen once and discarded.

**What would you do differently?**

Design the state representation upfront. I iterated from 8D to 20D midway through — this created an awkward period where some trained artifacts were on 8D state and others on 20D and the evaluator had to handle both. A clean state contract from the start avoids that. I'd also add performance instrumentation to the C++ inference path from day one — I added it later when I noticed latency variance. Easier to build in than to retrofit.
