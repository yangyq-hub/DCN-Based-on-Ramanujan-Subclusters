#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
均匀流量模式
"""

import random
import numpy as np
from collections import defaultdict
from traffic.traffic_base import TrafficBase

class UniformTraffic(TrafficBase):
    """均匀流量模式"""
    
    def __init__(self, topology, packet_rate=0.1, packet_size=1024, traffic_history_window=10.0):
        """
        初始化均匀流量模式
        
        参数:
            topology: 网络拓扑对象
            packet_rate: 每毫秒每节点产生的数据包数量
            packet_size: 平均数据包大小(字节)
            traffic_history_window: 流量历史窗口大小(秒)
        """
        super().__init__(topology, packet_rate, packet_size)
        self.packet_accumulator = 0.0  # 添加累积器以处理小数部分
        
        # 流量矩阵相关
        self.traffic_history_window = traffic_history_window * 1000  # 转换为毫秒
        self.traffic_history = []  # 存储历史流量记录 [(时间, 源, 目的, 大小), ...]
        self.last_matrix_time = 0.0  # 上次计算流量矩阵的时间
        self.current_traffic_matrix = defaultdict(float)  # 当前流量矩阵
    
    def generate_traffic(self, current_time, end_time):
        """
        生成均匀分布的流量
        
        参数:
            current_time: 当前仿真时间
            end_time: 结束仿真时间
            
        返回:
            数据包列表
        """
        packets = []
        
        # 计算这个时间段内每个节点产生的数据包数量
        time_interval = end_time - current_time
        # print(f"time_interval: {time_interval}")
        
        # 使用概率方法处理低流量情况
        for source in self.nodes:
            # 更新累积器
            self.packet_accumulator += self.packet_rate * time_interval
            packets_to_generate = int(self.packet_accumulator)
            self.packet_accumulator -= packets_to_generate
            
            # 如果累积器不足以生成完整数据包，使用概率方法决定是否生成
            if packets_to_generate == 0 and self.packet_accumulator > 0:
                if random.random() < self.packet_accumulator:
                    packets_to_generate = 1
                    self.packet_accumulator = 0
            
            # 为当前节点生成数据包
            for _ in range(packets_to_generate):
                # 随机选择目标节点（不是自己）
                if len(self.nodes) > 1:  # 确保有多个节点可选
                    destination = random.choice([n for n in self.nodes if n != source])
                    # print(f"source: {source}, destination: {destination}")
                    
                    # 随机生成数据包大小，围绕平均值波动
                    size = int(np.random.normal(self.packet_size, self.packet_size * 0.1))
                    size = max(64, size)  # 确保最小数据包大小为64字节
                    
                    # 随机生成发送时间，在当前时间和结束时间之间
                    start_time = current_time + random.random() * time_interval
                    
                    # 创建数据包
                    packet = self._create_packet(source, destination, size, start_time)
                    packets.append(packet)
                    
                    # 记录流量历史
                    self.traffic_history.append((start_time, source, destination, size))
        
        # 清理过期的流量历史记录
        self._clean_traffic_history(current_time)
        
        # 如果距离上次计算流量矩阵超过1秒，重新计算
        if current_time - self.last_matrix_time >= 1000:
            self._update_traffic_matrix(current_time)
            self.last_matrix_time = current_time
        
        return packets
    
    def _clean_traffic_history(self, current_time):
        """
        清理过期的流量历史记录
        
        参数:
            current_time: 当前仿真时间
        """
        cutoff_time = current_time - self.traffic_history_window
        self.traffic_history = [record for record in self.traffic_history if record[0] >= cutoff_time]
    
    def _update_traffic_matrix(self, current_time):
        """
        更新流量矩阵
        
        参数:
            current_time: 当前仿真时间
        """
        # 清空当前流量矩阵
        self.current_traffic_matrix = defaultdict(float)
        
        # 计算窗口起始时间
        window_start = current_time - self.traffic_history_window
        
        # 统计窗口内的流量
        for time, source, dest, size in self.traffic_history:
            if time >= window_start:
                # 将字节转换为比特，然后转换为Gbps
                bits = size * 8
                gbits = bits / 1e9  # 转换为Gb
                # 计算在窗口时间内的速率(Gbps)
                self.current_traffic_matrix[(source, dest)] += gbits / (self.traffic_history_window / 1000)
        
        # 打印一些统计信息
        if self.current_traffic_matrix:
            total_traffic = sum(self.current_traffic_matrix.values())
            max_traffic = max(self.current_traffic_matrix.values())
            num_flows = len(self.current_traffic_matrix)
            print(f"流量矩阵更新: {num_flows}条流, 总流量: {total_traffic:.3f}Gbps, 最大流: {max_traffic:.3f}Gbps")
    
    def get_current_traffic_matrix(self):
        """
        获取当前流量矩阵
        
        返回:
            流量矩阵字典，键为(源,目的)元组，值为流量(Gbps)
        """
        return dict(self.current_traffic_matrix)
    
    def get_traffic_matrix_for_clusters(self, cluster1, cluster2):
        """
        获取两个集群之间的流量矩阵
        
        参数:
            cluster1: 第一个集群的节点列表
            cluster2: 第二个集群的节点列表
            
        返回:
            集群间流量矩阵字典
        """
        cluster_matrix = {}
        
        # 提取两个集群之间的流量
        for (src, dst), traffic in self.current_traffic_matrix.items():
            if (src in cluster1 and dst in cluster2) or (src in cluster2 and dst in cluster1):
                cluster_matrix[(src, dst)] = traffic
        
        return cluster_matrix
    
    def get_aggregated_traffic_between_clusters(self, cluster1, cluster2):
        """
        获取两个集群之间的总流量
        
        参数:
            cluster1: 第一个集群的节点列表
            cluster2: 第二个集群的节点列表
            
        返回:
            总流量(Gbps)
        """
        total_traffic = 0.0
        
        # 计算两个集群之间的总流量
        for (src, dst), traffic in self.current_traffic_matrix.items():
            if (src in cluster1 and dst in cluster2) or (src in cluster2 and dst in cluster1):
                total_traffic += traffic
        
        return total_traffic
    
    def get_hotspot_nodes(self, top_n=10):
        """
        获取热点节点
        
        参数:
            top_n: 返回前N个热点节点
            
        返回:
            热点节点列表及其流量
        """
        # 计算每个节点的总流入和流出流量
        node_traffic = defaultdict(float)
        
        for (src, dst), traffic in self.current_traffic_matrix.items():
            node_traffic[src] += traffic  # 流出流量
            node_traffic[dst] += traffic  # 流入流量
        
        # 按流量排序
        sorted_nodes = sorted(node_traffic.items(), key=lambda x: x[1], reverse=True)
        
        # 返回前N个热点节点
        return sorted_nodes[:top_n]
