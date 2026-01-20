#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
拓扑基类，定义了所有拓扑必须实现的接口
"""

import networkx as nx
import numpy as np
from abc import ABC, abstractmethod

class TopologyBase(ABC):
    """网络拓扑基类"""
    
    def __init__(self):
        self.graph = None
        self.scale = None
        self.link_capacity = {}  # 链路容量 (Gbps)
        self.link_delay = {}     # 链路延迟 (ms)
        self.link_buffer = {}    # 链路缓冲区大小 (KB)
        
    @abstractmethod
    def generate(self):
        """生成拓扑"""
        pass
    
    def get_graph(self):
        """获取拓扑图"""
        return self.graph
    
    def get_nodes(self):
        """获取所有节点"""
        return self.graph.nodes()
    
    def get_edges(self):
        """获取所有边"""
        return self.graph.edges()
    
    def get_neighbors(self, node):
        """获取节点的邻居"""
        return list(self.graph.neighbors(node))
    
    def get_link_capacity(self, u, v):
        """获取链路容量 (Gbps)"""
        return self.link_capacity.get((u, v)) or self.link_capacity.get((v, u), 10.0)  # 默认10Gbps
    
    def get_link_delay(self, u, v):
        """获取链路延迟 (ms)"""
        return self.link_delay.get((u, v)) or self.link_delay.get((v, u), 0.01)  # 默认0.01ms
    
    def get_link_buffer(self, u, v):
        """获取链路缓冲区大小 (KB)"""
        return self.link_buffer.get((u, v)) or self.link_buffer.get((v, u), 1024)  # 默认1MB
    
    def get_scale_name(self):
        """获取拓扑规模名称"""
        return self.scale
    
    def compute_shortest_paths(self):
        """计算所有节点对之间的最短路径"""
        return dict(nx.all_pairs_shortest_path(self.graph))
    
    def compute_bisection_bandwidth(self, num_trials=10):
        """估计图的二分带宽"""
        best_cut_size = float('inf')
        n = self.graph.number_of_nodes()
        
        for _ in range(num_trials):
            # 随机初始分区
            partition = [0] * n
            for i in range(n//2):
                partition[i] = 1
            
            import random
            random.shuffle(partition)
            
            # 使用networkx的kernighan_lin_bisection
            try:
                sets = nx.algorithms.community.kernighan_lin_bisection(self.graph, partition)
                cut_size = nx.cut_size(self.graph, sets[0], sets[1])
                best_cut_size = min(best_cut_size, cut_size)
            except:
                continue
                
        return best_cut_size
    
    def compute_diameter(self):
        """计算图的直径"""
        return nx.diameter(self.graph)
    
    def compute_average_path_length(self):
        """计算平均路径长度"""
        return nx.average_shortest_path_length(self.graph)
