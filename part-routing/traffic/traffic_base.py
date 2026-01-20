#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
流量模式基类
"""

from abc import ABC, abstractmethod
import random
import uuid

class TrafficBase(ABC):
    """流量模式基类"""
    
    def __init__(self, topology, packet_rate=0.1, packet_size=1024):
        """
        初始化流量模式
        
        参数:
            topology: 网络拓扑对象
            packet_rate: 每个节点每时间单位产生的数据包数量
            packet_size: 数据包大小(bytes)
        """
        self.topology = topology
        self.graph = topology.get_graph()
        self.nodes = list(self.graph.nodes())
        self.packet_rate = packet_rate
        self.packet_size = packet_size
        self.flow_counter = 0
    
    def _generate_flow_id(self):
        """生成唯一的流ID"""
        self.flow_counter += 1
        return f"flow-{self.flow_counter}"
    
    @abstractmethod
    def generate_traffic(self, current_time, end_time):
        """
        生成流量
        
        参数:
            current_time: 当前仿真时间
            end_time: 结束仿真时间
            
        返回:
            数据包列表
        """
        pass
    
    def _create_packet(self, source, destination, size, start_time, protocol="TCP"):
        """
        创建数据包
        
        参数:
            source: 源节点
            destination: 目标节点
            size: 数据包大小(bytes)
            start_time: 发送时间
            protocol: 协议类型
            
        返回:
            数据包对象
        """
        from simulator.packet import Packet
        
        # 生成随机端口
        source_port = random.randint(1024, 65535)
        destination_port = random.randint(1024, 65535)
        
        # 生成唯一的包ID
        packet_id = str(uuid.uuid4())
        
        # 生成流ID
        flow_id = self._generate_flow_id()
        
        return Packet(
            packet_id=packet_id,
            flow_id=flow_id,
            source=source,
            destination=destination,
            size=size,
            start_time=start_time,
            protocol=protocol,
            source_port=source_port,
            destination_port=destination_port
        )
