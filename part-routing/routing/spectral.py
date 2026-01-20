#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Spectral Gap Routing Strategy
"""

import networkx as nx
import numpy as np
import random
import heapq
import scipy.sparse as sp
import scipy.sparse.linalg as sla
from routing.routing_base import RoutingBase

class SpectralGapRouting(RoutingBase):
    """Spectral Gap Routing Strategy"""
    
    def __init__(self, topology):
        """Initialize Spectral Gap Routing"""
        self.routes = {}  # Store computed routes
        self.num_nodes = len(topology.graph.nodes())
        self.link_loads = {}  # Track link utilization
        self.spectral_gap_cache = None
        self.eigenvector_cache = None
        self.laplacian_cache = None
        self.node_index_map = {node: idx for idx, node in enumerate(topology.graph.nodes())}
        self.index_node_map = {idx: node for node, idx in self.node_index_map.items()}
        super().__init__(topology)
        self._initialize_spectral_cache()
    
    def precompute_paths(self):
        """Precompute paths using spectral gap awareness"""
        print("Precomputing spectral gap aware paths...")
        self.compute_spectral_gap_aware_paths()
        
        # Store a default path for each node pair in self.paths
        for (source, target), paths in self.routes.items():
            if paths:
                self.paths[(source, target)] = paths[0]
    
    def _initialize_spectral_cache(self):
        """Initialize spectral computation cache"""
        # Create initial Laplacian matrix and cache it
        undirected_graph = self.graph.to_undirected()
        
        # Ensure we have a mapping between node IDs and matrix indices
        nodes = list(undirected_graph.nodes())
        self.node_index_map = {node: idx for idx, node in enumerate(nodes)}
        self.index_node_map = {idx: node for node, idx in self.node_index_map.items()}
        
        self.laplacian_cache = nx.normalized_laplacian_matrix(undirected_graph, nodelist=nodes).astype(np.float64)
        
        # Precompute and cache initial spectral gap and eigenvectors
        try:
            eigenvalues, eigenvectors = sla.eigsh(self.laplacian_cache, k=2, which='SM', return_eigenvectors=True)
            self.spectral_gap_cache = eigenvalues[1]  # Second smallest eigenvalue
            self.eigenvector_cache = eigenvectors[:, 1]  # Corresponding eigenvector
        except Exception as e:
            print(f"Warning: Failed to compute exact spectral gap: {e}")
            # If sparse solver fails, use approximation method
            self.spectral_gap_cache, self.eigenvector_cache = self._approximate_spectral_gap(self.laplacian_cache)
        
        self.last_modified_edges = set()
    
    def _approximate_spectral_gap(self, laplacian, max_iter=20, tol=1e-4):
        """Approximate spectral gap using power iteration method"""
        n = laplacian.shape[0]
        
        # Initialize random vector
        v = np.random.rand(n)
        # Ensure orthogonality to constant vector (corresponding to smallest eigenvalue 0)
        v = v - np.mean(v)
        v = v / np.linalg.norm(v)
        
        # Power iteration
        lambda_est = 0
        for _ in range(max_iter):
            # Matrix-vector multiplication
            if sp.issparse(laplacian):
                w = laplacian.dot(v)
            else:
                w = np.dot(laplacian, v)
            
            # Ensure orthogonality to constant vector
            w = w - np.mean(w)
            
            # Calculate Rayleigh quotient
            lambda_new = np.dot(w, v) / np.dot(v, v)
            
            # Normalize
            norm_w = np.linalg.norm(w)
            if norm_w < 1e-10:  # Avoid division by zero
                break
            v = w / norm_w
            
            # Check convergence
            if abs(lambda_new - lambda_est) < tol:
                break
                
            lambda_est = lambda_new
            
        return lambda_est, v
    
    def calculate_spectral_gap(self, edge_changes=None):
        """Calculate or approximate the spectral gap of the current network topology"""
        if self.graph is None:
            return 0
        
        # If no edge changes or cache not initialized, use cached value
        if edge_changes is None and self.spectral_gap_cache is not None:
            return self.spectral_gap_cache
        
        # If few edge changes, use incremental update
        if edge_changes and len(edge_changes) <= 5 and self.eigenvector_cache is not None:
            return self._incremental_spectral_gap_update(edge_changes)
        
        # For large networks, use approximation algorithm
        if self.num_nodes > 100:
            return self._fast_approximate_spectral_gap()
        
        # For small networks, use exact computation
        try:
            undirected_graph = self.graph.to_undirected()
            nodes = list(undirected_graph.nodes())
            self.node_index_map = {node: idx for idx, node in enumerate(nodes)}
            self.index_node_map = {idx: node for node, idx in self.node_index_map.items()}
            
            laplacian = nx.normalized_laplacian_matrix(undirected_graph, nodelist=nodes)
            eigenvalues = sla.eigsh(laplacian, k=2, which='SM', return_eigenvectors=False)
            self.spectral_gap_cache = eigenvalues[1]
            return self.spectral_gap_cache
        except:
            # If exact computation fails, fall back to approximation
            return self._fast_approximate_spectral_gap()
    
    def _incremental_spectral_gap_update(self, edge_changes):
        """Incremental spectral gap update based on matrix perturbation theory"""
        if self.eigenvector_cache is None:
            # If eigenvector cache is not available, recalculate spectral gap
            return self._fast_approximate_spectral_gap()
            
        delta_lambda = 0
        v = self.eigenvector_cache
        
        for u, w, old_weight, new_weight in edge_changes:
            # Convert node IDs to matrix indices
            u_idx = self.node_index_map.get(u)
            w_idx = self.node_index_map.get(w)
            
            # Skip if we can't find indices
            if u_idx is None or w_idx is None:
                continue
                
            # Calculate change in Laplacian matrix elements
            delta = new_weight - old_weight
            delta_lambda += delta * (v[u_idx] - v[w_idx])**2
        
        # Update cached spectral gap
        new_gap = self.spectral_gap_cache + delta_lambda
        self.spectral_gap_cache = max(0.001, new_gap)  # Ensure positive gap
        return self.spectral_gap_cache
    
    def _fast_approximate_spectral_gap(self):
        """Fast approximate spectral gap calculation"""
        # Use sampling for large networks
        if self.num_nodes > 100:
            return self._sampled_spectral_gap()
        
        # Use power iteration method
        undirected_graph = self.graph.to_undirected()
        nodes = list(undirected_graph.nodes())
        self.node_index_map = {node: idx for idx, node in enumerate(nodes)}
        self.index_node_map = {idx: node for node, idx in self.node_index_map.items()}
        
        laplacian = nx.normalized_laplacian_matrix(undirected_graph, nodelist=nodes)
        
        gap, vec = self._approximate_spectral_gap(laplacian)
        
        # Update cache
        self.laplacian_cache = laplacian
        self.spectral_gap_cache = gap
        self.eigenvector_cache = vec
        
        return gap
    
    def _sampled_spectral_gap(self):
        """Approximate spectral gap through subgraph sampling"""
        # Select sample size
        sample_size = min(100, self.num_nodes // 2)
        
        # Randomly select nodes
        nodes = list(self.graph.nodes())
        sampled_nodes = random.sample(nodes, sample_size)
        
        # Create subgraph
        subgraph = self.graph.subgraph(sampled_nodes).to_undirected()
        
        # Calculate spectral gap of subgraph
        if len(subgraph) > 1:  # Ensure subgraph has enough nodes
            laplacian = nx.normalized_laplacian_matrix(subgraph)
            gap, _ = self._approximate_spectral_gap(laplacian)
            
            # Use heuristic to adjust sampling result
            # Subgraph spectral gap is typically larger than original graph
            adjustment_factor = 0.85
            return gap * adjustment_factor
        else:
            # If sampling fails, return cached value or default
            return self.spectral_gap_cache if self.spectral_gap_cache is not None else 0.1
    
    def compute_spectral_gap_aware_paths(self):
        """Compute spectral gap aware routing paths"""
        self.routes = {}
        
        # Calculate initial spectral gap as baseline
        initial_spectral_gap = self.calculate_spectral_gap()
        print(f"Initial network spectral gap: {initial_spectral_gap:.6f}")
        
        # Compute routing table for each source-destination pair
        nodes = list(self.graph.nodes())
        for source in nodes:
            # Calculate candidate paths from source to all destinations
            paths_by_destination = {}
            
            # Use custom path finding for all destinations
            for target in nodes:
                if source == target:
                    continue
                
                # Find k shortest paths using custom implementation
                cutoff = min(8, self.num_nodes//2)
                max_paths = 3
                all_paths = self._find_k_shortest_paths(source, target, max_paths, cutoff)
                paths_by_destination[target] = all_paths
            
            # Evaluate paths for each destination
            for target, candidate_paths in paths_by_destination.items():
                if not candidate_paths:
                    self.routes[(source, target)] = []
                    continue
                
                # Evaluate each path
                path_scores = []
                for path in candidate_paths:
                    # Convert to edge path
                    edge_path = [(path[i], path[i+1]) for i in range(len(path)-1)]
                    
                    # Calculate inverse of path length (shorter is better)
                    path_length_inv = 1.0 / len(edge_path)
                    
                    # Calculate spectral health
                    try:
                        spectral_health = self._compute_spectral_health(edge_path)
                    except Exception as e:
                        print(f"Warning: Failed to compute spectral health: {e}")
                        spectral_health = 0
                    
                    # Calculate composite score
                    alpha = 0.6  # Path length weight
                    beta = 0.4   # Spectral health weight
                    score = alpha * path_length_inv + beta * spectral_health
                    
                    path_scores.append((score, path))
                
                # Select k paths with highest scores
                k = min(3, len(path_scores))  # Number of paths to keep
                if k > 0:
                    best_paths = heapq.nlargest(k, path_scores, key=lambda x: x[0])
                    self.routes[(source, target)] = [path for _, path in best_paths]
                else:
                    self.routes[(source, target)] = []
        
        print(f"Spectral gap aware routing completed, computed routes for {len(self.routes)} node pairs")

    def _find_k_shortest_paths(self, source, target, k=3, cutoff=8):
        """
        Find k shortest paths from source to target
        
        Args:
            source: Source node
            target: Target node
            k: Maximum number of paths to find
            cutoff: Maximum path length
            
        Returns:
            List of paths (each path is a list of nodes)
        """
        # 首先尝试找最短路径
        try:
            shortest_path = nx.shortest_path(self.graph, source, target)
            if len(shortest_path) > cutoff:
                return [shortest_path]  # 如果最短路径已超过cutoff，只返回这一条
        except:
            return []  # 如果没有路径，返回空列表
        
        # 使用BFS找到多条路径
        paths = []
        queue = [(source, [source])]
        visited_edges = set()  # 记录已访问的边，而不是节点
        
        while queue and len(paths) < k:
            current, path = queue.pop(0)
            
            # 如果路径长度已达到cutoff，不再扩展
            if len(path) > cutoff:
                continue
            
            # 如果到达目标节点，添加到路径列表
            if current == target and path not in paths:
                paths.append(path)
                continue
            
            # 遍历邻居节点
            neighbors = list(self.graph.neighbors(current))
            # 随机打乱邻居顺序，增加路径多样性
            random.shuffle(neighbors)
            
            for neighbor in neighbors:
                edge = (current, neighbor)
                # 避免环路和重复访问同一条边
                if neighbor not in path and edge not in visited_edges:
                    visited_edges.add(edge)
                    queue.append((neighbor, path + [neighbor]))
        
        # 如果没有找到足够的路径，尝试使用Yen算法找k条最短路径
        if len(paths) < k:
            try:
                # 导入k最短路径算法
                from networkx.algorithms.simple_paths import shortest_simple_paths
                path_generator = shortest_simple_paths(self.graph, source, target)
                
                # 获取前k条路径
                for i, path in enumerate(path_generator):
                    if i >= k or len(path) > cutoff:
                        break
                    if path not in paths:
                        paths.append(path)
            except:
                # 如果算法失败，至少确保有一条最短路径
                if not paths and 'shortest_path' in locals():
                    paths.append(shortest_path)
        
        # 确保路径按长度排序
        paths.sort(key=len)
        
        # 如果还是没有找到路径，尝试使用启发式方法
        if not paths:
            try:
                # 使用A*算法找一条路径
                path = nx.astar_path(self.graph, source, target)
                if len(path) <= cutoff:
                    paths.append(path)
            except:
                pass
        
        return paths[:k]  # 返回至多k条路径

    def _compute_spectral_health(self, edge_path):
        """
        Calculate the spectral health of a path
        
        Args:
            edge_path: Path represented as a list of edges
            
        Returns:
            Spectral health S(p)
        """
        if not edge_path:
            return 0
            
        # Calculate original spectral gap
        original_gap = self.calculate_spectral_gap()
        
        # Simulate situation after allocating traffic to the path
        edge_changes = []
        for u, v in edge_path:
            # Get current edge weight
            if self.graph.has_edge(u, v):
                old_weight = self.graph[u][v].get('weight', 1.0)
                # Simulate weight decrease due to increased load
                utilization = self.link_loads.get((u, v), 0) / self.graph[u][v].get('bandwidth', 1.0)
                alpha = 0.2  # Load impact factor on weight
                new_weight = old_weight * (1 - alpha * (utilization + 0.1))  # Assume 10% utilization increase
                edge_changes.append((u, v, old_weight, new_weight))
        
        # Calculate new spectral gap using incremental update
        try:
            new_gap = self._incremental_spectral_gap_update(edge_changes)
        except Exception as e:
            print(f"Warning: Failed to update spectral gap: {e}")
            new_gap = original_gap * 0.9  # Fallback approximation
        
        # Calculate spectral health (original gap / new gap)
        if new_gap <= 0.001:  # Avoid very small denominators
            return 0
        
        spectral_health = original_gap / new_gap
        return spectral_health
    
    def get_next_hop(self, current, destination, packet=None):
        """
        获取下一跳节点，使用谱间隙路由，但在目的地近在咫尺时优先考虑直接路径
        
        参数:
            current: 当前节点
            destination: 目标节点
            packet: 数据包对象（可选）
            
        返回:
            下一跳节点ID
        """
        if current == destination:
            return None
        
        # 检查是否可以直接到达目的地
        if self.graph.has_edge(current, destination):
            return destination
        
        # 检查是否距离目的地只有两跳
        common_neighbors = list(nx.common_neighbors(self.graph, current, destination))
        if common_neighbors:
            # 如果有共同邻居，选择其中一个作为下一跳
            return random.choice(common_neighbors)
        
        # 获取可用路径
        paths = self.routes.get((current, destination), [])
        
        if not paths:
            # 如果没有预计算的路径，尝试临时计算
            try:
                path = nx.shortest_path(self.graph, current, destination)
                if len(path) > 1:
                    return path[1]
            except:
                return None
            return None
        
        # 检查是否有非常短的路径（比如3跳以内）
        short_paths = [p for p in paths if len(p) <= 3]
        if short_paths:
            # 如果有短路径，优先使用短路径
            selected_path = random.choice(short_paths)
            if len(selected_path) > 1:
                return selected_path[1]
        
        # 基于数据包哈希选择路径（如果可用）
        if packet and hasattr(packet, 'flow_id'):
            path_idx = hash(packet.flow_id) % len(paths)
        else:
            path_idx = random.randint(0, len(paths)-1)
        
        selected_path = paths[path_idx]
        
        # 返回下一跳
        if len(selected_path) > 1:
            return selected_path[1]
        
        return None
