#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据包类
"""

import uuid

class Packet:
    """数据包类"""
    
    def __init__(self, packet_id=None, flow_id=None, source=None, destination=None, 
                 size=1024, start_time=0, protocol="TCP", source_port=0, destination_port=0):
        """
        初始化数据包
        
        参数:
            packet_id: 数据包ID，如果为None则自动生成
            flow_id: 流ID，如果为None则自动生成
            source: 源节点
            destination: 目标节点
            size: 数据包大小(bytes)
            start_time: 发送时间
            protocol: 协议类型
            source_port: 源端口
            destination_port: 目标端口
        """
        self.packet_id = packet_id if packet_id else str(uuid.uuid4())
        self.flow_id = flow_id if flow_id else str(uuid.uuid4())
        self.source = source
        self.destination = destination
        self.size = size
        self.start_time = start_time
        self.protocol = protocol
        self.source_port = source_port
        self.destination_port = destination_port
        
        # 跟踪数据包的路径和时间
        self.path = []
        self.hops = 0
        self.arrival_time = None
        self.current_node = None
        self.next_node = None

                # 延迟和拥塞相关属性
        self.queuing_delay = 0.0  # 排队延迟
        self.transmission_delay = 0.0  # 传输延迟
        self.propagation_delay = 0.0  # 传播延迟
        self.processing_delay = 0.0  # 处理延迟
        self.total_delay = 0.0  # 总延迟
        
        # 拥塞和丢包相关
        self.dropped = False  # 是否被丢弃
        self.drop_reason = None  # 丢包原因
        self.retransmitted = False  # 是否重传
        self.congestion_experienced = False  # 是否经历拥塞
        
        # 流量类型标记
        self.is_reduce_scatter = False  # 是否为Reduce-Scatter阶段
        self.is_all_gather = False  # 是否为All-Gather阶段
    
    def add_hop(self, node, time):
        """
        添加一个跳转记录
        
        参数:
            node: 节点ID
            time: 到达时间
        """
        self.path.append((node, time))
        self.hops += 1
        self.current_node = node
    
    def mark_delivered(self, time):
        """
        标记数据包已送达
        
        参数:
            time: 送达时间
        """
        self.arrival_time = time
        
        # 创建消息内容
        message = f"Packet {self.packet_id} delivered at {time}, total delay:{time-self.start_time}"
        
        # 将消息写入文件
        with open("packet_delivery.log", "a") as log_file:
            log_file.write(message + "\n")
        
        self.total_delay = time - self.start_time

    
    def mark_dropped(self, reason):
        """
        标记数据包已丢弃
        
        参数:
            reason: 丢弃原因
        """
        self.dropped = True
        self.drop_reason = reason
        print(reason)

    
    def get_five_tuple(self):
        """获取五元组标识"""
        return (self.source, self.source_port, self.destination, self.destination_port, self.protocol)
    
    def __str__(self):
        """字符串表示"""
        return f"Packet(id={self.packet_id}, flow={self.flow_id}, {self.source}->{self.destination}, size={self.size}B)"

