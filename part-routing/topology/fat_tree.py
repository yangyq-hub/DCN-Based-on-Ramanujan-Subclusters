#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fat-Tree拓扑生成器
"""

import networkx as nx
import random

from topology.topology_base import TopologyBase

class FatTreeTopology(TopologyBase):
    """Fat-Tree拓扑"""
    
    def __init__(self, k):
        """
        初始化Fat-Tree拓扑
        
        参数:
            k: Fat-Tree的k参数，必须是偶数
        """
        super().__init__()
        self.k = k
        
        # 检查k是否为偶数
        if k % 2 != 0:
            raise ValueError("k必须是偶数")
        
        # 设置规模名称
        if k <= 8:
            self.scale = 'small'
        elif k <= 12:
            self.scale = 'medium'
        else:
            self.scale = 'large'
            
        # 生成拓扑
        self.generate()
        
    def generate(self):
        """生成k-ary Fat-Tree拓扑"""
        print(f"生成{self.k}-ary Fat-Tree拓扑...")
        
        self.graph = nx.Graph()
        
        # 计算节点数量
        num_pods = self.k
        num_core = (self.k//2)**2
        num_agg = (self.k//2) * self.k
        num_edge = (self.k//2) * self.k
        
        # 添加节点
        # 核心交换机
        for i in range(num_core):
            self.graph.add_node(i, layer='core', pos=(i, 3))
        
        # 汇聚层交换机
        for i in range(num_agg):
            self.graph.add_node(num_core + i, layer='aggregation', 
                          pos=(i % (self.k//2) + (i//(self.k//2))*(self.k+1), 2))
        
        # 边缘层交换机
        for i in range(num_edge):
            self.graph.add_node(num_core + num_agg + i, layer='edge', 
                          pos=(i % (self.k//2) + (i//(self.k//2))*(self.k+1), 1))
        
        # 添加连接
        # 连接核心层和汇聚层
        for p in range(num_pods):
            for i in range(self.k//2):  # 每个pod中的汇聚交换机
                agg_sw = num_core + p*(self.k//2) + i
                for j in range(self.k//2):  # 连接到核心交换机
                    core_sw = i*(self.k//2) + j
                    self.graph.add_edge(core_sw, agg_sw)
        
        # 连接汇聚层和边缘层
        for p in range(num_pods):
            for i in range(self.k//2):  # 每个pod中的汇聚交换机
                agg_sw = num_core + p*(self.k//2) + i
                for j in range(self.k//2):  # 连接到边缘交换机
                    edge_sw = num_core + num_agg + p*(self.k//2) + j
                    self.graph.add_edge(agg_sw, edge_sw)
        
        # 设置链路属性
        self._set_link_properties()
        
        print(f"Fat-Tree拓扑生成完成，节点数: {self.graph.number_of_nodes()}, 边数: {self.graph.number_of_edges()}")
    
    def _set_link_properties(self):
        """设置链路属性"""
        for u, v in self.graph.edges():
            # 根据层级设置不同的链路容量
            u_layer = self.graph.nodes[u].get('layer', '')
            v_layer = self.graph.nodes[v].get('layer', '')
            
            # 核心到汇聚层的链路容量较高
            if (u_layer == 'core' and v_layer == 'aggregation') or \
               (v_layer == 'core' and u_layer == 'aggregation'):
                capacity = 40.0  # 40Gbps
                delay = 0.01     # 0.01ms
                buffer_size = 2048  # 2MB
            # 汇聚到边缘层的链路容量中等
            elif (u_layer == 'aggregation' and v_layer == 'edge') or \
                 (v_layer == 'aggregation' and u_layer == 'edge'):
                capacity = 20.0  # 20Gbps
                delay = 0.02     # 0.02ms
                buffer_size = 1024  # 1MB
            # 其他链路
            else:
                capacity = 10.0  # 10Gbps
                delay = 0.05     # 0.05ms
                buffer_size = 512   # 512KB
            
            # 添加一些随机变化
            capacity *= (0.9 + 0.2 * random.random())
            delay *= (0.9 + 0.2 * random.random())
            buffer_size = int(buffer_size * (0.9 + 0.2 * random.random()))
            
            self.link_capacity[(u, v)] = capacity
            self.link_delay[(u, v)] = delay
            self.link_buffer[(u, v)] = buffer_size
