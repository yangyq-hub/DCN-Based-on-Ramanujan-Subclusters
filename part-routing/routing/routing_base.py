#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
路由策略基类
"""

from abc import ABC, abstractmethod

class RoutingBase(ABC):
    """路由策略基类"""
    
    def __init__(self, topology):
        """
        初始化路由策略
        
        参数:
            topology: 网络拓扑对象
        """
        self.topology = topology
        self.graph = topology.get_graph()
        self.paths = {}  # 缓存路径
        
        # 预计算路径
        self.precompute_paths()
    
    @abstractmethod
    def precompute_paths(self):
        """预计算路径"""
        pass
    
    @abstractmethod
    def recalculate_routes(self, new_topology):
        """预计算路径"""
        pass
    
    @abstractmethod
    def get_next_hop(self, current, destination, packet=None):
        """
        获取下一跳节点
        
        参数:
            current: 当前节点
            destination: 目标节点
            packet: 数据包对象（可选）
            
        返回:
            下一跳节点ID
        """
        pass
    
    def get_path(self, source, destination):
        """
        获取从源到目的的完整路径
        
        参数:
            source: 源节点
            destination: 目标节点
            
        返回:
            节点ID列表，表示完整路径
        """
        if (source, destination) not in self.paths:
            return None
        return self.paths[(source, destination)]
