#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
BCube拓扑生成器
"""

import networkx as nx
import random
import math

from topology.topology_base import TopologyBase

class BCubeTopology(TopologyBase):
    """BCube拓扑"""
    
    def __init__(self, n, k):
        """
        初始化BCube拓扑
        
        参数:
            n: 每个交换机连接的服务器数量
            k: BCube的级别，BCube_k由多个BCube_{k-1}构建
        """
        super().__init__()
        self.n = n  # 每个交换机连接的服务器数量
        self.k = k  # BCube级别
        
        # 计算总服务器数
        self.num_servers = n ** (k + 1)
        
        # 设置规模名称
        if self.num_servers <= 64:
            self.scale = 'small'
        elif self.num_servers <= 512:
            self.scale = 'medium'
        else:
            self.scale = 'large'
            
        # 生成拓扑
        self.generate()
        
    def generate(self):
        """生成BCube拓扑"""
        print(f"生成BCube拓扑 (n={self.n}, k={self.k})...")
        
        self.graph = nx.Graph()
        
        # 添加服务器节点
        for i in range(self.num_servers):
            # 计算服务器的BCube坐标
            coords = self._get_server_coords(i)
            
            # 计算节点位置以便可视化
            x = 0
            y = 0
            for level, coord in enumerate(coords):
                x += coord * math.cos(2 * math.pi * level / (self.k + 1)) * (self.k + 2 - level)
                y += coord * math.sin(2 * math.pi * level / (self.k + 1)) * (self.k + 2 - level)
            
            self.graph.add_node(i, 
                               type='server', 
                               coords=coords,
                               pos=(x, y))
        
        # 添加交换机节点和连接
        switch_id = self.num_servers
        
        # 对每个级别k
        for level in range(self.k + 1):
            # 计算该级别的交换机数量
            num_switches_at_level = self.n ** self.k
            
            # 对每个交换机
            for i in range(num_switches_at_level):
                # 计算交换机的位置
                switch_coords = self._get_switch_coords(i, level)
                
                # 计算节点位置以便可视化
                x = 0
                y = 0
                for l, coord in enumerate(switch_coords):
                    if l != level:
                        x += coord * math.cos(2 * math.pi * l / (self.k + 1)) * (self.k + 2)
                        y += coord * math.sin(2 * math.pi * l / (self.k + 1)) * (self.k + 2)
                # 添加额外偏移以区分交换机和服务器
                x += (self.k + 3) * math.cos(2 * math.pi * level / (self.k + 1))
                y += (self.k + 3) * math.sin(2 * math.pi * level / (self.k + 1))
                
                self.graph.add_node(switch_id, 
                                   type='switch', 
                                   level=level,
                                   coords=switch_coords,
                                   pos=(x, y))
                
                # 连接到对应的服务器
                for j in range(self.n):
                    # 计算服务器坐标
                    server_coords = list(switch_coords)
                    server_coords[level] = j
                    
                    # 找到对应的服务器ID
                    server_id = self._get_server_id(server_coords)
                    
                    # 添加连接
                    self.graph.add_edge(switch_id, server_id)
                
                switch_id += 1
        
        # 设置链路属性
        self._set_link_properties()
        
        print(f"BCube拓扑生成完成，节点数: {self.graph.number_of_nodes()}, 边数: {self.graph.number_of_edges()}")
    
    def _get_server_coords(self, server_id):
        """将服务器ID转换为BCube坐标"""
        coords = []
        temp_id = server_id
        for _ in range(self.k + 1):
            coords.append(temp_id % self.n)
            temp_id //= self.n
        return coords
    
    def _get_server_id(self, coords):
        """将BCube坐标转换为服务器ID"""
        server_id = 0
        for i in range(self.k + 1):
            server_id += coords[i] * (self.n ** i)
        return server_id
    
    def _get_switch_coords(self, switch_idx, level):
        """计算交换机的坐标（除了level位置）"""
        coords = []
        temp_idx = switch_idx
        for i in range(self.k + 1):
            if i == level:
                coords.append(-1)  # 标记该位置为交换机级别
            else:
                digit = temp_idx % self.n
                coords.append(digit)
                temp_idx //= self.n
        return coords
    
    def _set_link_properties(self):
        """设置链路属性"""
        for u, v in self.graph.edges():
            # 获取节点类型
            u_type = self.graph.nodes[u].get('type', '')
            v_type = self.graph.nodes[v].get('type', '')
            
            # 服务器到交换机的链路
            if (u_type == 'server' and v_type == 'switch') or \
               (v_type == 'server' and u_type == 'switch'):
                # 获取交换机级别
                switch_node = u if u_type == 'switch' else v
                level = self.graph.nodes[switch_node].get('level', 0)
                
                # 根据级别设置不同的链路属性
                # 较低级别的交换机具有更高的带宽和更低的延迟
                capacity = 40.0 / (level + 1)  # 带宽随级别降低
                delay = 0.01 * (level + 1)     # 延迟随级别增加
                buffer_size = 2048 // (level + 1)  # 缓冲区随级别降低
            else:
                # 默认链路属性
                capacity = 10.0
                delay = 0.05
                buffer_size = 512
            
            # 添加一些随机变化
            capacity *= (0.9 + 0.2 * random.random())
            delay *= (0.9 + 0.2 * random.random())
            buffer_size = int(buffer_size * (0.9 + 0.2 * random.random()))
            
            self.link_capacity[(u, v)] = capacity
            self.link_delay[(u, v)] = delay
            self.link_buffer[(u, v)] = buffer_size
