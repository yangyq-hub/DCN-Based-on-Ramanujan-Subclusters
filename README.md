# DCN-Based-on-Ramanujan-Subclusters

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Rethinking Data-Center Network for AI: A Co-designed Architecture with Ramanujan Graphs and Spectral Principles**

This repository contains the source code and simulation framework for the paper:

> Y. Yang†, B. Xiao†, H. Xu, S. Zhang, C. Ma\*. "Rethinking Data-Center Network for AI: A Co-designed Architecture with Ramanujan Graphs and Spectral Principles." *Submitted to Nature*.
>
> \*Corresponding author. Email: macheng@tsinghua.edu.cn  
> †These authors contributed equally to this work.

## Overview

We present a co-designed data center network (DCN) architecture that holistically integrates **topology**, **routing**, and **scheduling** around a unified spectral principle. The three pillars are:

1. **Topology** — Hierarchical networks built from Ramanujan subclusters with near-optimal expansion properties, constructed via simulated annealing for arbitrary degrees/sizes.
2. **Routing** — Spectral-health-aware routing that combines offline precomputation with lightweight online eigenvalue estimation to preserve network connectivity under congestion and failures.
3. **Scheduling** — Topology-aware scheduling using spectral-affinity clustering followed by simulated-annealing refinement to align distributed training workloads with network structure.


## Repository Structure

```
DCN-Based-on-Ramanujan-Subclusters/
├── part-routing/                    # Discrete-event network simulator (routing & topology)
│   ├── main.py                      # Main entry: run routing experiments
│   ├── anal.py                      # Log parser & visualization for simulation results
│   ├── topology/                    # Topology generators
│   │   ├── topology_base.py         # Abstract base class for all topologies
│   │   ├── ramanujan.py             # Ramanujan graph construction (SA-based)
│   │   ├── fat_tree.py              # Fat-Tree topology
│   │   ├── jellyfish.py             # Jellyfish random-regular topology
│   │   ├── dragonfly.py             # Dragonfly topology
│   │   ├── xpander.py               # Xpander topology
│   │   └── ocs.py                   # OCS reconfigurable topology
│   ├── routing/                     # Routing strategies
│   │   ├── routing_base.py          # Abstract base class for routing
│   │   ├── shortest_path.py         # Dijkstra shortest-path routing
│   │   ├── ecmp.py                  # Equal-Cost Multi-Path routing
│   │   ├── spectral.py              # Spectral-health-aware routing (core contribution)
│   │   └── valiant.py               # Valiant load-balanced routing
│   ├── traffic/                     # Traffic pattern generators
│   │   ├── traffic_base.py          # Abstract base class
│   │   ├── uniform.py               # Uniform random traffic
│   │   ├── hotspot.py               # Hotspot traffic
│   │   ├── all_reduce.py            # All-reduce collective traffic
│   │   └── cross.py                 # Cross-cluster hotspot traffic
│   └── simulator/                   # Event-driven simulator core
│       ├── simulator.py             # Main simulation engine
│       ├── event.py                 # Event definitions
│       ├── node.py                  # Network node model
│       ├── link.py                  # Network link model
│       └── packet.py                # Packet model
│
├── llmSimulator-main/               # LLM distributed training simulator
│   ├── simulation.py                # Pipeline + data parallel training simulator
│   ├── suanfa.py                    # Spectral clustering for node grouping
│   ├── test1.py                     # Standalone training simulation script
│   ├── backend/                     # Web-based visualization backend (Node.js + Python)
│   │   ├── server.js                # Express.js API server
│   │   ├── network.py               # Network topology utilities
│   │   ├── simulator.py             # Backend simulation engine
│   │   ├── schedule.py              # Topology-aware scheduling algorithms
│   │   │                              (K-means, greedy, SA, spectral+SA)
│   │   ├── run_scheduler.py         # Scheduler execution script
│   │   ├── traffic.py               # Traffic generation
│   │   └── topo/                    # Pre-generated topology adjacency matrices
│   │       ├── ramanujan.txt
│   │       ├── fat_tree.txt
│   │       ├── dragonfly.txt
│   │       ├── fully_connected.txt
│   │       └── random_graph.txt
│   ├── network/                     # Network simulation module
│   │   ├── sim.py                   # Simplified simulator
│   │   └── topologies/              # Additional topology files
│   └── frontend/                    # Vue 3 + Vite web dashboard
│       ├── src/
│       └── package.json
│
└── docs/                            # Documentation and figures
```

## System Requirements

### Software Dependencies

| Component | Requirement |
|-----------|------------|
| **Python** | ≥ 3.8 |
| **Node.js** | ≥ 16.0 (for web visualization only) |
| **Operating System** | Linux, macOS, or Windows |

### Python Packages

```
numpy >= 1.21.0
scipy >= 1.7.0
networkx >= 2.6.0
pandas >= 1.3.0
matplotlib >= 3.4.0
seaborn >= 0.11.0
scikit-learn >= 1.0.0
tqdm >= 4.62.0
```

### Non-standard Hardware

No specialized hardware is required. All experiments run on standard CPUs. Large-scale simulations (≥1000 nodes) benefit from ≥16 GB RAM.

### Typical Install Time

< 5 minutes on a standard desktop computer (excluding dependency download time).

## Installation

```bash
# Clone the repository
git clone https://github.com/yangyq-hub/DCN-Based-on-Ramanujan-Subclusters.git
cd DCN-Based-on-Ramanujan-Subclusters

# Create and activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt
```

### Web Visualization (Optional)

```bash
# Backend
cd llmSimulator-main/backend
npm install

# Frontend
cd ../frontend
npm install
```

## Demo / Quick Start

### 1. Routing Simulation (Core Experiment)

Run a small-scale routing experiment comparing Ramanujan, Fat-Tree, and Jellyfish topologies:

```bash
cd part-routing
python main.py
```

This runs a 20-node network with shortest-path routing under hotspot traffic. Results are saved to `results/`.

**Expected output:**
```
=== 生成k=4规模拓扑 ===
生成节点数为20、度数为4的Ramanujan图拓扑...
...
完成: Ramanujan - ShortestPath - 平均延迟: X.XXXms, 吞吐量: X.XXXGbps
完成: Fat-Tree - ShortestPath - 平均延迟: X.XXXms, 吞吐量: X.XXXGbps
```

**Typical run time:** ~2–5 minutes for k=4 (20 nodes); ~30–60 minutes for k=28 (980 nodes).

To run the full-scale experiment (all scales and routing strategies), uncomment the corresponding entries in `main.py`:

```python
scales = {
    'k=4': {'nodes': 20, 'degree': 4, 'k': 4},
    'k=8': {'nodes': 80, 'degree': 7, 'k': 8},
    # ... uncomment additional scales
    'k=28': {'nodes': 980, 'degree': 22, 'k': 28},
}

routing_strategies = {
    'ShortestPath': ShortestPathRouting,
    'ECMP': ECMPRouting,
    'Spectral': SpectralGapRouting,
}
```

### 2. LLM Training Simulation

Run the distributed training simulator with pipeline and data parallelism:

```bash
cd llmSimulator-main
python simulation.py hybrid <topology_file> <config_file>
```

Example with the provided Fat-Tree topology:

```bash
cd llmSimulator-main
python simulation.py hybrid backend/topo/fat_tree.txt tliuliang.txt
```

**Typical run time:** ~1–10 minutes depending on configuration.

### 3. Scheduling Comparison

Run the spectral clustering node grouping:

```bash
cd llmSimulator-main
python suanfa.py
```

### 4. Web-Based Visualization (Optional)

```bash
# Terminal 1: Start backend
cd llmSimulator-main/backend
npm start

# Terminal 2: Start frontend
cd llmSimulator-main/frontend
npm run dev

# Open http://localhost:5173/ in your browser
```

## Reproducing Paper Results

### Figure 3: Ramanujan Graph Properties

The simulated-annealing Ramanujan graph construction and fault-tolerance analysis are implemented in `part-routing/topology/ramanujan.py`. Key parameters:

- Initial temperature: 100
- Cooling rate: 0.95
- Max iterations: 20,000 (with early stopping at 2,000 non-improving iterations)
- Target: minimize second-largest eigenvalue λ₂

### Figures 4: Routing Performance Comparison

Modify `part-routing/main.py` to enable all scales and routing strategies, then run:

```bash
cd part-routing
python main.py
```

Results are saved to `results/simulation_results_test.csv`. Use `anal.py` to generate plots:

```bash
python anal.py
```

### Figure 5–6: Scheduling and End-to-End Training

The topology-aware scheduler is in `llmSimulator-main/backend/schedule.py`. Compare scheduling methods:

```python
from schedule import QuantumInspiredTopoScheduler

scheduler = QuantumInspiredTopoScheduler("topo/ramanujan.txt")

# Compare methods
for method in ["random", "kmeans", "sa", "kmeans_sa"]:
    groups = scheduler.schedule(num_stages=16, method=method, num_groups=8)
    metrics = scheduler.evaluate_schedule(groups)
    print(f"{method}: intra-group BW = {metrics['avg_intra_group_bandwidth']:.2f}")
```

### Simulation Parameters (Default)

| Parameter | Value |
|-----------|-------|
| Network nodes | 1,092 |
| Average degree | 24 |
| Link bandwidth | 10 Gbps |
| Packet loss rate | 1×10⁻⁴ |
| Model parameters | 175B |
| Hidden size | 12,288 |
| Layers | 96 |
| Batch size | 256 |
| Micro-batch size | 2 |
| Sequence length | 2,048 tokens |

## Key Algorithms

| Algorithm | File | Description |
|-----------|------|-------------|
| SA-based Ramanujan construction | `part-routing/topology/ramanujan.py` | Degree-preserving edge swaps to minimize λ₂ |
| Spectral-health routing | `part-routing/routing/spectral.py` | Two-tier routing with online spectral gap estimation |
| Spectral-affinity scheduling | `llmSimulator-main/backend/schedule.py` | Spectral clustering + SA refinement |
| Pipeline/data parallel simulation | `llmSimulator-main/simulation.py` | Event-driven distributed training simulator |

## Known Limitations

- The `visualization` module referenced in `part-routing/main.py` is not included; comment out `from visualization.plot import plot_comparison` and the `plot_comparison(all_df)` call if running without it, or use `anal.py` for post-hoc visualization.
- The web visualization frontend is a development prototype and may require adjustments for production use.
- Large-scale experiments (k≥24) may require significant memory (≥16 GB) and computation time.


## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.


## Contact

For questions about the code or paper, please contact:

- **Cheng Ma** (Corresponding author) — macheng@tsinghua.edu.cn

Department of Precision Instrument, Center for Brain Inspired Computing Research (CBICR), Tsinghua University, Beijing, China.
