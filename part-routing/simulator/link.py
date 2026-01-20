#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
链路类，模拟网络链路
"""

import random
import numpy as np
from collections import deque
from simulator.event import LinkIdleEvent
class Link:
    """链路类"""
    
    def __init__(self, source, destination, capacity, delay, buffer_size, simulator=None):
        """
        初始化链路
        
        参数:
            source: 源节点
            destination: 目标节点
            capacity: 链路容量(Gbps)
            delay: 链路延迟(ms)
            buffer_size: 缓冲区大小(KB)
            simulator: 仿真器引用，用于调度事件
        """
        self.source = source
        self.destination = destination
        self.capacity = capacity  # Gbps
        self.base_delay = delay  # ms
        self.buffer_size = buffer_size * 1024*2   # 转换为bytes
        self.simulator = simulator  # 仿真器引用
        
        # 链路状态
        self.queue = deque()  # 数据包队列
        self.queue_size = 0  # 当前队列大小(bytes)
        self.busy_until = 0  # 链路忙碌直到的时间
        self.packets_in_transit = []  # 正在传输的数据包
        self.completed_packets = []  # 已完成传输的数据包
        self.current_packet = None  # 当前正在传输的数据包
        
        # 链路统计
        self.packets_sent = 0
        self.packets_dropped = 0
        self.bytes_sent = 0
        self.utilization = 0.0
        self.congestion_level = 0.0
        self.max_queue_size = 0
        self.total_queuing_delay = 0.0
        
        # 链路动态属性
        self.jitter = 0.0  # 抖动(ms)
        self.error_rate = 0.0001  # 错误率
        self.failure_probability = 0.0  # 故障概率
        self.is_failed = False  # 是否故障
    
    def set_simulator(self, simulator):
        """设置仿真器引用"""
        self.simulator = simulator
    
    def send_packet(self, packet, current_time):
        """
        发送数据包（模拟器调用的接口）
        
        参数:
            packet: 数据包对象
            current_time: 当前时间
            
        返回:
            (成功与否, 预计到达时间)
        """
        # 检查链路是否故障
        if self.is_failed:
            self.packets_dropped += 1
            packet.mark_dropped("LINK_FAILURE")
            return False, None
        
        # 检查链路是否忙碌
        if current_time < self.busy_until:
            # 链路忙碌，尝试将数据包加入队列
            if self.queue_size + packet.size > self.buffer_size:
                # 缓冲区溢出，丢弃数据包
                self.packets_dropped += 1
                packet.mark_dropped("BUFFER_OVERFLOW")
                return False, None
            else:
                # 将数据包加入队列
                self.queue.append((packet, current_time))
                self.queue_size += packet.size
                self.max_queue_size = max(self.max_queue_size, self.queue_size)
                
                return True, None
        
        # 链路空闲，直接发送数据包
        return self._transmit_packet(packet, current_time)
    
    def _transmit_packet(self, packet, current_time):
        """
        实际传输数据包（内部方法）
        
        参数:
            packet: 数据包对象
            current_time: 当前时间
            
        返回:
            (成功与否, 到达时间)
        """
        # 计算传输延迟 (size in bytes / capacity in Gbps -> ms)
        transmission_delay = (packet.size * 8) / (self.capacity * 1000)
        
        # 计算传播延迟 (基础延迟 + 抖动)
        self.jitter = np.random.exponential(0.001)  # 随机抖动
        propagation_delay = self.base_delay/100 + self.jitter
        
        # 计算总延迟
        total_delay = transmission_delay + propagation_delay
        
        # 计算数据包到达目的地的时间
        completion_time = current_time + total_delay
        
        # 更新链路状态
        self.busy_until = current_time + transmission_delay  # 链路只在传输时间内忙碌
        self.current_packet = packet
        self.packets_in_transit.append((packet, completion_time))
        
        # 更新数据包延迟信息
        packet.transmission_delay += transmission_delay
        packet.propagation_delay += propagation_delay
        
        # 更新统计信息
        self.packets_sent += 1
        self.bytes_sent += packet.size
        
        # 计算链路利用率
        self.update_utilization(current_time)
        
        # 计算拥塞级别 (0-1)
        self.congestion_level = self.queue_size / self.buffer_size if self.buffer_size > 0 else 0
        
        # 随机错误
        if random.random() < self.error_rate:
            packet.mark_dropped("ERROR")
            return False, None
        
        # 如果链路将在未来空闲，并且队列不为空，调度下一个数据包的传输
        if self.simulator and self.queue and self.busy_until > current_time:
            # 调度链路空闲事件
            self.simulator.schedule_event(LinkIdleEvent(self.busy_until, self))
        
        return True, completion_time
    
    def process_next_packet(self, current_time):
        """
        处理队列中的下一个数据包
        
        参数:
            current_time: 当前时间
            
        返回:
            (数据包, 传输完成时间) 或 (None, None)
        """
        # 检查链路是否忙碌
        if current_time < self.busy_until:
            return None, None
        
        # 检查队列是否为空
        if not self.queue:
            return None, None
        
        # 取出队首数据包
        packet, enqueue_time = self.queue.popleft()
        self.queue_size -= packet.size
        
        # 计算排队延迟
        queuing_delay = current_time - enqueue_time
        packet.queuing_delay += queuing_delay
        self.total_queuing_delay += queuing_delay
        
        # 传输数据包
        success, completion_time = self._transmit_packet(packet, current_time)
        
        if not success:
            return None, None
        
        return packet, completion_time
    
    def update(self, current_time):
        """
        更新链路状态
        
        参数:
            current_time: 当前时间
            
        返回:
            已完成传输的数据包列表
        """
        # 检查已完成传输的数据包
        completed = []
        remaining = []
        
        for packet, completion_time in self.packets_in_transit:
            if current_time >= completion_time:
                completed.append(packet)
                self.completed_packets.append(packet)
                if packet == self.current_packet:
                    self.current_packet = None
            else:
                remaining.append((packet, completion_time))
        
        self.packets_in_transit = remaining
        
        # 更新链路利用率
        self.update_utilization(current_time)
        
        # 模拟链路故障
        if not self.is_failed and random.random() < self.failure_probability:
            self.is_failed = True
        
        # 如果链路空闲且队列不为空，处理下一个数据包
        if current_time >= self.busy_until and not self.is_failed and self.queue:
            self.process_next_packet(current_time)
        
        return completed
    
    def get_completed_packets(self):
        """
        获取并清空已完成传输的数据包列表
        
        返回:
            已完成传输的数据包列表
        """
        completed = self.completed_packets
        self.completed_packets = []
        return completed
    
    def update_utilization(self, current_time, window=100):
        """
        更新链路利用率
        
        参数:
            current_time: 当前时间
            window: 计算窗口大小(ms)
        """
        # 计算过去window ms内的链路利用率
        busy_time = 0
        if self.busy_until > current_time - window:
            busy_time = min(self.busy_until, current_time) - max(self.busy_until - window, current_time - window)
        
        self.utilization = busy_time / window if window > 0 else 0
        
        # 清理过期的传输记录
        self.packets_in_transit = [(p, t) for p, t in self.packets_in_transit if t > current_time - window]
        
    def get_utilization(self):
        """获取链路利用率"""
        return self.utilization
    
    def get_current_delay(self):
        """获取当前链路延迟"""
        return self.base_delay + self.jitter + (self.congestion_level * 0.1)  # 拥塞增加延迟
    
    def get_queue_length(self):
        """获取当前队列长度（数据包数量）"""
        return len(self.queue)
    
    def get_queue_size(self):
        """获取当前队列大小（字节）"""
        return self.queue_size
    
    def simulate_failure(self, probability=0.0001):
        """
        模拟链路故障
        
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
        """修复链路故障"""
        self.is_failed = False
    
    def __str__(self):
        """字符串表示"""
        return f"Link({self.source}->{self.destination}, {self.capacity}Gbps, {self.base_delay}ms)"


