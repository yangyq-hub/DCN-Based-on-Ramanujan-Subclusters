#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Jellyfish拓扑生成器
"""

import networkx as nx
import random

from topology.topology_base import TopologyBase

class JellyfishTopology(TopologyBase):
    """Jellyfish拓扑"""
    
    def __init__(self, n, k, r):
        """
        初始化Jellyfish拓扑
        
        参数:
            n: 交换机数量
            k: 每个交换机的端口数
            r: 每个交换机连接到其他交换机的端口数 (r < k)
        """
        super().__init__()
        self.n = n  # 交换机数量
        self.k = k  # 每个交换机的端口数
        self.r = r  # 每个交换机连接到其他交换机的端口数
        
        if r >= k:
            raise ValueError("r必须小于k")
        
        # 设置规模名称
        if n <= 64:
            self.scale = 'small'
        elif n <= 128:
            self.scale = 'medium'
        else:
            self.scale = 'large'
            
        # 生成拓扑
        self.generate()
        
    def generate(self):
        """生成Jellyfish拓扑"""
        print(f"生成Jellyfish拓扑 (n={self.n}, k={self.k}, r={self.r})...")
        
        # 创建图
        self.graph = nx.Graph()
        
        # 添加节点
        for i in range(self.n):
            self.graph.add_node(i)
        
        # 随机连接
        self._random_regular_graph()
        
        # 设置链路属性
        self._set_link_properties()
        
        print(f"Jellyfish拓扑生成完成，节点数: {self.graph.number_of_nodes()}, 边数: {self.graph.number_of_edges()}")
        
        # 确保图是连通的
        if not nx.is_connected(self.graph):
            print("警告: 生成的Jellyfish图不是连通的，重新生成...")
            self.generate()
    
    def _random_regular_graph(self):
        """生成随机正则图作为Jellyfish拓扑"""
        # 使用NetworkX的随机正则图生成器
        temp_graph = nx.random_regular_graph(self.r, self.n)
        
        # 复制边到我们的图中
        self.graph.add_edges_from(temp_graph.edges())
        
        # 确保图是连通的
        if not nx.is_connected(self.graph):
            # 如果不连通，重新生成
            self.graph.clear_edges()
            self._random_regular_graph()
    
    def _set_link_properties(self):
        """设置链路属性"""
        for u, v in self.graph.edges():
            # Jellyfish中所有链路容量相同，但添加一些随机变化
            capacity = 17  # 10-20Gbps
            delay = 0.03 + random.random() * 0.05     # 0.01-0.05ms
            buffer_size = 512 + random.randint(0, 512)  # 512-1024KB
            
            self.link_capacity[(u, v)] = capacity
            self.link_delay[(u, v)] = delay
            self.link_buffer[(u, v)] = buffer_size
