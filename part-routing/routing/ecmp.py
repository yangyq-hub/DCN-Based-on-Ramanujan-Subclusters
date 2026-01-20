#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
等价多路径(ECMP)路由策略
"""

import networkx as nx
import random
import hashlib
from routing.routing_base import RoutingBase

class ECMPRouting(RoutingBase):
    """等价多路径(ECMP)路由策略"""
    
    def __init__(self, topology):
        """初始化ECMP路由"""
        self.equal_paths = {}  # 存储等价路径
        super().__init__(topology)
    
    def precompute_paths(self):
        """预计算所有节点对之间的等价最短路径"""
        print("预计算等价多路径...")
        nodes = list(self.graph.nodes())
        
        for source in nodes:
            for target in nodes:
                if source == target:
                    continue
                    
                # 获取所有最短路径
                try:
                    all_shortest_paths = list(nx.all_shortest_paths(self.graph, source, target))
                    
                    # 存储所有等价路径
                    self.equal_paths[(source, target)] = all_shortest_paths
                    
                    # 存储一个默认路径
                    if all_shortest_paths:
                        self.paths[(source, target)] = all_shortest_paths[0]
                except:
                    # 如果找不到路径，设置为空列表
                    self.equal_paths[(source, target)] = []
    
    def _flow_hash(self, packet):
        """
        计算流哈希值，用于ECMP路由决策
        
        参数:
            packet: 数据包对象
            
        返回:
            哈希值
        """
        if packet is None:
            return random.randint(0, 1000000)
        
        # 使用五元组计算哈希
        flow_id = f"{packet.source}:{packet.source_port}-{packet.destination}:{packet.destination_port}-{packet.protocol}"
        return int(hashlib.md5(flow_id.encode()).hexdigest(), 16)
    
    def get_next_hop(self, current, destination, packet=None):
        """
        获取下一跳节点，使用ECMP在等价路径间负载均衡
        
        参数:
            current: 当前节点
            destination: 目标节点
            packet: 数据包对象（可选）
            
        返回:
            下一跳节点ID
        """
        if current == destination:
            return None
        
        # 获取所有等价路径
        paths = self.equal_paths.get((current, destination), [])
        
        if not paths:
            # 如果没有预计算的路径，尝试临时计算
            try:
                paths = list(nx.all_shortest_paths(self.graph, current, destination))
            except:
                return None
        
        if not paths:
            return None
        
        # 使用流哈希选择路径
        hash_value = self._flow_hash(packet)
        selected_path = paths[hash_value % len(paths)]
        
        # 返回下一跳
        if len(selected_path) > 1:
            return selected_path[1]
        
        return None
