import os
import heapq
import random
import numpy as np
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional, Set, Any
from collections import defaultdict, deque


class Packet:
    """数据包类"""
    _next_id = 0  # 用于生成唯一ID
    
    def __init__(self, packet_id: int, src: int, dst: int, size: int, 
                 creation_time: float, flow_id: int):
        self.id = Packet._next_id
        Packet._next_id += 1
        self.packet_id = packet_id  # 在流中的ID
        self.src = src
        self.dst = dst
        self.size = size  # 字节
        self.creation_time = creation_time
        self.flow_id = flow_id
        self.current_node = src
        self.next_hop = None
        self.arrival_time = None
        self.queuing_delays = []
        self.transmission_delays = []
        self.propagation_delays = []
        self.dropped = False
        self.completed = False
    
    def __lt__(self, other):
        """用于heapq比较的方法"""
        if isinstance(other, Packet):
            return self.id < other.id
        return NotImplemented
    
    def get_total_delay(self) -> float:
        """获取总延迟"""
        if not self.arrival_time:
            return float('inf')
        return self.arrival_time - self.creation_time
    
    def get_hop_count(self) -> int:
        """获取跳数"""
        return len(self.queuing_delays)


class Flow:
    """流类"""
    _next_id = 0  # 用于生成唯一ID
    
    def __init__(self, src: int, dst: int, size: int, start_time: float, flow_type: str = "regular"):
        self.id = Flow._next_id
        Flow._next_id += 1
        self.src = src
        self.dst = dst
        self.size = size  # 字节
        self.start_time = start_time
        self.end_time = None
        self.packets = []
        self.packet_size = 1500  # 默认包大小
        self.completed_packets = 0
        self.type = flow_type  # regular, background, burst
        self.completed = False
    
    def generate_packets(self, packet_size: int = None) -> List[Packet]:
        """生成流的所有数据包"""
        if packet_size:
            self.packet_size = packet_size
        
        num_packets = (self.size + self.packet_size - 1) // self.packet_size
        packets = []
        
        for i in range(num_packets):
            # 最后一个包可能小于packet_size
            size = min(self.packet_size, self.size - i * self.packet_size)
            
            packet = Packet(
                packet_id=i,
                src=self.src,
                dst=self.dst,
                size=size,
                creation_time=self.start_time,
                flow_id=self.id
            )
            packets.append(packet)
        
        self.packets = packets
        return packets
    
    def is_completed(self) -> bool:
        """检查流是否完成"""
        return self.completed_packets == len(self.packets)
    
    def get_completion_time(self) -> float:
        """获取流完成时间"""
        if self.end_time:
            return self.end_time - self.start_time
        return float('inf')


class Link:
    """链路类"""
    def __init__(self, src: int, dst: int, bandwidth: float, propagation_delay: float,
                 queue_size: int, loss_rate: float = 0.0, failure_prob: float = 0.0):
        self.src = src
        self.dst = dst
        self.bandwidth = bandwidth  # bits per second
        self.propagation_delay = propagation_delay  # seconds
        self.queue_size = queue_size  # packets
        self.queue = deque()  # (packet, enqueue_time)
        self.loss_rate = loss_rate
        self.failure_prob = failure_prob
        self.failed = False
        self.busy_until = 0  # 链路忙碌直到该时间
        self.bytes_transmitted = 0
        self.packets_dropped = 0
        self.next_packet_event = None  # 下一个包的完成事件
    
    def check_failure(self) -> bool:
        """检查链路是否故障"""
        if random.random() < self.failure_prob:
            self.failed = True
            return True
        return False
    
    def enqueue(self, packet: Packet, current_time: float) -> bool:
        """将数据包加入队列，如果队列满则返回False"""
        if self.failed:
            self.packets_dropped += 1
            return False
        
        # 随机丢包
        if random.random() < self.loss_rate:
            self.packets_dropped += 1
            return False
        
        # 检查队列是否已满
        if len(self.queue) >= self.queue_size:
            self.packets_dropped += 1
            return False
        
        self.queue.append((packet, current_time))
        return True
    
    def dequeue(self, current_time: float) -> Tuple[Optional[Packet], float]:
        """从队列中取出数据包，返回(packet, next_event_time)"""
        if self.failed or not self.queue or current_time < self.busy_until:
            return None, float('inf')
        
        packet, enqueue_time = self.queue.popleft()
        
        # 计算排队延迟
        queuing_delay = max(0, current_time - enqueue_time)
        packet.queuing_delays.append(queuing_delay)
        
        # 计算传输延迟 (size in bytes * 8 bits/byte / bandwidth in bits/sec)
        transmission_delay = (packet.size * 8) / self.bandwidth
        packet.transmission_delays.append(transmission_delay)
        
        # 计算传播延迟
        packet.propagation_delays.append(self.propagation_delay)
        
        # 更新链路状态
        self.busy_until = current_time + transmission_delay
        self.bytes_transmitted += packet.size
        
        # 下一个事件时间 = 当前时间 + 传输延迟 + 传播延迟
        next_event_time = self.busy_until + self.propagation_delay
        
        return packet, next_event_time
    
    def get_utilization(self, simulation_time: float) -> float:
        """计算链路利用率"""
        if simulation_time == 0:
            return 0.0
        return (self.bytes_transmitted * 8) / (self.bandwidth * simulation_time)


class Router:
    """路由器类"""
    def __init__(self, node_id: int, algorithm: str = "shortest_path"):
        self.node_id = node_id
        self.algorithm = algorithm
        self.routing_table = {}  # {dst: next_hop}
    
    def set_routing_table(self, routing_table: Dict[int, int]) -> None:
        """设置路由表"""
        self.routing_table = routing_table
    
    def get_next_hop(self, dst: int) -> Optional[int]:
        """获取下一跳"""
        return self.routing_table.get(dst)


class Event:
    """事件类"""
    PACKET_ARRIVAL = 0
    PACKET_DEPARTURE = 1
    FLOW_ARRIVAL = 2
    LINK_CHECK = 3
    SIMULATION_END = 4
    
    def __init__(self, event_type: int, time: float, data: Any = None):
        self.type = event_type
        self.time = time
        self.data = data
    
    def __lt__(self, other):
        """用于heapq比较的方法"""
        if isinstance(other, Event):
            if self.time == other.time:
                return self.type < other.type
            return self.time < other.time
        return NotImplemented


class NetworkSimulator:
    """网络仿真器类"""
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.nodes = []
        self.links = {}  # (src, dst) -> Link
        self.routers = {}  # node_id -> Router
        self.flows = []
        self.flow_dict = {}  # flow_id -> Flow (添加这个字典用于快速查找)
        self.topology = None
        self.graph = None
        self.event_queue = []
        self.current_time = 0
        self.simulation_end_time = config.get("simulation_end_time", 1000)
        self.random_seed = config.get("random_seed", 42)
        self.event_counter = 0  # 用于确保事件顺序的唯一性
        
        # 设置随机种子
        random.seed(self.random_seed)
        np.random.seed(self.random_seed)
    
    def load_topology(self, topology_file: str) -> None:
        """从文件加载拓扑结构"""
        try:
            print(f"Loading topology from {topology_file}...")
            
            # 读取邻接矩阵
            adj_matrix = np.loadtxt(topology_file, dtype=int)
            self.topology = adj_matrix
            
            # 创建NetworkX图
            self.graph = nx.from_numpy_array(adj_matrix)
            
            # 检查图的连通性
            if not nx.is_connected(self.graph):
                print("WARNING: The graph is not connected!")
                components = list(nx.connected_components(self.graph))
                print(f"Number of connected components: {len(components)}")
            
            # 初始化节点和路由器
            self.nodes = list(range(len(adj_matrix)))
            for node in self.nodes:
                self.routers[node] = Router(node, self.config.get("routing_algorithm", "shortest_path"))
            
            # 初始化链路
            for i in range(len(adj_matrix)):
                for j in range(len(adj_matrix)):
                    if adj_matrix[i][j] == 1:
                        self.links[(i, j)] = Link(
                            src=i,
                            dst=j,
                            bandwidth=self.config.get("link_bandwidth", 10e9),
                            propagation_delay=self.config.get("link_propagation_delay", 0.0001),
                            queue_size=self.config.get("queue_size", 100),
                            loss_rate=self.config.get("link_loss_rate", 0.0),
                            failure_prob=self.config.get("link_failure_prob", 0.0)
                        )
            
            # 计算路由表
            self._compute_routing_tables()
            
            print(f"Loaded topology with {len(self.nodes)} nodes and {len(self.links)} links")
            
        except Exception as e:
            print(f"Error loading topology: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    def _compute_routing_tables(self) -> None:
        """计算所有节点的路由表"""
        algorithm = self.config.get("routing_algorithm", "shortest_path")
        
        if algorithm == "shortest_path":
            # 使用Dijkstra算法计算最短路径
            for src in self.nodes:
                shortest_paths = nx.single_source_shortest_path(self.graph, src)
                routing_table = {}
                
                for dst in self.nodes:
                    if dst == src:
                        continue
                    
                    if dst in shortest_paths:
                        path = shortest_paths[dst]
                        if len(path) > 1:
                            routing_table[dst] = path[1]  # 下一跳
                
                self.routers[src].set_routing_table(routing_table)
        else:
            raise ValueError(f"Unsupported routing algorithm: {algorithm}")
    
    def generate_flows(self) -> None:
        """生成流量"""
        max_flows = self.config.get("max_flows", 1000)
        flow_size_range = self.config.get("flow_size_range", (1000, 1000000))
        flow_arrival_rate = self.config.get("flow_arrival_rate", 10)
        packet_size = self.config.get("packet_size", 1500)
        background_flow_percentage = self.config.get("background_flow_percentage", 0.2)
        burst_flow_percentage = self.config.get("burst_flow_percentage", 0.1)
        burst_time = self.config.get("burst_time", 500)
        burst_duration = self.config.get("burst_duration", 10)
        
        # 生成常规流
        num_regular_flows = int(max_flows * (1 - background_flow_percentage - burst_flow_percentage))
        regular_flow_times = np.random.exponential(1 / flow_arrival_rate, num_regular_flows)
        regular_flow_times = np.cumsum(regular_flow_times)
        
        # 生成背景流
        num_background_flows = int(max_flows * background_flow_percentage)
        background_flow_times = np.random.uniform(0, self.simulation_end_time, num_background_flows)
        
        # 生成突发流
        num_burst_flows = int(max_flows * burst_flow_percentage)
        burst_flow_times = np.random.uniform(burst_time, burst_time + burst_duration, num_burst_flows)
        
        # 合并所有流
        all_flow_times = []
        all_flow_times.extend([(t, "regular") for t in regular_flow_times])
        all_flow_times.extend([(t, "background") for t in background_flow_times])
        all_flow_times.extend([(t, "burst") for t in burst_flow_times])
        
        # 按时间排序
        all_flow_times.sort(key=lambda x: x[0])
        
        # 创建流对象
        for time, flow_type in all_flow_times:
            if time >= self.simulation_end_time:
                continue
            
            # 随机选择源和目的节点
            if len(self.nodes) >= 2:  # 确保至少有两个节点
                src, dst = random.sample(self.nodes, 2)
                
                # 随机选择流大小
                size = random.randint(flow_size_range[0], flow_size_range[1])
                
                # 创建流
                flow = Flow(src, dst, size, time, flow_type)
                flow.generate_packets(packet_size)
                
                self.flows.append(flow)
                self.flow_dict[flow.id] = flow  # 添加到字典中
                
                # 添加流到达事件
                self.add_event(Event(Event.FLOW_ARRIVAL, time, flow))
        
        print(f"Generated {len(self.flows)} flows: {num_regular_flows} regular, {num_background_flows} background, {num_burst_flows} burst")
    
    def add_event(self, event: Event) -> None:
        """添加事件到事件队列"""
        heapq.heappush(self.event_queue, event)
    
    def schedule_link_checks(self) -> None:
        """调度链路检查事件"""
        check_interval = self.simulation_end_time / 100  # 100次检查
        for i in range(1, 101):
            check_time = i * check_interval
            self.add_event(Event(Event.LINK_CHECK, check_time))
    
    def handle_flow_arrival(self, flow: Flow) -> None:
        """处理流到达事件"""
        # 为流的每个包添加包到达事件
        for packet in flow.packets:
            self.add_event(Event(Event.PACKET_ARRIVAL, packet.creation_time, packet))
    
    def handle_packet_arrival(self, packet: Packet) -> None:
        """处理包到达事件"""
        # 如果包已经到达目的地
        if packet.current_node == packet.dst:
            packet.arrival_time = self.current_time
            packet.completed = True
            
            # 更新流的完成状态
            flow = self.flow_dict.get(packet.flow_id)  # 使用字典查找
            if flow:
                flow.completed_packets += 1
                
                if flow.is_completed() and not flow.completed:
                    flow.completed = True
                    flow.end_time = self.current_time
            else:
                print(f"Warning: Flow {packet.flow_id} not found for packet {packet.id}")
            
            return
        
        # 获取下一跳
        router = self.routers[packet.current_node]
        next_hop = router.get_next_hop(packet.dst)
        
        if next_hop is None:
            # 找不到路由，丢弃包
            packet.dropped = True
            return
        
        packet.next_hop = next_hop
        
        # 将包放入链路队列
        link = self.links.get((packet.current_node, next_hop))
        if link is None:
            # 链路不存在，丢弃包
            packet.dropped = True
            return
        
        # 尝试入队
        if link.enqueue(packet, self.current_time):
            # 如果链路当前空闲，立即处理这个包
            if self.current_time >= link.busy_until:
                self.process_next_packet(link)
        else:
            # 入队失败，丢弃包
            packet.dropped = True
    
    def process_next_packet(self, link: Link) -> None:
        """处理链路上的下一个包"""
        packet, next_event_time = link.dequeue(self.current_time)
        
        if packet:
            # 更新包的当前节点
            packet.current_node = link.dst
            
            # 添加包到达事件
            self.add_event(Event(Event.PACKET_DEPARTURE, next_event_time, (packet, link)))
    
    def handle_packet_departure(self, packet: Packet, link: Link) -> None:
        """处理包离开事件"""
        # 添加包到达事件
        self.add_event(Event(Event.PACKET_ARRIVAL, self.current_time, packet))
        
        # 如果链路队列不为空，处理下一个包
        if link.queue:
            self.process_next_packet(link)
    
    def handle_link_check(self) -> None:
        """处理链路检查事件"""
        for link in self.links.values():
            link.check_failure()
    
    def run_simulation(self) -> Dict[str, Any]:
        """运行仿真"""
        # 添加仿真结束事件
        self.add_event(Event(Event.SIMULATION_END, self.simulation_end_time))
        
        # 生成流量
        self.generate_flows()
        
        # 调度链路检查
        self.schedule_link_checks()
        
        # 主循环
        while self.event_queue:
            event = heapq.heappop(self.event_queue)
            
            # 更新当前时间
            self.current_time = event.time
            
            # 处理事件
            if event.type == Event.FLOW_ARRIVAL:
                self.handle_flow_arrival(event.data)
            elif event.type == Event.PACKET_ARRIVAL:
                self.handle_packet_arrival(event.data)
            elif event.type == Event.PACKET_DEPARTURE:
                packet, link = event.data
                self.handle_packet_departure(packet, link)
            elif event.type == Event.LINK_CHECK:
                self.handle_link_check()
            elif event.type == Event.SIMULATION_END:
                break
        
        # 收集结果
        return self.collect_results()
    
    def collect_results(self) -> Dict[str, Any]:
        """收集仿真结果"""
        # 计算吞吐量
        total_bytes = sum(flow.size for flow in self.flows if flow.completed)
        throughput = (total_bytes * 8) / self.simulation_end_time  # bits per second
        
        # 计算流类型的吞吐量
        regular_bytes = sum(flow.size for flow in self.flows if flow.completed and flow.type == "regular")
        background_bytes = sum(flow.size for flow in self.flows if flow.completed and flow.type == "background")
        burst_bytes = sum(flow.size for flow in self.flows if flow.completed and flow.type == "burst")
        
        regular_throughput = (regular_bytes * 8) / self.simulation_end_time
        background_throughput = (background_bytes * 8) / self.simulation_end_time
        burst_throughput = (burst_bytes * 8) / self.simulation_end_time
        
        # 计算平均延迟
        completed_packets = [p for flow in self.flows for p in flow.packets if p.completed]
        avg_delay = np.mean([p.get_total_delay() for p in completed_packets]) if completed_packets else 0
        
        # 计算平均跳数
        avg_hops = np.mean([p.get_hop_count() for p in completed_packets]) if completed_packets else 0
        
        # 计算丢包率
        total_packets = sum(len(flow.packets) for flow in self.flows)
        dropped_packets = sum(1 for flow in self.flows for p in flow.packets if p.dropped)
        packet_loss_rate = dropped_packets / total_packets if total_packets > 0 else 0
        
        # 计算流完成率
        completed_flows = sum(1 for flow in self.flows if flow.completed)
        flow_completion_ratio = completed_flows / len(self.flows) if self.flows else 0
        
        # 计算流完成时间
        flow_completion_times = [flow.get_completion_time() for flow in self.flows if flow.completed]
        
        # 计算链路利用率
        link_utilization = {(link.src, link.dst): link.get_utilization(self.simulation_end_time) 
                           for (src, dst), link in self.links.items()}
        
        # 计算不同流类型的平均FCT
        regular_fct = [flow.get_completion_time() for flow in self.flows 
                      if flow.completed and flow.type == "regular"]
        background_fct = [flow.get_completion_time() for flow in self.flows 
                         if flow.completed and flow.type == "background"]
        burst_fct = [flow.get_completion_time() for flow in self.flows 
                    if flow.completed and flow.type == "burst"]
        
        regular_avg_fct = np.mean(regular_fct) if regular_fct else 0
        background_avg_fct = np.mean(background_fct) if background_fct else 0
        burst_avg_fct = np.mean(burst_fct) if burst_fct else 0
        
        return {
            "throughput": throughput,
            "avg_delay": avg_delay,
            "avg_hops": avg_hops,
            "packet_loss_rate": packet_loss_rate,
            "flow_completion_ratio": flow_completion_ratio,
            "flow_completion_times": flow_completion_times,
            "link_utilization": link_utilization,
            "regular_throughput": regular_throughput,
            "background_throughput": background_throughput,
            "burst_throughput": burst_throughput,
            "regular_avg_fct": regular_avg_fct,
            "background_avg_fct": background_avg_fct,
            "burst_avg_fct": burst_avg_fct
        }


def compare_topologies(topology_files: Dict[str, str], config: Dict[str, Any], 
                       num_runs: int = 1) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """比较不同拓扑的性能"""
    results = []
    
    for topo_name, topo_file in topology_files.items():
        if not os.path.exists(topo_file):
            print(f"Warning: Topology file {topo_file} does not exist. Skipping {topo_name}.")
            continue
            
        print(f"\nSimulating {topo_name} topology...")
        
        for run in range(1, num_runs + 1):
            print(f"Run {run}/{num_runs}...")
            
            # 创建仿真器
            simulator = NetworkSimulator(config)
            
            # 加载拓扑
            try:
                simulator.load_topology(topo_file)
                
                # 运行仿真
                results_dict = simulator.run_simulation()
                
                # 添加拓扑名称和运行次数
                results_dict["topology"] = topo_name
                results_dict["run"] = run
                
                results.append(results_dict)
                
                print(f"  Throughput: {results_dict['throughput'] / 1e9:.2f} Gbps")
                print(f"  Flow completion ratio: {results_dict['flow_completion_ratio'] * 100:.2f}%")
                
            except Exception as e:
                print(f"Error simulating {topo_name}: {e}")
                import traceback
                traceback.print_exc()
    
    # 创建DataFrame
    df_results = pd.DataFrame(results)
    
    # 计算摘要统计
    summary = df_results.groupby("topology").agg({
        "throughput": "mean",
        "avg_delay": "mean",
        "avg_hops": "mean",
        "packet_loss_rate": "mean",
        "flow_completion_ratio": "mean",
        "regular_throughput": "mean",
        "background_throughput": "mean",
        "burst_throughput": "mean",
        "regular_avg_fct": "mean",
        "background_avg_fct": "mean",
        "burst_avg_fct": "mean"
    }).reset_index()
    
    return df_results, summary


def plot_comparison(summary: pd.DataFrame, output_dir: str = "results") -> None:
    """绘制比较图表"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 吞吐量比较
    plt.figure(figsize=(10, 6))
    plt.bar(summary["topology"], summary["throughput"] / 1e9)
    plt.title("Average Throughput Comparison")
    plt.ylabel("Throughput (Gbps)")
    plt.xlabel("Topology")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/throughput_comparison.png")
    
    # 延迟比较
    plt.figure(figsize=(10, 6))
    plt.bar(summary["topology"], summary["avg_delay"] * 1000)  # 转换为毫秒
    plt.title("Average Delay Comparison")
    plt.ylabel("Delay (ms)")
    plt.xlabel("Topology")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/delay_comparison.png")
    
    # 平均跳数比较
    plt.figure(figsize=(10, 6))
    plt.bar(summary["topology"], summary["avg_hops"])
    plt.title("Average Hop Count Comparison")
    plt.ylabel("Hop Count")
    plt.xlabel("Topology")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/hops_comparison.png")
    
    # 丢包率比较
    plt.figure(figsize=(10, 6))
    plt.bar(summary["topology"], summary["packet_loss_rate"] * 100)  # 转换为百分比
    plt.title("Packet Loss Rate Comparison")
    plt.ylabel("Loss Rate (%)")
    plt.xlabel("Topology")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/loss_comparison.png")
    
    # 流完成率比较
    plt.figure(figsize=(10, 6))
    plt.bar(summary["topology"], summary["flow_completion_ratio"] * 100)  # 转换为百分比
    plt.title("Flow Completion Ratio Comparison")
    plt.ylabel("Completion Ratio (%)")
    plt.xlabel("Topology")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/flow_completion_comparison.png")
    
    # 不同流类型的吞吐量比较
    plt.figure(figsize=(12, 6))
    x = np.arange(len(summary["topology"]))
    width = 0.25
    
    plt.bar(x - width, summary["regular_throughput"] / 1e9, width, label='Regular')
    plt.bar(x, summary["background_throughput"] / 1e9, width, label='Background')
    plt.bar(x + width, summary["burst_throughput"] / 1e9, width, label='Burst')
    
    plt.title("Throughput by Flow Type")
    plt.ylabel("Throughput (Gbps)")
    plt.xlabel("Topology")
    plt.xticks(x, summary["topology"], rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{output_dir}/flow_type_throughput_comparison.png")
    
    # 不同流类型的FCT比较
    plt.figure(figsize=(12, 6))
    
    plt.bar(x - width, summary["regular_avg_fct"] * 1000, width, label='Regular')
    plt.bar(x, summary["background_avg_fct"] * 1000, width, label='Background')
    plt.bar(x + width, summary["burst_avg_fct"] * 1000, width, label='Burst')
    
    plt.title("Flow Completion Time by Flow Type")
    plt.ylabel("Average FCT (ms)")
    plt.xlabel("Topology")
    plt.xticks(x, summary["topology"], rotation=45)
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{output_dir}/flow_type_fct_comparison.png")
    
    plt.close('all')


def main():
    # 配置参数
    config = {
        "simulation_end_time": 1000,
        "random_seed": 42,
        "link_bandwidth": 10e6,  # 10 Mbps
        "link_propagation_delay": 0.001,  # 1 ms
        "queue_size": 100,  # 包
        "link_loss_rate": 0.0001,  # 0.01%
        "link_failure_prob": 0.001,  # 0.1%
        "max_flows": 10000,
        "flow_size_range": (100000, 10000000),  # 10KB to 10MB
        "flow_arrival_rate": 100,  # 每秒10个流
        "background_flow_percentage": 0.2,
        "burst_flow_percentage": 0.1,
        "burst_time": 500,
        "burst_duration": 10,
        "packet_size": 150000,  # 字节
        "routing_algorithm": "shortest_path"
    }
    
    # 拓扑文件
    topology_files = {
        "FatTree": "topologies/fat_tree.txt",
        "Dragonfly": "topologies/dragonfly.txt",
        "Ramanujan": "topologies/ramanujan.txt",
        "RandomGraph": "topologies/random_graph.txt",
        "FullyConnected":"topologies/fully_connected.txt"
    }
    
    # 比较拓扑
    results, summary = compare_topologies(topology_files, config, num_runs=1)
    
    # 保存结果
    if not os.path.exists("results"):
        os.makedirs("results")
    
    results.to_csv("results/detailed_results.csv", index=False)
    summary.to_csv("results/summary_results.csv", index=False)
    
    # 打印摘要
    print("\nSummary Results:")
    print(summary.to_string(index=False))
    
    # 绘制比较图表
    plot_comparison(summary)


if __name__ == "__main__":
    main()

