#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AllReduce流量模式
"""

import random
import numpy as np
from traffic.traffic_base import TrafficBase

class AllReduceTraffic(TrafficBase):
    """AllReduce流量模式"""
    
    def __init__(self, topology, packet_rate=0.1, packet_size=1024, 
                 group_size=16, num_groups=None):
        """
        初始化AllReduce流量模式
        
        参数:
            topology: 网络拓扑对象
            packet_rate: 每个节点每时间单位产生的数据包数量
            packet_size: 数据包大小(bytes)
            group_size: 每个AllReduce组的节点数量
            num_groups: 组数量，如果为None则自动计算
        """
        super().__init__(topology, packet_rate, packet_size)
        self.group_size = min(group_size, len(self.nodes))
        
        # 计算组数量
        if num_groups is None:
            self.num_groups = max(1, len(self.nodes) // self.group_size)
        else:
            self.num_groups = min(num_groups, len(self.nodes) // self.group_size)
        
        # 将节点分配到组
        self.groups = self._assign_nodes_to_groups()
        
        print(f"已创建 {len(self.groups)} 个AllReduce组，每组 {self.group_size} 个节点")
    
    def _assign_nodes_to_groups(self):
        """将节点分配到AllReduce组"""
        # 随机打乱节点
        nodes = list(self.nodes)
        random.shuffle(nodes)
        
        # 分配到组
        groups = []
        nodes_per_group = min(self.group_size, len(nodes) // self.num_groups)
        
        for i in range(self.num_groups):
            start_idx = i * nodes_per_group
            end_idx = start_idx + nodes_per_group
            
            if end_idx <= len(nodes):
                group = nodes[start_idx:end_idx]
                groups.append(group)
        
        return groups
    
    def generate_traffic(self, current_time, end_time):
        """
        生成AllReduce流量
        
        参数:
            current_time: 当前仿真时间
            end_time: 结束仿真时间
            
        返回:
            数据包列表
        """
        packets = []
        time_interval = end_time - current_time
        
        # AllReduce操作分为两个阶段：Reduce-Scatter和All-Gather
        # 每个节点需要与组内其他所有节点通信
        
        # 计算每个节点在这个时间段内发起的AllReduce操作数量
        operations_per_node = max(1, int(self.packet_rate * time_interval / 2))
        
        # 为每个组生成AllReduce流量
        for group in self.groups:
            for _ in range(operations_per_node):
                # 生成一个随机的开始时间
                operation_start = current_time + random.random() * (time_interval * 0.8)
                
                # 第一阶段：Reduce-Scatter
                for i, source in enumerate(group):
                    for j, destination in enumerate(group):
                        if i != j:  # 不需要自己给自己发送
                            # 计算这个数据包的大小（AllReduce中，数据包大小通常与组大小相关）
                            size = int(self.packet_size / (len(group) - 1))
                            size = max(64, size)  # 确保最小数据包大小
                            
                            # 创建数据包，添加一点随机延迟
                            start_time = operation_start + random.random() * 0.1
                            packet = self._create_packet(source, destination, size, start_time, "UDP")
                            packet.is_reduce_scatter = True
                            packets.append(packet)
                
                # 第二阶段：All-Gather (在Reduce-Scatter之后)
                for i, source in enumerate(group):
                    for j, destination in enumerate(group):
                        if i != j:
                            size = int(self.packet_size / (len(group) - 1))
                            size = max(64, size)
                            
                            # All-Gather在Reduce-Scatter之后开始
                            start_time = operation_start + 0.2 + random.random() * 0.1
                            packet = self._create_packet(source, destination, size, start_time, "UDP")
                            packet.is_all_gather = True
                            packets.append(packet)
        
        return packets
