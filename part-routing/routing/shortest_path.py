#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
最短路径路由策略（带随机边删除功能）
"""

import networkx as nx
import random
import math
from routing.routing_base import RoutingBase

class ShortestPathRouting(RoutingBase):
    """最短路径路由策略"""
    
    def __init__(self, topology, failure_rate=0.0):
        """
        初始化最短路径路由
        
        参数:
            topology: 网络拓扑对象
            failure_rate: 随机删除的边比例 (0.0-1.0)
        """
        super().__init__(topology)
        self.failure_rate = failure_rate
        self.original_graph = self.graph.copy()  # 保存原始图的副本
        self.failed_edges = []  # 存储被删除的边
        
        # 随机删除边
        self.randomly_remove_edges()
        
        # 预计算路径
        self.precompute_paths()
    
    def randomly_remove_edges(self):
        """随机删除指定比例的边"""
        print(f"随机删除 {self.failure_rate * 100:.1f}% 的边...")
        
        # 获取所有边
        all_edges = list(self.graph.edges())
        
        # 计算需要删除的边数
        num_edges_to_remove = math.ceil(len(all_edges) * self.failure_rate)
        
        # 随机选择要删除的边
        if num_edges_to_remove > 0:
            edges_to_remove = random.sample(all_edges, num_edges_to_remove)
            
            # 逐个删除边，但确保图仍然保持连通
            for u, v in edges_to_remove:
                # 临时删除边
                self.graph.remove_edge(u, v)
                
                # 检查图是否仍然连通
                if nx.is_connected(self.graph):
                    # 记录成功删除的边
                    self.failed_edges.append((u, v))
                    print(f"  删除边: ({u}, {v})")
                else:
                    # 如果图不再连通，恢复边
                    self.graph.add_edge(u, v)
            
            print(f"成功删除 {len(self.failed_edges)} 条边，保持图连通")
        else:
            print("没有边被删除")
    
    def precompute_paths(self):
        """预计算所有节点对之间的最短路径"""
        print("预计算最短路径...")
        shortest_paths = nx.all_pairs_shortest_path(self.graph)
        
        # 存储所有路径
        self.paths = {}
        for source, targets in shortest_paths:
            for target, path in targets.items():
                self.paths[(source, target)] = path
        
        # 计算路径统计信息
        path_lengths = [len(path)-1 for path in self.paths.values()]
        if path_lengths:
            avg_path_length = sum(path_lengths) / len(path_lengths)
            max_path_length = max(path_lengths)
            print(f"平均路径长度: {avg_path_length:.2f}, 最大路径长度: {max_path_length}")
    
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
        if current == destination:
            return None
        
        # 获取预计算的路径
        path = self.paths.get((current, destination))
        
        if path and len(path) > 1:
            return path[1]
        
        # 如果没有预计算的路径，使用临时计算
        try:
            path = nx.shortest_path(self.graph, current, destination)
            if len(path) > 1:
                return path[1]
        except nx.NetworkXNoPath:
            print(f"警告: 从节点 {current} 到节点 {destination} 没有可用路径")
            return None
        except Exception as e:
            print(f"路径计算错误: {e}")
            return None
        
        # 如果仍然找不到路径，返回None
        return None
    
    def restore_network(self):
        """恢复网络到原始状态（恢复所有删除的边）"""
        print("恢复网络到原始状态...")
        self.graph = self.original_graph.copy()
        self.failed_edges = []
        self.precompute_paths()
        return True
    
    def get_routing_stats(self):
        """获取路由统计信息"""
        stats = {
            "routing_type": "最短路径路由",
            "total_edges": self.original_graph.number_of_edges(),
            "failed_edges": len(self.failed_edges),
            "failure_rate": len(self.failed_edges) / self.original_graph.number_of_edges() if self.original_graph.number_of_edges() > 0 else 0,
            "connected": nx.is_connected(self.graph),
        }
        
        # 如果图是连通的，计算路径统计
        if stats["connected"]:
            path_lengths = [len(path)-1 for path in self.paths.values()]
            stats.update({
                "avg_path_length": sum(path_lengths) / len(path_lengths) if path_lengths else 0,
                "max_path_length": max(path_lengths) if path_lengths else 0,
                "total_paths": len(self.paths)
            })
        
        return stats
    
    def recalculate_routes(self, new_topology):
        """
        根据新拓扑重新计算路由
        
        参数:
            new_topology: 新的网络拓扑对象
        """
        # 更新拓扑引用
        self.topology = new_topology
        self.graph = new_topology.get_graph()
        
        # 重新计算路由表
        self.precompute_paths()
