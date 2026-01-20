#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dragonfly拓扑生成器
"""

import networkx as nx
import random
import math

from topology.topology_base import TopologyBase

class DragonflyTopology(TopologyBase):
    """Dragonfly拓扑"""
    
    def __init__(self, p, a, h):
        """
        初始化Dragonfly拓扑
        
        参数:
            p: 每个组内的路由器数量
            a: 每个路由器连接到其他组的链路数量
            h: 每个路由器连接的终端节点数量
        """
        super().__init__()
        self.p = p  # 每组路由器数量
        self.a = a  # 每个路由器的全局链路数
        self.h = h  # 每个路由器连接的终端数
        
        # 计算组数 g
        self.g = self.a * self.p + 1
        
        # 设置规模名称
        total_routers = self.p * self.g
        if total_routers <= 100:
            self.scale = 'small'
        elif total_routers <= 500:
            self.scale = 'medium'
        else:
            self.scale = 'large'
            
        # 生成拓扑
        self.generate()
        
    def generate(self):
        """生成Dragonfly拓扑"""
        print(f"生成Dragonfly拓扑 (p={self.p}, a={self.a}, g={self.g}, h={self.h})...")
        
        self.graph = nx.Graph()
        
        # 添加路由器节点
        router_id = 0
        for group in range(self.g):
            for i in range(self.p):
                # 计算节点位置以便可视化
                angle = 2 * math.pi * group / self.g
                radius = 10
                x = radius * math.cos(angle) + (i - self.p/2) * math.cos(angle + math.pi/2)
                y = radius * math.sin(angle) + (i - self.p/2) * math.sin(angle + math.pi/2)
                
                self.graph.add_node(router_id, 
                                   type='router', 
                                   group=group, 
                                   pos=(x, y))
                router_id += 1
        
        # 添加组内连接 (完全图)
        for group in range(self.g):
            group_routers = [n for n, attr in self.graph.nodes(data=True) 
                            if attr.get('type') == 'router' and attr.get('group') == group]
            
            # 在每个组内创建完全图
            for i in range(len(group_routers)):
                for j in range(i+1, len(group_routers)):
                    self.graph.add_edge(group_routers[i], group_routers[j], link_type='local')
        
        # 添加组间连接
        # 使用确定性算法为每个路由器分配全局链路
        for src_group in range(self.g):
            src_routers = [n for n, attr in self.graph.nodes(data=True) 
                          if attr.get('type') == 'router' and attr.get('group') == src_group]
            
            for i, src_router in enumerate(src_routers):
                for j in range(self.a):
                    # 计算目标组 (确保均匀分布)
                    dst_group = (src_group + 1 + (i * self.a + j)) % self.g
                    if dst_group == src_group:
                        dst_group = (dst_group + 1) % self.g
                    
                    # 选择目标组中的路由器
                    dst_routers = [n for n, attr in self.graph.nodes(data=True) 
                                  if attr.get('type') == 'router' and attr.get('group') == dst_group]
                    
                    # 计算目标路由器索引
                    dst_router_idx = (src_group + i + j) % len(dst_routers)
                    dst_router = dst_routers[dst_router_idx]
                    
                    # 添加全局链路
                    if not self.graph.has_edge(src_router, dst_router):
                        self.graph.add_edge(src_router, dst_router, link_type='global')
        
        # 设置链路属性
        self._set_link_properties()
        
        print(f"Dragonfly拓扑生成完成，节点数: {self.graph.number_of_nodes()}, 边数: {self.graph.number_of_edges()}")
    
    def _set_link_properties(self):
        """设置链路属性"""
        for u, v in self.graph.edges():
            link_type = self.graph.edges[u, v].get('link_type', '')
            
            # 全局链路具有较高的延迟但容量较大
            if link_type == 'global':
                capacity = 40.0  # 100Gbps
                delay = 0.05      # 0.05ms
                buffer_size = 4096  # 4MB
            # 局部链路延迟低
            elif link_type == 'local':
                capacity = 20.0   # 50Gbps
                delay = 0.01      # 0.01ms
                buffer_size = 2048  # 2MB
            # 默认链路
            else:
                capacity = 10.0   # 25Gbps
                delay = 0.02      # 0.02ms
                buffer_size = 1024  # 1MB
            
            # 添加一些随机变化
            capacity *= (0.9 + 0.2 * random.random())
            delay *= (0.9 + 0.2 * random.random())
            buffer_size = int(buffer_size * (0.9 + 0.2 * random.random()))
            
            self.link_capacity[(u, v)] = capacity
            self.link_delay[(u, v)] = delay
            self.link_buffer[(u, v)] = buffer_size
