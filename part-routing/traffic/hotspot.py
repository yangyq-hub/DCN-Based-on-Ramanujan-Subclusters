#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
热点流量模式
"""

import random
import numpy as np
from traffic.traffic_base import TrafficBase

class HotspotTraffic(TrafficBase):
    """热点流量模式"""
    
    def __init__(self, topology, packet_rate=0.1, packet_size=1024, 
                 hotspot_nodes_pct=0.1, hotspot_traffic_pct=0.9):
        """
        初始化热点流量模式
        
        参数:
            topology: 网络拓扑对象
            packet_rate: 每个节点每时间单位产生的数据包数量
            packet_size: 数据包大小(bytes)
            hotspot_nodes_pct: 热点节点占总节点的比例
            hotspot_traffic_pct: 热点流量占总流量的比例
        """
        super().__init__(topology, packet_rate, packet_size)
        self.hotspot_nodes_pct = hotspot_nodes_pct
        self.hotspot_traffic_pct = hotspot_traffic_pct
        
        # 选择热点节点
        num_hotspots = max(1, int(len(self.nodes) * hotspot_nodes_pct))
        self.hotspot_nodes = random.sample(self.nodes, num_hotspots)
        self.packet_accumulator = 0.0  # 添加累积器以处理小数部分
        
        print(f"已选择 {len(self.hotspot_nodes)} 个热点节点: {self.hotspot_nodes}")
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
                    if random.random() < self.hotspot_traffic_pct:
                        # 热点流量：目标是热点节点
                        destination = random.choice(self.hotspot_nodes)
                        # 确保源不是目标
                        while source == destination:
                            destination = random.choice(self.hotspot_nodes)
                    else:
                        # 普通流量：随机选择非热点目标
                        non_hotspot = [n for n in self.nodes if n != source and n not in self.hotspot_nodes]
                        if non_hotspot:
                            destination = random.choice(non_hotspot)
                        else:
                            # 如果没有非热点节点可选，就随机选择一个不是自己的节点
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
        
        return packets
 