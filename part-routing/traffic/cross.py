#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
跨组热点流量模式 - 专为两个Ramanujan拓扑之间的热点节点通信设计
"""

import random
import numpy as np
from collections import defaultdict
from traffic.traffic_base import TrafficBase

class CrossClusterHotspotTraffic(TrafficBase):
    """跨组热点流量模式 - 专为两个Ramanujan拓扑之间的热点节点通信设计"""
    
    def __init__(self, topology, packet_rate=0.1, packet_size=1024, traffic_window=10.0, 
                 hotspot_count_ratio=0.2, hotspot_change_interval=7010):
        """
        初始化跨组热点流量模式
        
        参数:
            topology: 网络拓扑对象
            packet_rate: 每毫秒每节点产生的数据包数量
            packet_size: 平均数据包大小(字节)
            traffic_window: 流量统计窗口大小(秒)
            hotspot_count_ratio: 热点节点占总节点的比例
            hotspot_change_interval: 热点变化间隔(毫秒)
        """
        super().__init__(topology, packet_rate, packet_size)
        self.packet_accumulator = 0.0  # 添加累积器以处理小数部分
        
        # 获取两个集群的节点
        self.tor1_nodes = topology.get_tor1_nodes()
        self.tor2_nodes = topology.get_tor2_nodes()
        
        # 流量矩阵 - 直接记录源目的地和流量
        self.traffic_window = traffic_window * 1000  # 转换为毫秒
        self.current_traffic_matrix = defaultdict(float)  # 当前流量矩阵 {(src, dst): traffic_in_gbps}
        self.last_matrix_update = 0.0  # 上次更新流量矩阵的时间
        
        # 热点相关参数
        self.hotspot_count_ratio = hotspot_count_ratio  # 热点节点占总节点的比例
        self.hotspot_change_interval = hotspot_change_interval  # 热点变化间隔(毫秒)
        self.last_hotspot_change_time = 0.0  # 上次热点变化时间
        
        # 当前热点
        self.current_hotspots_tor1 = []  # 第一个集群中的热点节点
        self.current_hotspots_tor2 = []  # 第二个集群中的热点节点
        
        # 初始化热点
        self._select_new_hotspots()
    
    def _select_new_hotspots(self):
        """选择新的热点节点并清空流量矩阵"""
        # 清空流量矩阵
        self.current_traffic_matrix.clear()
        print("热点变化，流量矩阵已清空")
        
        # 在每个集群中选择一部分节点作为热点
        hotspot_count_tor1 = max(1, int(len(self.tor1_nodes) * self.hotspot_count_ratio))
        hotspot_count_tor2 = max(1, int(len(self.tor2_nodes) * self.hotspot_count_ratio))
        
        self.current_hotspots_tor1 = random.sample(self.tor1_nodes, hotspot_count_tor1)
        self.current_hotspots_tor2 = random.sample(self.tor2_nodes, hotspot_count_tor2)
        
        print(f"新热点已选择: TOR1集群热点数: {len(self.current_hotspots_tor1)}, TOR2集群热点数: {len(self.current_hotspots_tor2)}")
        print(f"TOR1热点: {self.current_hotspots_tor1}")
        print(f"TOR2热点: {self.current_hotspots_tor2}")
    
    def generate_traffic(self, current_time, end_time):
        """
        生成热点之间的跨组流量
        
        参数:
            current_time: 当前仿真时间
            end_time: 结束仿真时间
            
        返回:
            数据包列表
        """
        packets = []
        
        # 检查是否需要更新热点
        if current_time - self.last_hotspot_change_time >= self.hotspot_change_interval:
            self._select_new_hotspots()  # 这里会清空流量矩阵
            self.last_hotspot_change_time = current_time
            print(f"时间 {current_time}ms: 热点已更新")
        
        # 计算这个时间段内每个热点节点产生的数据包数量
        time_interval = end_time - current_time
        
        # 临时存储本次生成的流量
        current_traffic = defaultdict(float)
        
        # 第一个集群的热点向第二个集群的热点发送数据包
        for source in self.current_hotspots_tor1:
            # 更新累积器
            self.packet_accumulator += self.packet_rate * time_interval * 5  # 热点节点产生更多流量
            packets_to_generate = int(self.packet_accumulator)
            self.packet_accumulator -= packets_to_generate
            
            # 如果累积器不足以生成完整数据包，使用概率方法决定是否生成
            if packets_to_generate == 0 and self.packet_accumulator > 0:
                if random.random() < self.packet_accumulator:
                    packets_to_generate = 1
                    self.packet_accumulator = 0
            
            # 为当前热点节点生成数据包
            for _ in range(packets_to_generate):
                # 选择第二个集群中的一个热点作为目的地
                if self.current_hotspots_tor2:
                    destination = random.choice(self.current_hotspots_tor2)
                    
                    # 生成数据包大小，热点流量的数据包较大
                    size = int(np.random.normal(self.packet_size * 2, self.packet_size * 0.3))
                    size = max(64, size)  # 确保最小数据包大小为64字节
                    
                    # 随机生成发送时间，在当前时间和结束时间之间
                    start_time = current_time + random.random() * time_interval
                    
                    # 创建数据包
                    packet = self._create_packet(source, destination, size, start_time)
                    packets.append(packet)
                    
                    # 直接累加流量 (转换为Gbps)
                    bits = size * 8
                    gbits = bits / 1e9
                    current_traffic[(source, destination)] += gbits
        
        # 第二个集群的热点向第一个集群的热点发送数据包
        for source in self.current_hotspots_tor2:
            # 更新累积器
            self.packet_accumulator += self.packet_rate * time_interval * 5  # 热点节点产生更多流量
            packets_to_generate = int(self.packet_accumulator)
            self.packet_accumulator -= packets_to_generate
            
            # 如果累积器不足以生成完整数据包，使用概率方法决定是否生成
            if packets_to_generate == 0 and self.packet_accumulator > 0:
                if random.random() < self.packet_accumulator:
                    packets_to_generate = 1
                    self.packet_accumulator = 0
            
            # 为当前热点节点生成数据包
            for _ in range(packets_to_generate):
                # 选择第一个集群中的一个热点作为目的地
                if self.current_hotspots_tor1:
                    destination = random.choice(self.current_hotspots_tor1)
                    
                    # 生成数据包大小，热点流量的数据包较大
                    size = int(np.random.normal(self.packet_size * 2, self.packet_size * 0.3))
                    size = max(64, size)  # 确保最小数据包大小为64字节
                    
                    # 随机生成发送时间，在当前时间和结束时间之间
                    start_time = current_time + random.random() * time_interval
                    
                    # 创建数据包
                    packet = self._create_packet(source, destination, size, start_time)
                    packets.append(packet)
                    
                    # 直接累加流量 (转换为Gbps)
                    bits = size * 8
                    gbits = bits / 1e9
                    current_traffic[(source, destination)] += gbits
        
        # 更新流量矩阵 - 将当前时间段内生成的流量添加到流量矩阵中
        # 将流量转换为Gbps (每秒千兆比特)
        time_in_seconds = time_interval / 1000
        for (src, dst), traffic in current_traffic.items():
            # 转换为Gbps
            traffic_gbps = traffic / time_in_seconds
            
            # 更新流量矩阵，使用最新值而不是累加
            # 这样可以确保流量矩阵反映当前状态
            self.current_traffic_matrix[(src, dst)] = traffic_gbps
        
        # 如果距离上次更新流量矩阵超过1秒，打印统计信息
        if current_time - self.last_matrix_update >= 1000:
            self._print_traffic_stats()
            self.last_matrix_update = current_time
        
        return packets
    
    def _print_traffic_stats(self):
        """打印流量统计信息"""
        if not self.current_traffic_matrix:
            print("流量矩阵为空")
            return
            
        total_traffic = sum(self.current_traffic_matrix.values())
        max_traffic = max(self.current_traffic_matrix.values()) if self.current_traffic_matrix else 0
        num_flows = len(self.current_traffic_matrix)
        
        # 计算热点之间的流量
        hotspot_traffic = 0
        for (src, dst), traffic in self.current_traffic_matrix.items():
            if ((src in self.current_hotspots_tor1 and dst in self.current_hotspots_tor2) or 
                (src in self.current_hotspots_tor2 and dst in self.current_hotspots_tor1)):
                hotspot_traffic += traffic
        
        print(f"流量矩阵统计: {num_flows}条流, 总流量: {total_traffic:.3f}Gbps, "
              f"热点间流量: {hotspot_traffic:.3f}Gbps, 最大流: {max_traffic:.3f}Gbps")
    
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
    
    def get_hotspot_nodes(self):
        """
        获取当前热点节点
        
        返回:
            当前热点节点字典，按集群分组
        """
        return {
            'tor1_hotspots': self.current_hotspots_tor1,
            'tor2_hotspots': self.current_hotspots_tor2
        }
    
    def get_hotspot_traffic_percentage(self):
        """
        计算热点流量占总流量的百分比
        
        返回:
            热点流量百分比
        """
        total_traffic = sum(self.current_traffic_matrix.values())
        if total_traffic == 0:
            return 0
        
        hotspot_traffic = 0
        for (src, dst), traffic in self.current_traffic_matrix.items():
            if ((src in self.current_hotspots_tor1 and dst in self.current_hotspots_tor2) or 
                (src in self.current_hotspots_tor2 and dst in self.current_hotspots_tor1)):
                hotspot_traffic += traffic
        
        return (hotspot_traffic / total_traffic) * 100 if total_traffic > 0 else 0
