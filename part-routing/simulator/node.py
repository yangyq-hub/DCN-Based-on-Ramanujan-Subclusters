#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
节点类，模拟网络节点
"""

import random
from collections import defaultdict

class Node:
    """节点类"""
    
    def __init__(self, node_id, processing_delay=0.01, is_ocs_node=False):
        """
        初始化节点
        
        参数:
            node_id: 节点ID
            processing_delay: 处理延迟(ms)
            is_ocs_node: 是否为OCS节点
        """
        self.node_id = node_id
        self.processing_delay = processing_delay
        self.is_ocs_node = is_ocs_node
        
        # 节点统计
        self.packets_sent = 0
        self.packets_received = 0
        self.packets_dropped = 0
        self.packets_forwarded = 0
        
        # 流量统计
        self.traffic_sent = defaultdict(float)  # 发送到各目的地的流量 {dest_id: bytes}
        self.traffic_received = defaultdict(float)  # 从各源接收的流量 {src_id: bytes}
        
        # 节点状态
        self.links = {}  # 连接到该节点的链路 {dest_id: link}
        self.is_failed = False  # 节点是否故障
        self.failure_probability = 0.0  # 故障概率
        
        # OCS相关
        self.ocs_links = set()  # OCS链路的目的节点ID集合
        self.in_reconfiguration = False  # 是否正在重构
    
    def add_link(self, destination, link, is_ocs_link=False):
        """
        添加链路
        
        参数:
            destination: 目标节点ID
            link: 链路对象
            is_ocs_link: 是否为OCS链路
        """
        self.links[destination] = link
        if is_ocs_link:
            self.ocs_links.add(destination)
    
    def remove_link(self, destination):
        """
        移除链路
        
        参数:
            destination: 目标节点ID
            
        返回:
            被移除的链路对象，如果不存在则返回None
        """
        if destination in self.links:
            link = self.links.pop(destination)
            if destination in self.ocs_links:
                self.ocs_links.remove(destination)
            return link
        return None
    
    def process_packet(self, packet, current_time):
        """
        处理数据包
        
        参数:
            packet: 数据包对象
            current_time: 当前时间
            
        返回:
            处理完成时间
        """
        # 检查节点是否故障
        if self.is_failed:
            self.packets_dropped += 1
            packet.mark_dropped("NODE_FAILURE")
            return 0
        
        # 检查是否正在重构（如果是OCS节点）
        if self.is_ocs_node and self.in_reconfiguration:
            self.packets_dropped += 1
            packet.mark_dropped("OCS_RECONFIGURATION")
            return 0
        
        # 添加处理延迟
        processing_time = self.processing_delay * (0.8 + 0.4 * random.random())  # 随机波动
        packet.processing_delay += processing_time
        
        # 更新统计信息
        if packet.source == self.node_id:
            self.packets_sent += 1
            self.traffic_sent[packet.destination] += packet.size
        elif packet.destination == self.node_id:
            self.packets_received += 1
            self.traffic_received[packet.source] += packet.size
        else:
            self.packets_forwarded += 1
        
        return processing_time
    
    def send_packet(self, packet, next_hop, current_time):
        """
        发送数据包
        
        参数:
            packet: 数据包对象
            next_hop: 下一跳节点ID
            current_time: 当前时间
            
        返回:
            (是否成功, 预计到达时间)
        """
        # 检查节点是否故障
        if self.is_failed:
            self.packets_dropped += 1
            packet.mark_dropped("NODE_FAILURE")
            return False, None
        
        # 检查是否正在重构（如果是OCS节点且下一跳是通过OCS）
        if self.is_ocs_node and next_hop in self.ocs_links and self.in_reconfiguration:
            self.packets_dropped += 1
            packet.mark_dropped("OCS_RECONFIGURATION")
            return False, None
            
        # 检查链路是否存在
        if next_hop not in self.links:
            self.packets_dropped += 1
            packet.mark_dropped("NO_ROUTE")
            return False, None
        
        # 获取链路并发送数据包
        link = self.links[next_hop]
        success, arrival_time = link.send_packet(packet, current_time)
        
        if not success:
            self.packets_dropped += 1
        
        return success, arrival_time
    
    def simulate_failure(self, probability=0.0001):
        """
        模拟节点故障
        
        参数:
            probability: 故障概率
            
        返回:
            是否发生故障
        """
        self.failure_probability = probability
        if random.random() < probability:
            self.is_failed = True
            return True
        return False
    
    def repair(self):
        """修复节点故障"""
        self.is_failed = False
    
    def start_reconfiguration(self):
        """开始OCS重构"""
        if self.is_ocs_node:
            self.in_reconfiguration = True
            return True
        return False
    
    def end_reconfiguration(self):
        """结束OCS重构"""
        if self.is_ocs_node:
            self.in_reconfiguration = False
            return True
        return False
    
    def get_traffic_stats(self):
        """获取流量统计信息"""
        total_sent = sum(self.traffic_sent.values())
        total_received = sum(self.traffic_received.values())
        
        # 获取发送流量最大的目的地
        top_destinations = sorted(self.traffic_sent.items(), key=lambda x: x[1], reverse=True)[:5]
        
        # 获取接收流量最大的源
        top_sources = sorted(self.traffic_received.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            'total_sent_bytes': total_sent,
            'total_received_bytes': total_received,
            'packets_sent': self.packets_sent,
            'packets_received': self.packets_received,
            'packets_forwarded': self.packets_forwarded,
            'packets_dropped': self.packets_dropped,
            'top_destinations': top_destinations,
            'top_sources': top_sources,
            'ocs_links_count': len(self.ocs_links)
        }
    
    def clear_stats(self):
        """清除统计信息"""
        self.packets_sent = 0
        self.packets_received = 0
        self.packets_dropped = 0
        self.packets_forwarded = 0
        self.traffic_sent = defaultdict(float)
        self.traffic_received = defaultdict(float)
    
    def __str__(self):
        """字符串表示"""
        ocs_status = "OCS" if self.is_ocs_node else "Regular"
        return f"Node({self.node_id}, {ocs_status})"
