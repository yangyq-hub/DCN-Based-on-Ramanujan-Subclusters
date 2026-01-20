#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
事件驱动网络仿真器
"""

import heapq
import time
import numpy as np
import pandas as pd
from tqdm import tqdm

from simulator.event import *
from simulator.node import Node
from simulator.link import Link

class NetworkSimulator:
    """事件驱动网络仿真器"""
    
    def __init__(self, topology, routing, traffic, dynamic_topology=False, 
             reconfig_interval=10.0, reconfig_delay=0.1):     # 重构延迟100毫秒):
        """
        初始化仿真器
        
        参数:
            topology: 网络拓扑对象
            routing: 路由策略对象
            traffic: 流量模式对象
        """
        print(traffic)
        self.topology = topology
        self.routing = routing
        self.traffic = traffic
        
        # OCS重构相关参数
        self.dynamic_topology = dynamic_topology
        self.reconfig_interval = reconfig_interval
        self.reconfig_delay = reconfig_delay
        self.in_reconfiguration = False
        self.reconfig_count = 0
        self.reconfig_start_times = []
        self.reconfig_end_times = []
        
        # 仿真状态
        self.current_time = 0.0
        self.event_queue = []
        self.nodes = {}
        self.links = {}
        self.packets = {}
        self.delivered_packets = []
        self.dropped_packets = []
        
        # 仿真统计
        self.total_packets = 0
        self.delivered_count = 0
        self.dropped_count = 0
        self.total_hops = 0
        self.total_delay = 0.0
        self.max_delay = 0.0
        self.min_delay = float('inf')
        self.throughput = 0.0
        self.link_utilization = {}
        self.congestion_levels = {}
        
        # 仿真结束时间
        self.simulation_end_time = 0.0
        
        # 初始化仿真环境
        self._initialize_environment()
    
    def _initialize_environment(self):
        """初始化仿真环境"""
        print("初始化仿真环境...")
        
        # 创建节点
        for node_id in self.topology.get_nodes():
            self.nodes[node_id] = Node(node_id)
        
        # 创建链路
        for u, v in self.topology.get_edges():
            capacity = self.topology.get_link_capacity(u, v)
            delay = self.topology.get_link_delay(u, v)
            buffer = self.topology.get_link_buffer(u, v)
            
            # 创建双向链路，并传入仿真器引用
            link_uv = Link(u, v, capacity, delay, buffer, self)
            link_vu = Link(v, u, capacity, delay, buffer, self)
            
            # 添加到链路字典
            self.links[(u, v)] = link_uv
            self.links[(v, u)] = link_vu
            
            # 将链路添加到节点
            self.nodes[u].add_link(v, link_uv)
            self.nodes[v].add_link(u, link_vu)
            
            # 初始化链路利用率和拥塞级别统计
            self.link_utilization[(u, v)] = 0.0
            self.link_utilization[(v, u)] = 0.0
            self.congestion_levels[(u, v)] = 0.0
            self.congestion_levels[(v, u)] = 0.0
        
        print(f"初始化完成: {len(self.nodes)}个节点, {len(self.links)}条链路")
    
    def schedule_event(self, event):
        """
        调度事件
        
        参数:
            event: 事件对象
        """
        heapq.heappush(self.event_queue, event)
    
    def run(self, simulation_time, traffic_interval=10.0, show_progress=True):
        """
        运行仿真
        
        参数:
            simulation_time: 仿真时间(ms)
            traffic_interval: 流量生成间隔(ms)
            show_progress: 是否显示进度条
            
        返回:
            仿真结果指标字典
        """
        print(f"开始仿真, 时长: {simulation_time}ms")
        start_real_time = time.time()
        
        # 设置仿真结束时间
        self.simulation_end_time = simulation_time
        
        # 调度第一个流量生成事件
        first_traffic_event = TrafficGenerationEvent(0.0, traffic_interval)
        self.schedule_event(first_traffic_event)
        
        if self.dynamic_topology:
            first_reconfig_event = TopologyReconfigurationEvent(0.0, self.reconfig_interval, self.reconfig_delay)
            self.schedule_event(first_reconfig_event)
        
        # 进度条
        if show_progress:
            pbar = tqdm(total=simulation_time, desc="仿真进度")
            last_update = 0
        
        # 主事件循环
        while self.event_queue:
            # 处理下一个事件
            event = heapq.heappop(self.event_queue)
                  
            # 更新当前时间
            old_time = self.current_time
            self.current_time = event.time
            
            # 更新进度条
            if show_progress and int(self.current_time) > last_update:
                pbar.update(int(self.current_time) - last_update)
                last_update = int(self.current_time)
            
            # 处理事件
            if isinstance(event, TrafficGenerationEvent):
                self._handle_traffic_generation(event)
            elif isinstance(event, PacketGenerationEvent):
                self._handle_packet_generation(event)
            elif isinstance(event, PacketArrivalEvent):
                self._handle_packet_arrival(event)
            elif isinstance(event, PacketDepartureEvent):
                self._handle_packet_departure(event)
            elif isinstance(event, PacketDeliveryEvent):
                self._handle_packet_delivery(event)
            elif isinstance(event, LinkCongestionEvent):
                self._handle_link_congestion(event)
            elif isinstance(event, LinkIdleEvent):
                self._handle_link_idle(event)
            elif isinstance(event, TopologyReconfigurationEvent):
                self._handle_topology_reconfiguration(event)
            elif isinstance(event, ReconfigurationCompletionEvent):
                self._handle_topology_reconfiguration_completion(event)
            elif isinstance(event, RouteRecalculationEvent):
                self._handle_route_recalculation(event)
            else:
                raise ValueError(f"未知事件类型: {type(event)}")

        
        if show_progress:
            pbar.close()
        
        # 计算仿真统计数据
        self._calculate_statistics(simulation_time)
        
        elapsed = time.time() - start_real_time
        print(f"仿真完成，实际耗时: {elapsed:.2f}秒")
        print(f"生成数据包: {self.total_packets}, 送达: {self.delivered_count}, 丢弃: {self.dropped_count}")
        print(f"平均延迟: {self.total_delay/max(1, self.delivered_count):.3f}ms, 吞吐量: {self.throughput:.3f}Gbps")
        
        # 返回仿真结果
        return {
            'total_packets': self.total_packets,
            'delivered_packets': self.delivered_count,
            'dropped_packets': self.dropped_count,
            'delivery_rate': self.delivered_count / max(1, self.total_packets),
            'avg_delay': self.total_delay / max(1, self.delivered_count),
            'max_delay': self.max_delay,
            'min_delay': self.min_delay if self.min_delay != float('inf') else 0,
            'avg_hops': self.total_hops / max(1, self.delivered_count),
            'throughput': self.throughput,
            'std_link_utilization': np.std(list(self.link_utilization.values())),
            'avg_link_utilization': np.mean(list(self.link_utilization.values())),
            'max_link_utilization': max(self.link_utilization.values()),
            'avg_congestion': np.mean(list(self.congestion_levels.values())),
            'max_congestion': max(self.congestion_levels.values())
        }
    
    def _handle_traffic_generation(self, event):
        """
        处理流量生成事件
        
        参数:
            event: 流量生成事件
        """
        # 获取流量生成间隔
        traffic_interval = event.interval
        
        # 计算下一个时间点
        next_time = self.current_time + traffic_interval
        
        # 生成新的流量
        packets = self.traffic.generate_traffic(self.current_time, next_time)
        
        # 更新总数据包计数
        self.total_packets += len(packets)
        
        # 处理生成的数据包
        for packet in packets:
            # 为每个数据包创建生成事件
            self.schedule_event(PacketGenerationEvent(self.current_time, packet))
        
        # 调度下一次流量生成事件（如果仿真仍在进行）
        if next_time < self.simulation_end_time:
            next_event = TrafficGenerationEvent(next_time, traffic_interval)
            self.schedule_event(next_event)
    
    def _handle_packet_generation(self, event):
        """
        处理数据包生成事件
        
        参数:
            event: 数据包生成事件
        """
        packet = event.packet
        source = packet.source
        
        # 添加到源节点的路径
        packet.add_hop(source, packet.start_time)
        
        # 处理数据包
        processing_time = self.nodes[source].process_packet(packet, packet.start_time)
        
        # 查找下一跳
        next_hop = self.routing.get_next_hop(source, packet.destination, packet)
        
        if next_hop is None:
            # 无法路由
            packet.mark_dropped("NO_ROUTE")
            self.dropped_packets.append(packet)
            self.dropped_count += 1
            return
        
        # 调度数据包离开事件
        departure_time = packet.start_time + processing_time
        self.schedule_event(PacketDepartureEvent(packet.start_time, packet, source, next_hop))
    
    def _handle_packet_departure(self, event):
        """
        处理数据包离开事件
        
        参数:
            event: 数据包离开事件
        """
        packet = event.packet
        current_node = event.node
        next_node = event.next_node
        
        # 获取节点
        node = self.nodes.get(current_node)
        
        # 发送数据包
        success, arrival_time = node.send_packet(packet, next_node, self.current_time)
        
        if not success:
            # 发送失败（链路故障或缓冲区已满）
            packet.mark_dropped("SEND_FAILED")
            self.dropped_packets.append(packet)
            self.dropped_count += 1
            return
        
        # 如果有预估到达时间，调度数据包到达事件
        if arrival_time is not None:
            self.schedule_event(PacketArrivalEvent(arrival_time, packet, next_node))
    
    def _handle_packet_arrival(self, event):
        """
        处理数据包到达事件
        
        参数:
            event: 数据包到达事件
        """
        packet = event.packet
        node = event.node
        
        # 添加到路径
        packet.add_hop(node, self.current_time)
        
        # 检查是否到达目的地
        if node == packet.destination:
            # 调度数据包送达事件
            self.schedule_event(PacketDeliveryEvent(self.current_time, packet))
            return
        
        # 处理数据包
        processing_time = self.nodes[node].process_packet(packet, self.current_time)
        
        # 查找下一跳
        next_hop = self.routing.get_next_hop(node, packet.destination, packet)
        
        if next_hop is None:
            # 无法路由
            packet.mark_dropped("NO_ROUTE")
            self.dropped_packets.append(packet)
            self.dropped_count += 1
            return
        
        # 调度数据包离开事件
        departure_time = self.current_time + processing_time
        self.schedule_event(PacketDepartureEvent(departure_time, packet, node, next_hop))
    
    def _handle_packet_delivery(self, event):
        """
        处理数据包送达事件
        
        参数:
            event: 数据包送达事件
        """
        packet = event.packet
        
        # 标记数据包已送达
        packet.mark_delivered(self.current_time)
        
        # 更新统计信息
        self.delivered_packets.append(packet)
        self.delivered_count += 1
        self.total_delay += packet.total_delay
        self.max_delay = max(self.max_delay, packet.total_delay)
        self.min_delay = min(self.min_delay, packet.total_delay)
        self.total_hops += len(packet.path) - 1  # 减去源节点
    
    def _handle_link_congestion(self, event):
        """
        处理链路拥塞事件
        
        参数:
            event: 链路拥塞事件
        """
        source = event.source
        destination = event.destination
        level = event.congestion_level
        
        # 更新链路拥塞级别
        self.congestion_levels[(source, destination)] = level
    
    def _handle_link_idle(self, event):
        """
        处理链路空闲事件
        
        参数:
            event: 链路空闲事件
        """
        link = event.link
        
        # 处理队列中的下一个数据包
        packet, completion_time = link.process_next_packet(self.current_time)
        
        # 如果成功处理了数据包，调度数据包到达事件
        if packet and completion_time:
            self.schedule_event(PacketArrivalEvent(completion_time, packet, link.destination))
    
    def _calculate_statistics(self, simulation_time):
        """
        计算仿真统计数据
        
        参数:
            simulation_time: 仿真时间(ms)
        """
        # 计算吞吐量 (Gbps)
        total_bytes = sum(p.size for p in self.delivered_packets if p.arrival_time< simulation_time)
        self.throughput = (total_bytes * 8) / (simulation_time * 1000000)  # 转换为Gbps
        
        # 更新链路利用率
        for (u, v), link in self.links.items():
            self.link_utilization[(u, v)] = link.get_utilization()
            self.congestion_levels[(u, v)] = link.congestion_level
    
    def get_node(self, node_id):
        """
        获取节点对象
        
        参数:
            node_id: 节点ID
            
        返回:
            节点对象
        """
        return self.nodes.get(node_id)
    
    # 添加拓扑重构事件处理方法
    def _handle_topology_reconfiguration(self, event):
        """
        处理拓扑重构事件
        
        参数:
            event: 拓扑重构事件
        """
        # 记录重构开始时间
        self.reconfig_start_times.append(self.current_time)
        
        # 标记正在重构
        self.in_reconfiguration = True

        print(f"时间 {self.current_time:.2f}ms: 开始第{self.reconfig_count+1}次拓扑重构")
        
        # 获取当前流量矩阵
        traffic_matrix = None
        if hasattr(self.traffic, 'get_current_traffic_matrix'):
            traffic_matrix = self.traffic.get_current_traffic_matrix()
            
            # 打印流量矩阵统计信息
            if traffic_matrix:
                print(traffic_matrix)
                num_flows = len(traffic_matrix)
                total_traffic = sum(traffic_matrix.values())
                max_flow = max(traffic_matrix.values()) if traffic_matrix else 0
                print(f"流量矩阵: {num_flows}条流, 总流量: {total_traffic:.3f}Gbps, 最大流: {max_flow:.3f}Gbps")
        
        # 重新配置OCS连接
        self.topology.reconfigure_ocs(traffic_matrix)
        
        self._apply_new_topology(self.topology)
        
        # 标记重构完成
        self.in_reconfiguration = False
        
        # 记录重构结束时间
        self.reconfig_end_times.append(self.current_time)
        
        # 增加重构计数
        self.reconfig_count += 1
        
        print(f"时间 {self.current_time:.2f}ms: 完成第{self.reconfig_count}次拓扑重构")
        
        # 调度路由重新计算事件
        self.routing.recalculate_routes(self.topology)
        
        # 调度下一次拓扑重构事件（如果仿真仍在进行）
        next_reconfig_time = self.current_time + event.reconfig_interval * 1000  # 转换为毫秒
        if next_reconfig_time < self.simulation_end_time:
            next_event = TopologyReconfigurationEvent(next_reconfig_time, event.reconfig_interval, event.reconfig_delay)
            self.schedule_event(next_event)




    def _handle_topology_reconfiguration_completion(self, event):
        """
        处理重构完成事件
        
        参数:
            event: 重构完成事件
        """
        # 应用新的拓扑结构
        self._apply_new_topology(event.new_topology)
        
        # 标记重构完成
        self.in_reconfiguration = False
        
        # 记录重构结束时间
        self.reconfig_end_times.append(self.current_time)
        
        # 增加重构计数
        self.reconfig_count += 1
        
        print(f"时间 {self.current_time:.2f}ms: 完成第{self.reconfig_count}次拓扑重构")
        
        # 调度路由重新计算事件
        self.schedule_event(RouteRecalculationEvent(self.current_time))


    def _handle_route_recalculation(self, event):
        """
        处理路由重新计算事件
        
        参数:
            event: 路由重新计算事件
        """
        print(f"时间 {self.current_time:.2f}ms: 开始路由重新计算")
        
        # 通知路由对象重新计算路由
        self.routing.recalculate_routes(self.topology)
        
        print(f"时间 {self.current_time:.2f}ms: 完成路由重新计算")


    def _calculate_new_topology(self, traffic_matrix):
        """
        根据流量矩阵计算新的拓扑结构
        
        参数:
            traffic_matrix: 当前流量矩阵
        
        返回:
            新的拓扑结构
        """
        # 这里实现您的OCS重构算法
        # 例如：基于流量需求的贪心算法
        
        # 创建新的拓扑对象作为当前拓扑的副本
        new_topology = self.topology.copy()
        
        # 获取节点数量
        n = len(self.topology.get_nodes())
        
        # 创建节点对和流量的列表
        node_pairs = []
        for i in range(n):
            for j in range(i+1, n):
                if i != j:
                    # 计算i和j之间的双向流量总和
                    total_traffic = traffic_matrix.get((i, j), 0) + traffic_matrix.get((j, i), 0)
                    node_pairs.append((i, j, total_traffic))
        
        # 按流量需求排序
        node_pairs.sort(key=lambda x: x[2], reverse=True)
        
        # 选择流量最大的128对节点建立OCS连接
        ocs_connections = set()
        for i in range(min(128, len(node_pairs))):
            src, dst, _ = node_pairs[i]
            ocs_connections.add((src, dst))
            ocs_connections.add((dst, src))  # 添加反向连接
        
        # 更新拓扑中的OCS连接
        new_topology.update_ocs_connections(ocs_connections)
        
        return new_topology


    def _apply_new_topology(self, new_topology):
        """
        应用新的拓扑结构
        
        参数:
            new_topology: 新的拓扑结构
        """
        # 获取需要添加和删除的链路
        added_edges = []
        removed_edges = []
        
        # 当前网络中存在的边（从self.links中获取）
        current_edges = set((u, v) for u, v in self.links.keys())
        
        # 新拓扑中的边
        new_edges = set(new_topology.get_edges())
        
        # 同时添加反向边（因为我们的链路是双向的）
        new_edges_bidirectional = set()
        for u, v in new_edges:
            new_edges_bidirectional.add((u, v))
            new_edges_bidirectional.add((v, u))
        
        # 找出需要删除的链路（在当前网络中存在但在新拓扑中不存在）
        for u, v in current_edges:
            if (u, v) not in new_edges_bidirectional:
                removed_edges.append((u, v))
        
        # 找出需要添加的链路（在新拓扑中存在但在当前网络中不存在）
        for u, v in new_edges:
            if (u, v) not in current_edges:
                added_edges.append((u, v))
            # 同时检查反向边
            if (v, u) not in current_edges:
                added_edges.append((v, u))
        
        print(f"拓扑变更: 删除 {len(removed_edges)} 条链路, 添加 {len(added_edges)} 条链路")
        
        # 删除旧链路
        for u, v in removed_edges:
            # 从节点中移除链路
            if u in self.nodes:
                self.nodes[u].remove_link(v)
            
            # 移除链路对象
            if (u, v) in self.links:
                del self.links[(u, v)]
            
            # 更新链路利用率和拥塞级别统计
            if (u, v) in self.link_utilization:
                del self.link_utilization[(u, v)]
            if (u, v) in self.congestion_levels:
                del self.congestion_levels[(u, v)]
        
        # 添加新链路
        for u, v in added_edges:
            # 获取链路参数
            capacity = new_topology.get_link_capacity(u, v)
            delay = new_topology.get_link_delay(u, v)
            buffer = new_topology.get_link_buffer(u, v)
            
            # 创建链路
            link = Link(u, v, capacity, delay, buffer, self)
            self.links[(u, v)] = link
            
            # 将链路添加到节点
            if u in self.nodes:
                self.nodes[u].add_link(v, link)
            
            # 初始化链路利用率和拥塞级别统计
            self.link_utilization[(u, v)] = 0.0
            self.congestion_levels[(u, v)] = 0.0
        
        # 更新拓扑
        self.topology = new_topology



