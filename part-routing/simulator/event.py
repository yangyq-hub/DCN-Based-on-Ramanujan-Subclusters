#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
事件类，用于事件驱动仿真
"""

class Event:
    """事件基类"""
    
    def __init__(self, time, event_type, data=None):
        """
        初始化事件
        
        参数:
            time: 事件发生时间
            event_type: 事件类型
            data: 事件相关数据
        """
        self.time = time
        self.event_type = event_type
        self.data = data
    
    def __lt__(self, other):
        """比较运算符，用于事件优先级队列"""
        return self.time < other.time
    
    def __str__(self):
        """字符串表示"""
        return f"Event(time={self.time}, type={self.event_type})"

class PacketGenerationEvent(Event):
    """数据包生成事件"""
    
    def __init__(self, time, packet):
        """
        初始化数据包生成事件
        
        参数:
            time: 事件发生时间
            packet: 数据包对象
        """
        super().__init__(time, "PACKET_GENERATION", packet)
        self.packet = packet
    
    def __str__(self):
        """字符串表示"""
        return f"PacketGenerationEvent(time={self.time}, packet={self.packet.packet_id})"

class PacketArrivalEvent(Event):
    """数据包到达事件"""
    
    def __init__(self, time, packet, node):
        """
        初始化数据包到达事件
        
        参数:
            time: 事件发生时间
            packet: 数据包对象
            node: 到达的节点
        """
        super().__init__(time, "PACKET_ARRIVAL", packet)
        self.packet = packet
        self.node = node
    
    def __str__(self):
        """字符串表示"""
        return f"PacketArrivalEvent(time={self.time}, packet={self.packet.packet_id}, node={self.node})"

class PacketDepartureEvent(Event):
    """数据包离开事件"""
    
    def __init__(self, time, packet, node, next_node):
        """
        初始化数据包离开事件
        
        参数:
            time: 事件发生时间
            packet: 数据包对象
            node: 当前节点
            next_node: 下一跳节点
        """
        super().__init__(time, "PACKET_DEPARTURE", packet)
        self.packet = packet
        self.node = node
        self.next_node = next_node
    
    def __str__(self):
        """字符串表示"""
        return f"PacketDepartureEvent(time={self.time}, packet={self.packet.packet_id}, node={self.node}, next={self.next_node})"

class PacketDeliveryEvent(Event):
    """数据包送达事件"""
    
    def __init__(self, time, packet):
        """
        初始化数据包送达事件
        
        参数:
            time: 事件发生时间
            packet: 数据包对象
        """
        super().__init__(time, "PACKET_DELIVERY", packet)
        self.packet = packet
    
    def __str__(self):
        """字符串表示"""
        return f"PacketDeliveryEvent(time={self.time}, packet={self.packet.packet_id})"

class LinkCongestionEvent(Event):
    """链路拥塞事件"""
    
    def __init__(self, time, source, destination, congestion_level):
        """
        初始化链路拥塞事件
        
        参数:
            time: 事件发生时间
            source: 源节点
            destination: 目标节点
            congestion_level: 拥塞级别
        """
        super().__init__(time, "LINK_CONGESTION", None)
        self.source = source
        self.destination = destination
        self.congestion_level = congestion_level
    
    def __str__(self):
        """字符串表示"""
        return f"LinkCongestionEvent(time={self.time}, link=({self.source},{self.destination}), level={self.congestion_level})"

class TrafficGenerationEvent(Event):
    """流量生成事件"""
    
    def __init__(self, time, interval):
        """
        初始化流量生成事件
        
        参数:
            time: 事件发生时间
            interval: 流量生成间隔
        """
        super().__init__(time, "TRAFFIC_GENERATION", None)
        self.interval = interval
    
    def __str__(self):
        """字符串表示"""
        return f"TrafficGenerationEvent(time={self.time}, interval={self.interval})"

# 新增事件类型：链路空闲事件
class LinkIdleEvent(Event):
    """链路空闲事件类"""
    
    def __init__(self, time, link):
        """
        初始化事件
        
        参数:
            time: 事件时间
            link: 链路对象
        """
        super().__init__(time, "LINK_IDLE", None)
        self.link = link
    
    def __str__(self):
        """字符串表示"""
        return f"LinkIdleEvent(time={self.time})"
    
class TopologyReconfigurationEvent:
    """拓扑重构事件"""
    
    def __init__(self, time, reconfig_interval, reconfig_delay=0.1):
        """
        初始化拓扑重构事件
        
        参数:
            time: 事件发生时间
            reconfig_interval: 重构间隔时间
            reconfig_delay: 重构延迟时间(秒)
        """
        self.time = time
        self.reconfig_interval = reconfig_interval
        self.reconfig_delay = reconfig_delay
    
    def __lt__(self, other):
        return self.time < other.time


class ReconfigurationCompletionEvent:
    """重构完成事件"""
    
    def __init__(self, time, new_topology):
        """
        初始化重构完成事件
        
        参数:
            time: 事件发生时间
            new_topology: 重构后的拓扑
        """
        self.time = time
        self.new_topology = new_topology
    
    def __lt__(self, other):
        return self.time < other.time


class RouteRecalculationEvent:
    """路由重新计算事件"""
    
    def __init__(self, time):
        """
        初始化路由重新计算事件
        
        参数:
            time: 事件发生时间
        """
        self.time = time
    
    def __lt__(self, other):
        return self.time < other.time
