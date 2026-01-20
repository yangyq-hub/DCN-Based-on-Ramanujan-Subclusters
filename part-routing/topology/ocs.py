#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OCS可重构网络拓扑生成器 - 针对热点流量优化版，支持历史流量保留
"""

import networkx as nx
import numpy as np
import random
from tqdm import tqdm
from collections import defaultdict
import heapq

from topology.topology_base import TopologyBase
from topology.ramanujan import RamanujanTopology

class OCSReconfigurableTopology(TopologyBase):
    """OCS可重构网络拓扑 - 针对热点流量优化，支持历史流量保留"""
    
    def __init__(self, n_tor=128, d_tor=6, n_ocs_links=256, ocs_reconfiguration_interval=10.0, 
                 ocs_reconfiguration_delay=0.1, historical_traffic_weight=0.1):
        """
        初始化OCS可重构网络拓扑
        
        参数:
            n_tor: 每个ToR交换机的节点数
            d_tor: ToR交换机中每个节点的度数
            n_ocs_links: OCS链路数量
            ocs_reconfiguration_interval: OCS重构间隔(秒)
            ocs_reconfiguration_delay: OCS重构延迟(秒)
            historical_traffic_weight: 历史流量权重(0-1之间)，表示保留多少比例的历史连接
        """
        super().__init__()
        self.n_tor = n_tor
        self.d_tor = d_tor
        self.n_ocs_links = n_ocs_links
        self.ocs_reconfiguration_interval = ocs_reconfiguration_interval
        self.ocs_reconfiguration_delay = ocs_reconfiguration_delay
        self.historical_traffic_weight = historical_traffic_weight
        
        # 两个ToR交换机的节点ID范围
        self.tor1_nodes = list(range(0, n_tor))
        self.tor2_nodes = list(range(n_tor, 2 * n_tor))
        
        # OCS连接
        self.ocs_connections = set()
        self.previous_ocs_connections = set()  # 存储上一次的OCS连接
        
        # 流量历史记录
        self.traffic_history = defaultdict(list)  # 存储历史流量记录 {(src, dst): [traffic_values]}
        self.traffic_history_window = 3  # 保留最近3次的流量记录
        self.previous_traffic_matrix = None  # 存储上一次的流量矩阵
        
        # 热点检测阈值
        self.hotspot_threshold = 0.8  # 流量超过平均值的80%被视为热点
        
        # 生成拓扑
        self.generate()
    
    def generate(self):
        """生成OCS可重构网络拓扑"""
        print("生成OCS可重构网络拓扑...")
        
        # 创建空图
        self.graph = nx.Graph()
        
        # 生成两个Ramanujan图作为ToR拓扑
        print("生成第一个ToR拓扑...")
        tor1_topology = RamanujanTopology(self.n_tor, self.d_tor)
        tor1_graph = tor1_topology.graph
        
        print("生成第二个ToR拓扑...")
        tor2_topology = RamanujanTopology(self.n_tor, self.d_tor)
        tor2_graph = tor2_topology.graph
        
        # 添加节点
        for i in self.tor1_nodes:
            self.graph.add_node(i)
        for i in self.tor2_nodes:
            self.graph.add_node(i)
        
        # 添加ToR内部链路
        print("添加ToR内部链路...")
        # ToR1内部链路
        for u, v in tor1_graph.edges():
            self.graph.add_edge(u, v)
        
        # ToR2内部链路 (需要偏移节点ID)
        for u, v in tor2_graph.edges():
            self.graph.add_edge(u + self.n_tor, v + self.n_tor)
        
        # 初始化OCS连接
        print("初始化OCS连接...")
        self._initialize_ocs_connections()
        
        # 设置链路属性
        self._set_link_properties()
        
        print(f"OCS可重构网络拓扑生成完成，节点数: {self.graph.number_of_nodes()}, 边数: {self.graph.number_of_edges()}")
    
    def _initialize_ocs_connections(self):
        """初始化OCS连接"""
        # 随机选择节点对作为OCS连接
        tor1_nodes = self.tor1_nodes
        tor2_nodes = self.tor2_nodes
        
        # 确保不超过可能的最大连接数
        max_possible_links = min(self.n_ocs_links, len(tor1_nodes) * len(tor2_nodes))
        
        # 随机选择节点对
        selected_pairs = set()
        while len(selected_pairs) < max_possible_links:
            u = random.choice(tor1_nodes)
            v = random.choice(tor2_nodes)
            selected_pairs.add((u, v))
        
        # 添加OCS连接
        for u, v in selected_pairs:
            self.graph.add_edge(u, v)
            self.ocs_connections.add((u, v))
            self.ocs_connections.add((v, u))  # 添加反向连接
    
    def _set_link_properties(self):
        """设置链路属性"""
        # 为每条链路设置容量、延迟和缓冲区大小
        for u, v in self.graph.edges():
            if self._is_ocs_link(u, v):
                # OCS链路属性
                capacity = 100.0  # 100Gbps
                delay = 0.001     # 1微秒
                buffer_size = 1024  # 1024KB
            else:
                # ToR内部链路属性
                capacity = 18.0   # 18Gbps
                delay = 0.03 + random.random() * 0.05  # 0.03-0.08ms
                buffer_size = 1024 + random.randint(0, 1536)  # 512-2048KB
            
            self.link_capacity[(u, v)] = capacity
            self.link_delay[(u, v)] = delay
            self.link_buffer[(u, v)] = buffer_size
    
    def _is_ocs_link(self, u, v):
        """判断是否为OCS链路"""
        return (u in self.tor1_nodes and v in self.tor2_nodes) or (u in self.tor2_nodes and v in self.tor1_nodes)
    
    def _update_traffic_history(self, traffic_matrix):
        """
        更新流量历史记录
        
        参数:
            traffic_matrix: 当前流量矩阵
        """
        if not traffic_matrix:
            return
            
        # 更新每个节点对的流量历史
        for (src, dst), traffic in traffic_matrix.items():
            # 只关注跨集群流量
            if self._is_ocs_link(src, dst):
                self.traffic_history[(src, dst)].append(traffic)
                
                # 保持历史窗口大小
                if len(self.traffic_history[(src, dst)]) > self.traffic_history_window:
                    self.traffic_history[(src, dst)] = self.traffic_history[(src, dst)][-self.traffic_history_window:]
    
    def _detect_hotspots(self, traffic_matrix):
        """
        检测热点流量
        
        参数:
            traffic_matrix: 当前流量矩阵
            
        返回:
            热点节点对列表及其流量
        """
        if not traffic_matrix:
            return []
            
        # 计算跨集群流量的平均值
        cross_cluster_traffic = []
        for (src, dst), traffic in traffic_matrix.items():
            if self._is_ocs_link(src, dst):
                cross_cluster_traffic.append(traffic)
        
        if not cross_cluster_traffic:
            return []
            
        avg_traffic = sum(cross_cluster_traffic) / len(cross_cluster_traffic)
        hotspot_threshold = avg_traffic * self.hotspot_threshold
        
        # 识别热点流量
        hotspots = []
        for (src, dst), traffic in traffic_matrix.items():
            if self._is_ocs_link(src, dst) and traffic > hotspot_threshold:
                hotspots.append((src, dst, traffic))
        
        # 按流量排序
        hotspots.sort(key=lambda x: x[2], reverse=True)
        
        return hotspots
    
    def _predict_future_traffic(self, traffic_matrix):
        """
        基于历史数据预测未来流量
        
        参数:
            traffic_matrix: 当前流量矩阵
            
        返回:
            预测的流量矩阵
        """
        # 更新流量历史
        self._update_traffic_history(traffic_matrix)
        
        predicted_traffic = {}
        
        # 对每个节点对进行预测
        for (src, dst), history in self.traffic_history.items():
            if len(history) > 0:
                # 使用简单的趋势预测
                if len(history) >= 2:
                    # 计算增长趋势
                    trend = (history[-1] - history[0]) / len(history)
                    # 预测下一个时间点的流量
                    predicted = max(0, history[-1] + trend)
                else:
                    # 如果历史数据不足，使用最后一个值
                    predicted = history[-1]
                
                predicted_traffic[(src, dst)] = predicted
        
        return predicted_traffic
    
    def _calculate_link_stability(self, link, current_traffic, previous_traffic):
        """
        计算链路稳定性得分，用于决定是否保留历史链路
        
        参数:
            link: (src, dst)链路
            current_traffic: 当前流量矩阵
            previous_traffic: 上一次流量矩阵
            
        返回:
            稳定性得分，越高表示越应该保留
        """
        src, dst = link
        
        # 如果链路在当前流量矩阵中没有流量，给予低分
        current_flow = current_traffic.get((src, dst), 0)
        if current_flow == 0:
            return 0
        
        # 如果链路在上一次流量矩阵中有流量，计算流量变化率
        previous_flow = previous_traffic.get((src, dst), 0)
        if previous_flow > 0:
            # 流量稳定或增长的链路更有价值
            flow_change = current_flow / previous_flow if previous_flow > 0 else float('inf')
            
            # 流量变化不大或增长的链路更稳定
            if 0.8 <= flow_change <= 1.2:  # 流量变化在±20%以内
                stability = 3.0  # 高稳定性
            elif flow_change > 1.2:  # 流量增长超过20%
                stability = 2.0  # 中等稳定性，但有增长趋势
            else:  # 流量下降超过20%
                stability = 1.0  # 低稳定性
        else:
            # 新出现的流量
            stability = 0.5
        
        # 考虑流量大小，大流量链路更重要
        traffic_factor = min(1.0, current_flow / 10.0)  # 假设10Gbps是较大流量
        
        return stability * traffic_factor
    
    def reconfigure_ocs(self, traffic_matrix=None):
        """
        重新配置OCS连接，针对热点流量优化，同时保留部分历史连接
        
        参数:
            traffic_matrix: 流量矩阵，如果为None则随机重构
        
        返回:
            新的OCS连接集合
        """
        print("重新配置OCS连接...")
        
        # 保存当前OCS连接作为历史记录
        self.previous_ocs_connections = set(self.ocs_connections)
        
        # 移除旧的OCS连接
        ocs_edges = [(u, v) for u, v in self.graph.edges() if self._is_ocs_link(u, v)]
        for u, v in ocs_edges:
            self.graph.remove_edge(u, v)
        
        self.ocs_connections.clear()
        
        # 如果提供了流量矩阵，根据流量需求重构
        if traffic_matrix is not None and traffic_matrix:
            print("基于流量矩阵进行OCS重构")
            
            # 检测热点流量
            hotspots = self._detect_hotspots(traffic_matrix)
            
            # 打印热点信息
            if hotspots:
                print(f"检测到{len(hotspots)}个热点流量:")
                for i, (src, dst, traffic) in enumerate(hotspots[:5]):  # 只打印前5个
                    print(f"  热点 {i+1}: ({src}, {dst}) - {traffic:.3f} Gbps")
                if len(hotspots) > 5:
                    print(f"  ... 以及 {len(hotspots)-5} 个其他热点")
            
            # 计算需要保留的历史连接数量
            history_links_to_keep = int(self.n_ocs_links * self.historical_traffic_weight)
            new_links_to_add = self.n_ocs_links - history_links_to_keep
            
            print(f"计划保留 {history_links_to_keep} 条历史连接，添加 {new_links_to_add} 条新连接")
            
            # 如果有上一次的流量矩阵，计算历史连接的稳定性
            if self.previous_traffic_matrix:
                # 计算所有历史连接的稳定性得分
                link_stability = {}
                for u, v in self.previous_ocs_connections:
                    if u < v:  # 只处理一个方向
                        link_stability[(u, v)] = self._calculate_link_stability(
                            (u, v), traffic_matrix, self.previous_traffic_matrix
                        )
                
                # 按稳定性得分排序
                sorted_history_links = sorted(
                    [(link, score) for link, score in link_stability.items()],
                    key=lambda x: x[1], reverse=True
                )
                
                # 选择得分最高的历史连接保留
                history_links_selected = [link for link, _ in sorted_history_links[:history_links_to_keep]]
                
                print(f"基于稳定性评分选择了 {len(history_links_selected)} 条历史连接")
            else:
                # 如果没有历史数据，随机选择历史连接
                history_links = [(u, v) for u, v in self.previous_ocs_connections if u < v]  # 去重
                random.shuffle(history_links)
                history_links_selected = history_links[:history_links_to_keep]
                
                print(f"随机选择了 {len(history_links_selected)} 条历史连接")
            
            # 优先为热点分配OCS链路
            selected_pairs = []
            
            # 1. 首先添加选定的历史连接
            selected_pairs.extend(history_links_selected)
            
            # 创建已选节点对集合
            selected_set = set(selected_pairs)
            
            # 2. 分配给热点流量
            hotspot_pairs = []
            for src, dst, _ in hotspots:
                if (src, dst) not in selected_set and (dst, src) not in selected_set:
                    hotspot_pairs.append((src, dst))
                    selected_set.add((src, dst))
                    
                    # 如果已经达到新链路数量上限，停止添加
                    if len(hotspot_pairs) >= new_links_to_add:
                        break
            
            selected_pairs.extend(hotspot_pairs)
            print(f"为热点流量分配了 {len(hotspot_pairs)} 条OCS链路")
            
            # 3. 如果热点不足，考虑其他有流量的节点对
            if len(selected_pairs) < self.n_ocs_links:
                # 创建节点对和流量的列表，排除已分配的
                remaining_pairs = []
                for (src, dst), traffic in traffic_matrix.items():
                    if (src, dst) not in selected_set and (dst, src) not in selected_set and traffic > 0:
                        remaining_pairs.append((src, dst, traffic))
                
                # 按流量排序
                remaining_pairs.sort(key=lambda x: x[2], reverse=True)
                
                # 选择流量最大的节点对
                needed = min(self.n_ocs_links - len(selected_pairs), len(remaining_pairs))
                for src, dst, _ in remaining_pairs[:needed]:
                    selected_pairs.append((src, dst))
                    selected_set.add((src, dst))
                
                print(f"为其他流量分配了 {needed} 条OCS链路")
            
            # 4. 如果仍然不足，随机分配剩余链路
            if len(selected_pairs) < self.n_ocs_links:
                remaining = self.n_ocs_links - len(selected_pairs)
                print(f"随机分配剩余的 {remaining} 条OCS链路")
                
                # 随机选择更多节点对
                additional_pairs = []
                attempts = 0
                while len(additional_pairs) < remaining and attempts < 5000:
                    attempts += 1
                    u = random.choice(self.tor1_nodes)
                    v = random.choice(self.tor2_nodes)
                    if (u, v) not in selected_set and (v, u) not in selected_set:
                        additional_pairs.append((u, v))
                        selected_set.add((u, v))
                
                selected_pairs.extend(additional_pairs)
        else:
            # 随机重构
            print("使用随机重构")
            return self._random_reconfigure()
        
        # 添加新的OCS连接
        for u, v in selected_pairs:
            self.graph.add_edge(u, v)
            self.ocs_connections.add((u, v))
            self.ocs_connections.add((v, u))  # 添加反向连接
            
            # 设置OCS链路属性
            self.link_capacity[(u, v)] = 100.0  # 100Gbps
            self.link_delay[(u, v)] = 0.001     # 1微秒
            self.link_buffer[(u, v)] = 1024     # 1024KB
            
            # 同时设置反向链路属性
            self.link_capacity[(v, u)] = 100.0
            self.link_delay[(v, u)] = 0.001
            self.link_buffer[(v, u)] = 1024
        
        # 保存当前流量矩阵作为历史记录
        self.previous_traffic_matrix = traffic_matrix.copy() if traffic_matrix else None
        
        print(f"OCS重构完成，当前OCS连接数: {len(selected_pairs)}")
        
        # 计算热点覆盖率
        if hotspots:
            hotspot_set = set((src, dst) for src, dst, _ in hotspots)
            covered_hotspots = sum(1 for u, v in selected_pairs if (u, v) in hotspot_set or (v, u) in hotspot_set)
            coverage_rate = (covered_hotspots / len(hotspots)) * 100 if hotspots else 0
            print(f"热点覆盖率: {coverage_rate:.2f}% ({covered_hotspots}/{len(hotspots)})")
        
        # 计算历史连接保留率
        history_links_original = [(u, v) for u, v in self.previous_ocs_connections if u < v]
        history_links_kept = sum(1 for u, v in selected_pairs if (u, v) in self.previous_ocs_connections or (v, u) in self.previous_ocs_connections)
        history_retention_rate = (history_links_kept / len(history_links_original)) * 100 if history_links_original else 0
        print(f"历史连接保留率: {history_retention_rate:.2f}% ({history_links_kept}/{len(history_links_original)})")
        
        return self.ocs_connections

    def _random_reconfigure(self):
        """随机重构OCS连接"""
        # 随机选择节点对
        selected_pairs = set()
        attempts = 0
        
        while len(selected_pairs) < self.n_ocs_links and attempts < 10000:
            attempts += 1
            u = random.choice(self.tor1_nodes)
            v = random.choice(self.tor2_nodes)
            selected_pairs.add((u, v))
        
        selected_pairs = list(selected_pairs)
        
        # 添加新的OCS连接
        for u, v in selected_pairs:
            self.graph.add_edge(u, v)
            self.ocs_connections.add((u, v))
            self.ocs_connections.add((v, u))  # 添加反向连接
            
            # 设置OCS链路属性
            self.link_capacity[(u, v)] = 100.0  # 100Gbps
            self.link_delay[(u, v)] = 0.001     # 1微秒
            self.link_buffer[(u, v)] = 1024     # 1024KB
            
            # 同时设置反向链路属性
            self.link_capacity[(v, u)] = 100.0
            self.link_delay[(v, u)] = 0.001
            self.link_buffer[(v, u)] = 1024
        
        print(f"随机OCS重构完成，当前OCS连接数: {len(selected_pairs)}")
        return self.ocs_connections
    
    def evaluate_configuration(self, traffic_matrix):
        """
        评估当前OCS配置的有效性
        
        参数:
            traffic_matrix: 流量矩阵
            
        返回:
            评估分数和统计信息
        """
        if not traffic_matrix:
            return {'score': 0, 'stats': {}}
            
        # 统计信息
        stats = {
            'total_traffic': 0,
            'served_traffic': 0,
            'unserved_traffic': 0,
            'hotspot_traffic': 0,
            'hotspot_served': 0,
            'hotspot_count': 0,
            'ocs_utilization': 0,
            'history_retention': 0
        }
        
        # 检测热点
        hotspots = self._detect_hotspots(traffic_matrix)
        stats['hotspot_count'] = len(hotspots)
        
        # 计算总流量和服务流量
        for (src, dst), traffic in traffic_matrix.items():
            if self._is_ocs_link(src, dst):
                stats['total_traffic'] += traffic
                
                # 检查是否为热点
                is_hotspot = any(src == hs[0] and dst == hs[1] for hs in hotspots)
                if is_hotspot:
                    stats['hotspot_traffic'] += traffic
                
                # 检查是否有直接OCS连接
                if self.graph.has_edge(src, dst):
                    stats['served_traffic'] += traffic
                    if is_hotspot:
                        stats['hotspot_served'] += traffic
                else:
                    stats['unserved_traffic'] += traffic
        
        # 计算OCS链路利用率
        ocs_links_count = sum(1 for u, v in self.graph.edges() if self._is_ocs_link(u, v))
        if ocs_links_count > 0:
            stats['ocs_utilization'] = stats['served_traffic'] / ocs_links_count
        
        # 计算历史连接保留率
        if self.previous_ocs_connections:
            history_links_original = set((u, v) for u, v in self.previous_ocs_connections if u < v)
            history_links_kept = sum(1 for u, v in self.ocs_connections if (u, v) in history_links_original or (v, u) in history_links_original)
            stats['history_retention'] = history_links_kept / len(history_links_original) if history_links_original else 0
        
        # 计算总体评分 (0-100)
        # 考虑热点流量服务率、总体流量服务率、OCS链路利用率和历史连接保留率
        hotspot_service_rate = stats['hotspot_served'] / stats['hotspot_traffic'] if stats['hotspot_traffic'] > 0 else 0
        overall_service_rate = stats['served_traffic'] / stats['total_traffic'] if stats['total_traffic'] > 0 else 0
        
        # 评分计算: 60%热点服务率 + 20%总体服务率 + 20%历史连接保留率
        score = (hotspot_service_rate * 60 + 
                overall_service_rate * 20 + 
                stats['history_retention'] * 20)
        
        return {
            'score': score,
            'stats': stats
        }
        
    def get_ocs_connections(self):
        """获取当前OCS连接"""
        return self.ocs_connections
    
    def get_tor1_nodes(self):
        """获取ToR1中的节点"""
        return self.tor1_nodes
    
    def get_tor2_nodes(self):
        """获取ToR2中的节点"""
        return self.tor2_nodes
    
    def get_reconfiguration_params(self):
        """获取重构参数"""
        return {
            'interval': self.ocs_reconfiguration_interval,
            'delay': self.ocs_reconfiguration_delay,
            'historical_weight': self.historical_traffic_weight
        }
    
    def get_topology_info(self):
        """获取拓扑信息"""
        return {
            'n_tor': self.n_tor,
            'd_tor': self.d_tor,
            'n_ocs_links': self.n_ocs_links,
            'total_nodes': self.graph.number_of_nodes(),
            'total_edges': self.graph.number_of_edges(),
            'ocs_edges': len([e for e in self.graph.edges() if self._is_ocs_link(*e)]),
            'tor_edges': self.graph.number_of_edges() - len([e for e in self.graph.edges() if self._is_ocs_link(*e)])
        }
    
    def copy(self):
        """创建拓扑的深拷贝"""
        import copy
        new_topo = OCSReconfigurableTopology(
            n_tor=self.n_tor,
            d_tor=self.d_tor,
            n_ocs_links=self.n_ocs_links,
            ocs_reconfiguration_interval=self.ocs_reconfiguration_interval,
            ocs_reconfiguration_delay=self.ocs_reconfiguration_delay,
            historical_traffic_weight=self.historical_traffic_weight
        )
        
        # 复制图结构
        new_topo.graph = self.graph.copy()
        
        # 复制节点列表
        new_topo.tor1_nodes = copy.deepcopy(self.tor1_nodes)
        new_topo.tor2_nodes = copy.deepcopy(self.tor2_nodes)
        
        # 复制OCS连接
        new_topo.ocs_connections = copy.deepcopy(self.ocs_connections)
        new_topo.previous_ocs_connections = copy.deepcopy(self.previous_ocs_connections)
        
        # 复制链路属性
        new_topo.link_capacity = copy.deepcopy(self.link_capacity)
        new_topo.link_delay = copy.deepcopy(self.link_delay)
        new_topo.link_buffer = copy.deepcopy(self.link_buffer)
        
        # 复制流量历史
        new_topo.traffic_history = copy.deepcopy(self.traffic_history)
        new_topo.previous_traffic_matrix = copy.deepcopy(self.previous_traffic_matrix)
        
        return new_topo
    
    def has_edge(self, u, v):
        """
        检查是否存在边(u,v)
        """
        return self.graph.has_edge(u, v)
    
    def get_path(self, src, dst):
        """
        获取从src到dst的最短路径
        """
        try:
            return nx.shortest_path(self.graph, src, dst)
        except nx.NetworkXNoPath:
            return []
    
    def get_path_length(self, src, dst):
        """
        获取从src到dst的最短路径长度
        """
        try:
            return nx.shortest_path_length(self.graph, src, dst)
        except nx.NetworkXNoPath:
            return float('inf')
    
    def get_path_delay(self, src, dst):
        """
        获取从src到dst的路径延迟
        """
        try:
            path = nx.shortest_path(self.graph, src, dst)
            delay = 0.0
            for i in range(len(path) - 1):
                u, v = path[i], path[i+1]
                delay += self.link_delay.get((u, v), 0.0)
            return delay
        except nx.NetworkXNoPath:
            return float('inf')
    
    def get_path_capacity(self, src, dst):
        """
        获取从src到dst的路径容量(瓶颈容量)
        """
        try:
            path = nx.shortest_path(self.graph, src, dst)
            capacities = []
            for i in range(len(path) - 1):
                u, v = path[i], path[i+1]
                capacities.append(self.link_capacity.get((u, v), 0.0))
            return min(capacities) if capacities else 0.0
        except nx.NetworkXNoPath:
            return 0.0
def main():
    """
    测试和演示OCS可重构网络拓扑
    """
    import matplotlib.pyplot as plt
    import time
    
    # 创建OCS可重构网络拓扑
    n_tor = 64  # 每个ToR交换机的节点数
    d_tor = 4   # ToR交换机中每个节点的度数
    n_ocs = 100  # OCS链路数量
    history_weight = 0.3  # 历史流量权重
    
    print(f"创建OCS可重构网络拓扑: n_tor={n_tor}, d_tor={d_tor}, n_ocs={n_ocs}, history_weight={history_weight}")
    
    topo = OCSReconfigurableTopology(
        n_tor=n_tor,
        d_tor=d_tor,
        n_ocs_links=n_ocs,
        ocs_reconfiguration_interval=10.0,
        ocs_reconfiguration_delay=0.1,
        historical_traffic_weight=history_weight
    )
    
    # 打印拓扑信息
    info = topo.get_topology_info()
    print("\n拓扑信息:")
    for k, v in info.items():
        print(f"  {k}: {v}")
    
    # 生成随机流量矩阵
    def generate_traffic_matrix(hotspot_ratio=0.1, hotspot_intensity=5.0):
        """生成随机流量矩阵，包含一些热点"""
        traffic_matrix = {}
        
        # 生成基础流量
        for src in topo.get_tor1_nodes():
            for dst in topo.get_tor2_nodes():
                # 基础流量为0-1.0Gbps
                traffic_matrix[(src, dst)] = random.random()
        
        # 添加热点流量
        hotspot_count = int(n_tor * hotspot_ratio)
        hotspot_srcs = random.sample(topo.get_tor1_nodes(), hotspot_count)
        hotspot_dsts = random.sample(topo.get_tor2_nodes(), hotspot_count)
        
        for i in range(hotspot_count):
            src = hotspot_srcs[i]
            dst = hotspot_dsts[i]
            # 热点流量为基础流量的5-10倍
            traffic_matrix[(src, dst)] = traffic_matrix.get((src, dst), 0) + hotspot_intensity * random.uniform(1.0, 2.0)
        
        return traffic_matrix
    
    # 模拟多次OCS重构
    reconfiguration_count = 5
    scores = []
    hotspot_coverage = []
    history_retention = []
    
    print(f"\n开始模拟{reconfiguration_count}次OCS重构...")
    
    # 初始流量矩阵
    traffic_matrix = generate_traffic_matrix()
    
    for i in range(reconfiguration_count):
        print(f"\n第{i+1}次OCS重构:")
        
        # 评估当前配置
        eval_result = topo.evaluate_configuration(traffic_matrix)
        print(f"  当前配置评分: {eval_result['score']:.2f}")
        print(f"  热点数量: {eval_result['stats']['hotspot_count']}")
        print(f"  总流量: {eval_result['stats']['total_traffic']:.2f} Gbps")
        print(f"  已服务流量: {eval_result['stats']['served_traffic']:.2f} Gbps ({eval_result['stats']['served_traffic']/eval_result['stats']['total_traffic']*100:.2f}%)")
        print(f"  热点流量: {eval_result['stats']['hotspot_traffic']:.2f} Gbps")
        print(f"  已服务热点流量: {eval_result['stats']['hotspot_served']:.2f} Gbps ({eval_result['stats']['hotspot_served']/eval_result['stats']['hotspot_traffic']*100:.2f}% 的热点)")
        
        # 记录评估结果
        scores.append(eval_result['score'])
        
        if eval_result['stats']['hotspot_traffic'] > 0:
            hotspot_coverage.append(eval_result['stats']['hotspot_served'] / eval_result['stats']['hotspot_traffic'] * 100)
        else:
            hotspot_coverage.append(0)
            
        history_retention.append(eval_result['stats']['history_retention'] * 100)
        
        # 重构OCS连接
        start_time = time.time()
        topo.reconfigure_ocs(traffic_matrix)
        reconfig_time = time.time() - start_time
        print(f"  OCS重构耗时: {reconfig_time:.4f}秒")
        
        # 生成新的流量矩阵，但保留部分热点
        if i < reconfiguration_count - 1:
            # 保留70%的流量模式，添加30%新模式
            new_traffic = generate_traffic_matrix()
            mixed_traffic = {}
            
            for src_dst, traffic in traffic_matrix.items():
                # 70%概率保留旧流量，30%使用新流量
                if random.random() < 0.7:
                    mixed_traffic[src_dst] = traffic
                else:
                    mixed_traffic[src_dst] = new_traffic.get(src_dst, 0)
            
            # 添加新流量矩阵中不存在于旧流量矩阵的流量
            for src_dst, traffic in new_traffic.items():
                if src_dst not in mixed_traffic:
                    mixed_traffic[src_dst] = traffic
            
            traffic_matrix = mixed_traffic
    
    # 最终评估
    final_eval = topo.evaluate_configuration(traffic_matrix)
    print(f"\n最终配置评分: {final_eval['score']:.2f}")
    
    # 绘制评分变化图
    plt.figure(figsize=(12, 8))
    
    plt.subplot(3, 1, 1)
    plt.plot(range(1, reconfiguration_count + 1), scores, 'o-', color='blue')
    plt.title('OCS重构评分变化')
    plt.xlabel('重构次数')
    plt.ylabel('评分')
    plt.grid(True)
    
    plt.subplot(3, 1, 2)
    plt.plot(range(1, reconfiguration_count + 1), hotspot_coverage, 'o-', color='red')
    plt.title('热点流量覆盖率变化')
    plt.xlabel('重构次数')
    plt.ylabel('热点覆盖率 (%)')
    plt.grid(True)
    
    plt.subplot(3, 1, 3)
    plt.plot(range(1, reconfiguration_count + 1), history_retention, 'o-', color='green')
    plt.title('历史连接保留率变化')
    plt.xlabel('重构次数')
    plt.ylabel('历史连接保留率 (%)')
    plt.grid(True)
    
    plt.tight_layout()
    plt.savefig('ocs_reconfiguration_performance.png')
    plt.show()
    
    print(f"性能评估图表已保存为 'ocs_reconfiguration_performance.png'")

if __name__ == "__main__":
    main()
