#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Ramanujan图拓扑生成器
"""

import networkx as nx
import numpy as np
import math
import random
from tqdm import tqdm
import scipy.linalg as LA

from topology.topology_base import TopologyBase

class RamanujanTopology(TopologyBase):
    """Ramanujan图拓扑"""
    
    def __init__(self, n, d, iterations=2000, initial_temp=100.0, cooling_rate=0.95):
        """
        初始化Ramanujan图拓扑
        
        参数:
            n: 节点数
            d: 每个节点的度数
            iterations: 模拟退火迭代次数
            initial_temp: 初始温度
            cooling_rate: 冷却率
        """
        super().__init__()
        self.n = n
        self.d = d
        self.iterations = iterations
        self.initial_temp = initial_temp
        self.cooling_rate = cooling_rate
        
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
        """生成Ramanujan图拓扑"""
        print(f"生成节点数为{self.n}、度数为{self.d}的Ramanujan图拓扑...")
        
        self.graph, _, _ = self._simulated_annealing_ramanujan(
            self.n, self.d, self.iterations, self.initial_temp, self.cooling_rate
        )
        
        # 设置链路属性
        self._set_link_properties()
        
        print(f"Ramanujan拓扑生成完成，节点数: {self.graph.number_of_nodes()}, 边数: {self.graph.number_of_edges()}")
    
    def _set_link_properties(self):
        """设置链路属性"""
        # 为每条链路设置容量、延迟和缓冲区大小
        for u, v in self.graph.edges():
            # 容量在10-40Gbps之间随机变化
            capacity = 18
            # 延迟在0.01-0.1ms之间随机变化
            delay = 0.03 + random.random() * 0.05
            # 缓冲区大小在512-2048KB之间随机变化
            buffer_size = 512 + random.randint(0, 1536)
            
            self.link_capacity[(u, v)] = capacity
            self.link_delay[(u, v)] = delay
            self.link_buffer[(u, v)] = buffer_size
    
    def _create_random_regular_graph(self, n, d):
        """创建随机正则图"""
        if n * d % 2 != 0:
            raise ValueError("n*d必须是偶数")
        
        G = nx.random_regular_graph(d, n)
        while not nx.is_connected(G):
            G = nx.random_regular_graph(d, n)
        
        return G
    
    def _get_second_eigenvalue(self, G):
        """计算图的第二大特征值"""
        A = nx.to_numpy_array(G)
        eigenvalues = sorted(LA.eigvalsh(A), reverse=True)
        return eigenvalues[1]
    
    def _edge_swap(self, G):
        """随机选择两条边并交换它们的端点"""
        edges = list(G.edges())
        if len(edges) < 2:
            return False, None, None
        
        # 随机选择两条边
        e1, e2 = random.sample(edges, 2)
        
        # 确保这两条边没有共同的端点
        if e1[0] == e2[0] or e1[0] == e2[1] or e1[1] == e2[0] or e1[1] == e2[1]:
            return False, None, None
        
        # 确保新边不存在
        if G.has_edge(e1[0], e2[0]) or G.has_edge(e1[1], e2[1]):
            return False, None, None
        
        # 移除旧边
        G.remove_edge(e1[0], e1[1])
        G.remove_edge(e2[0], e2[1])
        
        # 添加新边
        G.add_edge(e1[0], e2[0])
        G.add_edge(e1[1], e2[1])
        
        return True, [e1, e2], [(e1[0], e2[0]), (e1[1], e2[1])]
    
    def _reverse_swap(self, G, old_edges, new_edges):
        """撤销边交换"""
        # 移除新边
        G.remove_edge(new_edges[0][0], new_edges[0][1])
        G.remove_edge(new_edges[1][0], new_edges[1][1])
        
        # 恢复旧边
        G.add_edge(old_edges[0][0], old_edges[0][1])
        G.add_edge(old_edges[1][0], old_edges[1][1])
    
    def _simulated_annealing_ramanujan(self, n, d, iterations=20000, initial_temp=100.0, cooling_rate=0.95):
        """
        使用模拟退火算法生成近似Ramanujan图
        """
        G = self._create_random_regular_graph(n, d)
        ramanujan_bound = 2 * math.sqrt(d - 1)
        
        current_lambda2 = self._get_second_eigenvalue(G)
        print(f"初始第二大特征值: {current_lambda2}, 与界限比值: {current_lambda2/ramanujan_bound:.4f}")
        history = [current_lambda2]
        all_eigenvalues = []
        
        best_lambda2 = current_lambda2
        best_G = G.copy()
        
        temp = initial_temp
        no_improvement_count = 0
        max_no_improvement = 1000
        
        for i in tqdm(range(iterations)):
            # 检查是否应该提前终止
            if no_improvement_count >= max_no_improvement:
                print(f"连续 {max_no_improvement} 次迭代没有找到更好的解，提前终止")
                break
                
            success, old_edges, new_edges = self._edge_swap(G)
            
            if not success:
                history.append(current_lambda2)
                continue
            
            # 确保图仍然连通
            if not nx.is_connected(G):
                self._reverse_swap(G, old_edges, new_edges)
                history.append(current_lambda2)
                continue
            
            new_lambda2 = self._get_second_eigenvalue(G)
            delta_e = new_lambda2 - current_lambda2
            
            # 接受判断
            randomn = random.random()
            acceptance_prob = math.exp(-600*delta_e / temp)
            
            if delta_e < 0 or randomn < acceptance_prob:
                # 接受新解
                current_lambda2 = new_lambda2
                no_improvement_count = 0
            
                history.append(current_lambda2)
                
                # 更新最佳解
                if current_lambda2 < best_lambda2:
                    best_lambda2 = current_lambda2
                    best_G = G.copy()
                    print(f"迭代 {i}: 找到更好的解，λ₂ = {best_lambda2}, 与界限比值: {best_lambda2/ramanujan_bound:.4f}")
            else:
                # 拒绝新解，撤销边交换
                self._reverse_swap(G, old_edges, new_edges)
                history.append(current_lambda2)
                no_improvement_count += 1
            
            # 降低温度
            if i % 100 == 0:
                temp *= cooling_rate
        
        print(f"最终第二大特征值: {best_lambda2}")
        print(f"与Ramanujan界限的比值: {best_lambda2 / ramanujan_bound:.4f}")
        
        return best_G, history, all_eigenvalues
