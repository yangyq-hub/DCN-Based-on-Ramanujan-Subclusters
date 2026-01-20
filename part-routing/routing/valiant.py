#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Valiant负载均衡路由策略
"""

import networkx as nx
import random
from routing.routing_base import RoutingBase

class ValiantRouting(RoutingBase):
    """Valiant负载均衡路由策略"""
    
    def __init__(self, topology):
        """初始化Valiant路由"""
        super().__init__(topology)
        self.intermediate_nodes = {}  # 存储中间节点
    
    def precompute_paths(self):
        """预计算所有节点对之间的最短路径"""
        print("预计算Valiant路由路径...")
        # 计算所有节点对之间的最短路径
        shortest_paths = nx.all_pairs_shortest_path(self.graph)
        
        # 存储所有路径
        for source, targets in shortest_paths:
            for target, path in targets.items():
                self.paths[(source, target)] = path
    
    def _select_intermediate_node(self, source, destination, packet=None):
        """
        为Valiant路由选择中间节点
        
        参数:
            source: 源节点
            destination: 目标节点
            packet: 数据包对象（可选）
            
        返回:
            中间节点ID
        """
        # 如果已经为这个流选择了中间节点，则继续使用
        if packet and packet.flow_id in self.intermediate_nodes:
            return self.intermediate_nodes[packet.flow_id]
        
        # 随机选择一个不是源或目的的节点作为中间节点
        nodes = list(self.graph.nodes())
        candidates = [n for n in nodes if n != source and n != destination]
        
        if not candidates:
            return None
        
        intermediate = random.choice(candidates)
        
        # 如果有数据包，存储这个流的中间节点
        if packet:
            self.intermediate_nodes[packet.flow_id] = intermediate
        
        return intermediate
    
    def get_next_hop(self, current, destination, packet=None):
        """
        获取下一跳节点，使用Valiant路由
        
        参数:
            current: 当前节点
            destination: 目标节点
            packet: 数据包对象（可选）
            
        返回:
            下一跳节点ID
        """
        if current == destination:
            return None
        
        # 如果数据包没有中间节点属性，为其选择一个
        if packet and not hasattr(packet, 'valiant_node'):
            packet.valiant_node = self._select_intermediate_node(packet.source, packet.destination, packet)
            packet.valiant_phase = 1  # 第1阶段：前往中间节点
        
        # 决定路由目标
        if packet and hasattr(packet, 'valiant_phase') and packet.valiant_phase == 1:
            # 第1阶段：路由到中间节点
            if current == packet.valiant_node:
                # 到达中间节点，切换到第2阶段
                packet.valiant_phase = 2
                target = destination
            else:
                target = packet.valiant_node
        else:
            # 第2阶段或没有使用Valiant：直接路由到目的地
            target = destination
        
        # 获取到目标的下一跳
        path = self.paths.get((current, target))
        
        if path and len(path) > 1:
            return path[1]
        
        # 如果没有预计算的路径，使用临时计算
        try:
            path = nx.shortest_path(self.graph, current, target)
            if len(path) > 1:
                return path[1]
        except:
            pass
        
        # 如果仍然找不到路径，返回None
        return None
