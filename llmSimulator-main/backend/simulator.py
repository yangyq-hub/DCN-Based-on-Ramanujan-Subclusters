import heapq
import random
import sys
import os
import time
import yaml
import numpy as np
from traffic import BackgroundTrafficGenerator
from network import NetworkManager

class Tee:
    """同时将输出写入文件和标准输出"""
    def __init__(self, stdout, file):
        self.stdout = stdout
        self.file = file
        self.closed = False
    
    def write(self, text):
        if not self.closed:
            self.stdout.write(text)
            self.file.write(text)
    
    def flush(self):
        if not self.closed:
            self.stdout.flush()
            self.file.flush()
            
    def close(self):
        self.closed = True
        if hasattr(self.file, 'close'):
            self.file.close()

class Event:
    """事件基类，支持优先级排序"""
    def __init__(self, time, event_type, data, priority=0):
        self.time = time
        self.event_type = event_type
        self.data = data
        self.priority = priority  # 相同时间时的次要排序条件
        
    def __lt__(self, other):
        # 首先按时间排序，时间相同时按优先级排序
        if self.time == other.time:
            return self.priority < other.priority
        return self.time < other.time

class ComputeNode:
    """计算节点，管理计算资源"""
    def __init__(self, node_id, compute_power=1.0):
        self.node_id = node_id
        self.busy = False
        self.busy_until = 0
        self.current_task = None
        # 当前节点所处理的任务队列
        self.task_queue = []
        # 用于Ring-AllReduce的状态
        self.received_gradients = {}  # {group_id: {chunk_id: received}}
        self.gradient_chunks = {}  # 存储梯度分块
        # 节点计算能力（相对值，1.0为标准）
        self.compute_power = compute_power
        # 统计信息
        self.compute_time = 0  # 总计算时间
        self.idle_time = 0  # 总空闲时间
        self.forward_count = 0  # 前向传播次数
        self.backward_count = 0  # 反向传播次数

    def start_computation(self, current_time, task_type, duration):
        """开始计算任务，更新统计信息"""
        if not self.busy:
            # 如果之前是空闲的，更新空闲时间
            if hasattr(self, 'last_state_change'):
                self.idle_time += current_time - self.last_state_change
        
        self.busy = True
        self.busy_until = current_time + duration
        self.last_state_change = current_time
        
        if task_type == 'forward':
            self.forward_count += 1
        elif task_type == 'backward':
            self.backward_count += 1
    
    def end_computation(self, current_time):
        """结束计算任务，更新统计信息"""
        if self.busy:
            # 更新计算时间
            if hasattr(self, 'last_state_change'):
                self.compute_time += current_time - self.last_state_change
        
        self.busy = False
        self.current_task = None
        self.last_state_change = current_time


class Simulator:
    """分布式训练仿真器"""
    def __init__(self, config_file):
        # 加载配置文件
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # 基本配置
        self.parallel_mode = self.config.get("parallel_mode", "pipeline")
        self.event_heap = []
        self.current_time = 0
        self.nodes = {}  # 计算节点
        
        # 获取网络配置
        self.network_config = self.config.get("network", {})
        
        # 获取路由算法配置
        routing_algorithm = self.network_config.get("routing_algorithm", "dijkstra")
        
        # 初始化网络管理器，传递路由算法参数
        self.network = NetworkManager(self, self.network_config)
        
        # 路由统计数据
        self.routing_stats = {
            "algorithm": routing_algorithm,
            "average_path_length": 0,
            "path_diversity": 0,
            "routing_performance": []
        }
        
        # 模型配置
        self.total_params = self.config.get("total_params", 1000)  # 模型总参数量（百万）
        self.batch_size = self.config.get("batch_size", 32)  # 批次大小
        self.micro_batch_count = self.config.get("micro_batch_count", 8)  # 微批次数量
        self.micro_batch_size = self.batch_size / self.micro_batch_count  # 微批次大小
        self.num_batches = self.config.get("num_batches", 1)  # 要训练的批次数量
        self.current_batch = 0  # 当前正在处理的批次
        
        # 精度配置
        self.precision = self.config.get("precision", "fp16")  # 训练精度
        self.precision_factor = {
            'fp32': 4,
            'fp16': 2,
            'bf16': 2,
            'int8': 1
        }.get(self.precision, 2) / 4.0  # 相对于FP32的比例
        
        # 激活值检查点配置
        self.activation_checkpointing = self.config.get("activation_checkpointing", True)
        self.activation_checkpoint_factor = 0.5 if self.activation_checkpointing else 1.0
        
        # 阶段配置
        self.stage_compute_times = {}  # 每个阶段的计算时间
        
        # 微批次状态追踪
        self.micro_batch_status = {}  # 追踪每个微批次的状态
        self.stage_dependencies = {}  # 阶段间依赖关系
        
        # 性能指标
        self.batch_completion_times = []
        self.node_utilization = {}
        self.iteration_times = []  # 每个迭代的完成时间
        self.throughput_samples = []  # 吞吐量采样点
        
        # 用于数据并行的特定属性
        self.gradient_aggregation_stages = {}  # 记录需要梯度聚合的阶段
        self.parameter_sync_frequency = self.config.get("parameter_sync_frequency", 1)  # 参数同步频率
        self.scheduled_transmissions = set()  # 记录已经调度的传输任务
        
        # 组信息
        self.groups = []  # 存储所有组
        self.group_stages = {}  # 每个组内的流水线阶段
        self.node_to_group = {}  # 节点到组的映射
        self.node_to_stage = {}  # 节点到阶段的映射
        
        # 并行度配置
        self.pipeline_parallel_size = 0  # 流水线并行度，将在setup_simulation中设置
        self.data_parallel_size = self.config.get("data_parallel_size", 1)  # 数据并行度
        
        # Ring-AllReduce 相关
        self.ring_allreduce_status = {}  # 记录每个组的Ring-AllReduce状态
        self.num_gradient_chunks = self.config.get("num_gradient_chunks", 4)  # 梯度分块数量
        
        # 背景流量配置
        background_traffic_config = self.config.get("background_traffic", {"mode": "none"})
        self.background_traffic = BackgroundTrafficGenerator(self, background_traffic_config)
        
        # 随机种子固定，确保结果可重现
        random_seed = self.config.get("random_seed", 42)
        random.seed(random_seed)
        
        # 通信量统计
        self.total_communication_volume = 0  # 总通信量（MB）
        self.forward_communication_volume = 0  # 前向传播通信量
        self.backward_communication_volume = 0  # 反向传播通信量
        self.parameter_communication_volume = 0  # 参数同步通信量

    def schedule_event(self, time, event_type, data, priority=0):
        """安排新事件"""
        heapq.heappush(self.event_heap, Event(time, event_type, data, priority))

    def setup_simulation(self):
        """设置仿真环境"""
        # 读取网络拓扑
        topology_file = self.config.get("topology_file", "fattree.txt")
        topology_file = os.path.join("topo", topology_file)

        num_nodes = self.network.read_adjacency_matrix(topology_file)
        
        # 初始化计算节点
        for i in range(num_nodes):
            # 可以为不同节点设置不同的计算能力
            compute_power = self.config.get("node_compute_power", {}).get(str(i), 1.0)
            self.nodes[i] = ComputeNode(i, compute_power)
        
        # 解析训练配置
        self.parse_training_config(num_nodes)

        if "routing_algorithm" not in self.network_config:
            self.network_config["routing_algorithm"] = "dijkstra"  # 默认使用Dijkstra
            
        
        # 设置初始事件
        self.schedule_initial_events()
        
    def parse_training_config(self, num_nodes):
        """解析训练配置"""
        # 获取基本配置
        self.packet_size = self.config.get("packet_size", 1)
        
        # 解析计算时间配置
        compute_times_config = self.config.get("compute_times", [0.1])
        if isinstance(compute_times_config, dict):
            # 如果是字典格式，解析为每个阶段的计算时间
            self.compute_times = []
            for i in range(100):  # 假设最多100个阶段
                stage_key = str(i)
                if stage_key in compute_times_config:
                    self.compute_times.append(float(compute_times_config[stage_key]))
                elif i < len(self.compute_times):
                    # 如果没有指定，使用最后一个指定的值
                    self.compute_times.append(self.compute_times[-1])
                else:
                    # 如果没有任何指定值，使用默认值
                    self.compute_times.append(0.1)
        elif isinstance(compute_times_config, list):
            # 如果是列表格式，直接使用
            self.compute_times = [float(t) for t in compute_times_config]
        else:
            # 如果是单个值，转换为列表
            self.compute_times = [float(compute_times_config)]
        
        # 解析分组信息
        groups_config = self.config.get("groups", [])
        self.groups = []
        self.node_to_group = {}
        self.node_to_stage = {}
        self.group_stages = {}
        
        for group_id, group_nodes in enumerate(groups_config):
            nodes = [n for n in group_nodes]
            self.groups.append(nodes)
            
            # 记录组内流水线阶段
            self.group_stages[group_id] = {}
            for stage_id, node in enumerate(nodes):
                self.node_to_group[node] = group_id
                self.node_to_stage[node] = stage_id
                self.group_stages[group_id][stage_id] = node
        
        # 如果没有配置组，创建默认组
        if not self.groups:
            default_group = list(range(min(num_nodes, 4)))  # 使用前4个节点或所有节点
            self.groups.append(default_group)
            self.group_stages[0] = {i: node for i, node in enumerate(default_group)}
            for i, node in enumerate(default_group):
                self.node_to_group[node] = 0
                self.node_to_stage[node] = i
        
        # 设置流水线并行度（每个组的阶段数）
        self.pipeline_parallel_size = max(len(stages) for stages in self.group_stages.values())
        
        # 数据并行度（组的数量）
        if self.data_parallel_size == 0:
            self.data_parallel_size = len(self.groups)

    def calculate_activation_size(self, stage_id, group_id, micro_batch_id):
        """
        计算前向传播激活值大小，考虑模型结构特征
        """
        
        # 获取模型结构参数
        hidden_size = self.config.get("model_config", {}).get("hidden_size", 1024)
        seq_length = self.config.get("model_config", {}).get("seq_length", 1024)
        
        # 每个微批次的激活值大小
        # 隐藏状态: micro_batch_size * seq_length * hidden_size * 精度因子
        activation_size = self.micro_batch_size * seq_length * hidden_size * self.precision_factor
        
        # 转换为MB
        return activation_size * 4 / (1024 * 1024)  # 4字节/单精度浮点数

    def calculate_gradient_size(self, stage_id, group_id, micro_batch_id):
        """
        计算反向传播梯度大小
        
        Args:
            stage_id: 当前阶段ID
            group_id: 组ID
            micro_batch_id: 微批次ID
            
        Returns:
            梯度大小（MB）
        """
        # 每个阶段负责的参数量
        hidden_size = self.config.get("model_config", {}).get("hidden_size", 1024)
        seq_length = self.config.get("model_config", {}).get("seq_length", 1024)
        
        # 每个微批次的激活值大小
        # 隐藏状态: micro_batch_size * seq_length * hidden_size * 精度因子
        activation_size = self.micro_batch_size * seq_length * hidden_size * self.precision_factor
        
        # 转换为MB
        return activation_size * 4 / (1024 * 1024)  # 4字节/单精度浮点数

    def schedule_initial_events(self):
        """根据并行策略安排初始事件"""
        # 为每个组和阶段分配计算时间
        for group_id, stages in self.group_stages.items():
            for stage_id in stages:
                # 确保计算时间索引在范围内
                compute_time_idx = min(stage_id, len(self.compute_times) - 1)
                self.stage_compute_times[(group_id, stage_id)] = self.compute_times[compute_time_idx]
                print(f"组 {group_id} 阶段 {stage_id} (节点: {stages[stage_id]}) 计算时间: {self.compute_times[compute_time_idx]}s")
        
        # 初始化微批次状态
        self.initialize_batch(0)
        
        # 初始化Ring-AllReduce状态
        for group_id in self.group_stages:
            self.ring_allreduce_status[group_id] = {
                "scatter_reduce_complete": False,
                "allgather_complete": False,
                "chunks_received": {node_id: set() for node_id in self.group_stages[group_id].values()},
                "chunks_processed": {node_id: set() for node_id in self.group_stages[group_id].values()}
            }
        
        # 为每个组安排第一个微批次的前向传播
        for group_id, stages in self.group_stages.items():
            first_stage_node = stages[0]  # 每个组的第一个阶段节点
            
            self.schedule_event(0.0, 'start_forward', {
                'micro_batch_id': 0,
                'batch_id': 0,
                'group_id': group_id,
                'stage_id': 0,
                'node_id': first_stage_node,
                'compute_time': self.stage_compute_times[(group_id, 0)]
            }, priority=1)
        
        # 如果启用了背景流量，安排第一个背景流量检查事件
        if self.background_traffic.active:
            self.schedule_event(0.0, 'check_background_traffic', {}, priority=10)

    def initialize_batch(self, batch_id):
        """初始化新批次的状态"""
        print(f"初始化批次 {batch_id}")
        
        # 初始化微批次状态
        for group_id in self.group_stages:
            for micro_batch_id in range(self.micro_batch_count):
                key = (batch_id, group_id, micro_batch_id)
                self.micro_batch_status[key] = {
                    "current_stage": -1,  # -1表示尚未开始
                    "forward_complete": set(),  # 完成前向传播的阶段
                    "backward_complete": set(),  # 完成反向传播的阶段
                    "start_time": None,
                    "end_time": None
                }

    def run_simulation(self):
        print("开始仿真...")
        training_complete = False
        
        while self.event_heap:
            event = heapq.heappop(self.event_heap)
            self.current_time = event.time
            
            # 如果训练已完成，且当前事件是背景流量相关事件，则跳过
            if training_complete and event.event_type in ['check_background_traffic', 'end_traffic_burst']:
                continue
            
            # 处理不同类型的事件
            if event.event_type == 'start_forward':
                self.handle_start_forward(event.data)
            elif event.event_type == 'complete_forward':
                self.handle_complete_forward(event.data)
            elif event.event_type == 'start_backward':
                self.handle_start_backward(event.data)
            elif event.event_type == 'complete_backward':
                self.handle_complete_backward(event.data)
            elif event.event_type == 'start_transmission':
                self.handle_start_transmission(event.data)
            elif event.event_type == 'complete_transmission':
                self.handle_complete_transmission(event.data)
            elif event.event_type == 'start_gradient_aggregation':
                self.handle_start_gradient_aggregation(event.data)
            elif event.event_type == 'complete_gradient_aggregation':
                self.handle_complete_gradient_aggregation(event.data)
            elif event.event_type == 'start_parameter_update':
                self.handle_start_parameter_update(event.data)
            elif event.event_type == 'complete_parameter_update':
                self.handle_complete_parameter_update(event.data)
            elif event.event_type == 'start_ring_allreduce':
                self.handle_start_ring_allreduce(event.data)
            elif event.event_type == 'complete_ring_reduce':
                self.handle_complete_ring_reduce(event.data)
            elif event.event_type == 'complete_ring_gather':
                self.handle_complete_ring_gather(event.data)
            elif event.event_type == 'check_background_traffic':
                self.handle_check_background_traffic(event.data)
            elif event.event_type == 'end_traffic_burst':
                self.handle_end_traffic_burst(event.data)
            elif event.event_type == 'start_next_batch':
                self.handle_start_next_batch(event.data)
            
            # 检查训练是否已完成
            if self._is_training_complete():
                training_complete = True
                # 清除所有背景流量相关的事件
                self._clear_background_traffic_events()
        
        print(f"仿真完成，总时间: {self.current_time:.3f}s")
        # if training_complete:
        self.routing_stats.update(self.network.get_routing_statistics())
        self.print_statistics()
        
    def generate_visualization_data(self):
        """生成前端可视化所需的数据"""
        # 基本统计数据
        result = {
            "simulation_time": self.current_time,
            "completed_batches": self.current_batch,
            "throughput": {
                "average": sum(t for _, t in self.throughput_samples) / len(self.throughput_samples) if self.throughput_samples else 0,
                "samples": self.throughput_samples
            },
            "communication_volume": {
                "forward": self.forward_communication_volume,
                "backward": self.backward_communication_volume,
                "parameter": self.parameter_communication_volume,
                "total": self.total_communication_volume
            },
            "iteration_times": self.iteration_times,
            "network_stats": self.network.get_network_stats(),
            "routing_stats": self.network.get_routing_statistics()
        }
        
        # 添加路由性能数据
        if hasattr(self.network, 'routing_performance_samples') and self.network.routing_performance_samples:
            # 检查样本的格式
            sample = self.network.routing_performance_samples[0]
            if isinstance(sample, tuple):
                if len(sample) == 3:  # 如果样本包含3个元素 (time, utilization, load_balance)
                    result["routing_performance"] = {
                        "timestamps": [t for t, _, _ in self.network.routing_performance_samples],
                        "path_utilization": [u for _, u, _ in self.network.routing_performance_samples],
                        "load_balance": [b for _, _, b in self.network.routing_performance_samples]
                    }
                elif len(sample) == 2:  # 如果样本包含2个元素 (time, utilization)
                    result["routing_performance"] = {
                        "timestamps": [t for t, _ in self.network.routing_performance_samples],
                        "path_utilization": [u for _, u in self.network.routing_performance_samples],
                        "load_balance": []  # 没有负载均衡数据
                    }
                else:
                    # 未知格式，提供空数据
                    result["routing_performance"] = {
                        "timestamps": [],
                        "path_utilization": [],
                        "load_balance": []
                    }
            else:
                # 如果不是元组格式，提供空数据
                result["routing_performance"] = {
                    "timestamps": [],
                    "path_utilization": [],
                    "load_balance": []
                }
        else:
            # 如果没有路由性能样本，提供空数据
            result["routing_performance"] = {
                "timestamps": [],
                "path_utilization": [],
                "load_balance": []
            }
        
        return result




    def handle_start_next_batch(self, data):
        """处理开始下一个批次的事件"""
        batch_id = data['batch_id']
        
        # 初始化新批次
        self.initialize_batch(batch_id)
        
        # 为每个组安排第一个微批次的前向传播
        for group_id, stages in self.group_stages.items():
            first_stage_node = stages[0]  # 每个组的第一个阶段节点
            
            self.schedule_event(self.current_time, 'start_forward', {
                'micro_batch_id': 0,
                'batch_id': batch_id,
                'group_id': group_id,
                'stage_id': 0,
                'node_id': first_stage_node,
                'compute_time': self.stage_compute_times[(group_id, 0)]
            }, priority=1)
        
        print(f"[{self.current_time:.3f}s] 开始批次 {batch_id}")

    def _is_training_complete(self):
        """检查训练是否已完成"""
        # 检查是否已完成所有批次
        
        if self.current_batch >= self.num_batches:
            # 检查最后一个批次是否完成
            last_batch_complete = True
            for group_id in self.group_stages:
                for micro_batch_id in range(self.micro_batch_count):
                    key = (self.num_batches - 1, group_id, micro_batch_id)
                    if key in self.micro_batch_status:
                        stages = self.group_stages[group_id]
                        if len(self.micro_batch_status[key]["backward_complete"]) < len(stages):
                            last_batch_complete = False
                            break
                if not last_batch_complete:
                    break
            
            if last_batch_complete:
                # 检查是否有正在进行的参数更新或梯度聚合
                for event in self.event_heap:
                    if event.event_type in ['start_parameter_update', 'complete_parameter_update', 
                                        'start_ring_allreduce', 'complete_ring_reduce', 
                                        'complete_ring_gather', 'start_gradient_aggregation',
                                        'complete_gradient_aggregation']:
                        return False
                
                # 检查是否有非背景传输
                for event in self.event_heap:
                    if event.event_type in ['start_transmission', 'complete_transmission']:
                        if 'is_background' in event.data and event.data['is_background']:
                            continue
                        if 'packet' in event.data and hasattr(event.data['packet'], 'packet_type') and event.data['packet'].packet_type == 'background':
                            continue
                        return False
                
                # 检查是否有节点仍在忙碌（非背景任务）
                for node in self.nodes.values():
                    if node.busy and (node.current_task is None or node.current_task.get('type') != 'background'):
                        return False
                print("检查完成")
                
                return True
        
        return False

    def _clear_background_traffic_events(self):
        """清除所有背景流量相关的事件"""
        new_event_heap = []
        for event in self.event_heap:
            # 保留非背景流量相关的事件
            if event.event_type not in ['check_background_traffic', 'end_traffic_burst']:
                # 对于传输事件，检查是否是背景流量
                if event.event_type in ['start_transmission', 'complete_transmission']:
                    if 'is_background' in event.data and event.data['is_background']:
                        continue
                    if 'packet' in event.data and hasattr(event.data['packet'], 'packet_type') and event.data['packet'].packet_type == 'background':
                        continue
                new_event_heap.append(event)
        
        # 重建事件堆
        self.event_heap = []
        for event in new_event_heap:
            heapq.heappush(self.event_heap, event)
        
        print(f"[{self.current_time:.3f}s] 训练完成，已清除所有背景流量事件。")

    def handle_check_background_traffic(self, data):
        """处理背景流量检查事件"""
        # 生成背景流量
        self.background_traffic.schedule_background_traffic(self.current_time)
        
        # 安排下一次背景流量检查
        next_check_time = self.current_time + 0.1  # 每0.1秒检查一次
        self.schedule_event(next_check_time, 'check_background_traffic', {}, priority=10)

    def handle_end_traffic_burst(self, data):
        """处理结束流量突发事件"""
        self.background_traffic.end_burst()

    def handle_start_forward(self, data):
        """处理开始前向传播事件"""
        micro_batch_id = data['micro_batch_id']
        batch_id = data.get('batch_id', 0)  # 默认为批次0
        group_id = data['group_id']
        stage_id = data['stage_id']
        node_id = data['node_id']
        compute_time = data['compute_time']
        
        # 更新微批次状态
        key = (batch_id, group_id, micro_batch_id)
        if key in self.micro_batch_status:
            if self.micro_batch_status[key]["current_stage"] < stage_id:
                self.micro_batch_status[key]["current_stage"] = stage_id
        else:
            print(f"警告: 微批次状态未找到 - 批次:{batch_id}, 组:{group_id}, 微批次:{micro_batch_id}")
            return
        
        # 如果是第一个阶段且是第一次处理该微批次，记录开始时间
        if stage_id == 0 and self.micro_batch_status[key]["start_time"] is None:
            self.micro_batch_status[key]["start_time"] = self.current_time
        
        # 检查节点是否空闲
        node = self.nodes[node_id]
        if node.busy:
            # 节点忙，将任务加入队列
            node.task_queue.append({
                'type': 'forward',
                'micro_batch_id': micro_batch_id,
                'batch_id': batch_id,
                'group_id': group_id,
                'stage_id': stage_id,
                'compute_time': compute_time
            })
            return
        
        # 根据节点计算能力调整计算时间
        adjusted_compute_time = compute_time / node.compute_power
    
        # 节点开始计算，更新统计信息
        node.start_computation(self.current_time, 'forward', adjusted_compute_time)
        node.current_task = {
            'type': 'forward',
            'micro_batch_id': micro_batch_id,
            'batch_id': batch_id,
            'group_id': group_id,
            'stage_id': stage_id
        }
        
        # 更新节点统计信息
        node.forward_count += 1
        
        print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 微批次 {micro_batch_id} 在节点 {node_id} 开始前向计算 (阶段 {stage_id})")
        
        # 安排完成事件
        self.schedule_event(node.busy_until, 'complete_forward', {
            'micro_batch_id': micro_batch_id,
            'batch_id': batch_id,
            'group_id': group_id,
            'stage_id': stage_id,
            'node_id': node_id
        })

    def handle_complete_forward(self, data):
        """处理完成前向传播事件"""
        micro_batch_id = data['micro_batch_id']
        batch_id = data.get('batch_id', 0)  # 默认为批次0
        group_id = data['group_id']
        stage_id = data['stage_id']
        node_id = data['node_id']
        
        # 更新节点状态
        node = self.nodes[node_id]
        node.end_computation(self.current_time)
        node.current_task = None
        
        # 更新微批次状态
        key = (batch_id, group_id, micro_batch_id)
        if key in self.micro_batch_status:
            self.micro_batch_status[key]["forward_complete"].add(stage_id)
        else:
            print(f"警告: 微批次状态未找到 - 批次:{batch_id}, 组:{group_id}, 微批次:{micro_batch_id}")
        print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 微批次 {micro_batch_id} 在节点 {node_id} 完成前向计算 (阶段 {stage_id})")
        
        # 处理节点队列中的下一个任务
        if node.task_queue:
            next_task = node.task_queue.pop(0)
            next_task["node_id"] = node_id
            self.schedule_event(self.current_time, f"start_{next_task['type']}", next_task)
        
        # 如果不是最后一个阶段，安排下一个阶段的前向传播
        stages = self.group_stages[group_id]
        if stage_id < max(stages.keys()):
            next_stage = stage_id + 1
            next_node = stages[next_stage]
            
            # 计算激活值大小
            activation_size = self.calculate_activation_size(stage_id, group_id, micro_batch_id)
            
            # 更新通信统计
            self.forward_communication_volume += activation_size
            self.total_communication_volume += activation_size
            
            # 安排数据传输
            print(micro_batch_id)
            self.schedule_event(self.current_time, 'start_transmission', {
                'micro_batch_id': micro_batch_id,
                'batch_id': batch_id,
                'src_node': node_id,
                'dest_node': next_node,
                'group_id': group_id,
                'size': activation_size,
                'direction': 'forward'
            })
        else:
            # 如果是最后一个阶段，开始反向传播
            self.schedule_event(self.current_time, 'start_backward', {
                'micro_batch_id': micro_batch_id,
                'batch_id': batch_id,
                'group_id': group_id,
                'stage_id': stage_id,
                'node_id': node_id,
                'compute_time': self.stage_compute_times[(group_id, stage_id)]
            })
        
        # 如果是第一个阶段，并且下一个微批次未超过总数，安排下一个微批次
        if stage_id == 0 and micro_batch_id + 1 < self.micro_batch_count:
            self.schedule_event(self.current_time, 'start_forward', {
                'micro_batch_id': micro_batch_id + 1,
                'batch_id': batch_id,
                'group_id': group_id,
                'stage_id': 0,
                'node_id': node_id,
                'compute_time': self.stage_compute_times[(group_id, 0)]
            })

    def handle_start_backward(self, data):
        """处理开始反向传播事件"""
        micro_batch_id = data['micro_batch_id']
        batch_id = data.get('batch_id', 0)  # 默认为批次0
        group_id = data['group_id']
        stage_id = data['stage_id']
        node_id = data['node_id']
        compute_time = data['compute_time']
        
        # 检查节点是否空闲
        node = self.nodes[node_id]
        if node.busy:
            # 节点忙，将任务加入队列
            node.task_queue.append({
                'type': 'backward',
                'micro_batch_id': micro_batch_id,
                'batch_id': batch_id,
                'group_id': group_id,
                'stage_id': stage_id,
                'compute_time': compute_time
            })
            return
        
        # 根据节点计算能力调整计算时间
        adjusted_compute_time = compute_time / node.compute_power
        
        # 节点空闲，开始计算 - 修复：使用'backward'而不是'forward'
        node.start_computation(self.current_time, 'backward', adjusted_compute_time)
        node.current_task = {
            'type': 'backward',  # 修复：使用'backward'而不是'forward'
            'micro_batch_id': micro_batch_id,
            'batch_id': batch_id,
            'group_id': group_id,
            'stage_id': stage_id
        }
        
        # 更新节点统计信息
        node.backward_count += 1
        
        print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 微批次 {micro_batch_id} 在节点 {node_id} 开始反向计算 (阶段 {stage_id})")
        
        # 安排完成事件
        self.schedule_event(node.busy_until, 'complete_backward', {
            'micro_batch_id': micro_batch_id,
            'batch_id': batch_id,
            'group_id': group_id,
            'stage_id': stage_id,
            'node_id': node_id
        })

    def handle_complete_backward(self, data):
        """处理完成反向传播事件"""
        micro_batch_id = data['micro_batch_id']
        batch_id = data.get('batch_id', 0)  # 默认为批次0
        group_id = data['group_id']
        stage_id = data['stage_id']
        node_id = data['node_id']
        
        # 更新节点状态
        node = self.nodes[node_id]
        node.end_computation(self.current_time)
        node.current_task = None
        
        # 更新微批次状态
        key = (batch_id, group_id, micro_batch_id)
        if key in self.micro_batch_status:
            self.micro_batch_status[key]["backward_complete"].add(stage_id)
        else:
            print(f"警告: 微批次状态未找到 - 批次:{batch_id}, 组:{group_id}, 微批次:{micro_batch_id}")
        
        print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 微批次 {micro_batch_id} 在节点 {node_id} 完成反向计算 (阶段 {stage_id})")
        
        # 处理节点队列中的下一个任务
        if node.task_queue:
            next_task = node.task_queue.pop(0)
            next_task["node_id"] = node_id
            self.schedule_event(self.current_time, f"start_{next_task['type']}", next_task)
        
        # 如果不是第一个阶段，安排前一个阶段的反向传播
        if stage_id > 0:
            prev_stage = stage_id - 1
            prev_node = self.group_stages[group_id][prev_stage]
            
            # 计算梯度大小
            gradient_size = self.calculate_gradient_size(stage_id, group_id, micro_batch_id)
            
            # 更新通信统计
            self.backward_communication_volume += gradient_size
            self.total_communication_volume += gradient_size
            
            # 安排数据传输
            self.schedule_event(self.current_time, 'start_transmission', {
                'micro_batch_id': micro_batch_id,
                'batch_id': batch_id,
                'src_node': node_id,
                'dest_node': prev_node,
                'group_id': group_id,
                'size': gradient_size,
                'direction': 'backward'
            })
        else:
            # 如果是第一个阶段，检查是否所有微批次都已完成该批次的反向传播
            all_complete = True
            for mb_id in range(self.micro_batch_count):
                mb_key = (batch_id, group_id, mb_id)
                if mb_key in self.micro_batch_status and 0 not in self.micro_batch_status[mb_key]["backward_complete"]:
                    all_complete = False
                    break
            
            if all_complete:
                # 所有微批次完成，开始梯度聚合
                if self.parallel_mode in ["data", "hybrid"]:
                    self.schedule_event(self.current_time, 'start_ring_allreduce', {
                        'group_id': group_id,
                        'batch_id': batch_id
                    })
                else:
                    # 流水线并行模式下，直接进行参数更新
                    self.schedule_event(self.current_time, 'start_parameter_update', {
                        'group_id': group_id,
                        'batch_id': batch_id
                    })
        
        # 检查该微批次是否完成所有阶段的反向传播
        stages = self.group_stages[group_id]
        if key in self.micro_batch_status and len(self.micro_batch_status[key]["backward_complete"]) == len(stages):
            # 记录完成时间
            self.micro_batch_status[key]["end_time"] = self.current_time
            if self.micro_batch_status[key]["start_time"] is not None:
                completion_time = self.micro_batch_status[key]["end_time"] - self.micro_batch_status[key]["start_time"]
                self.batch_completion_times.append(completion_time)
                print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 微批次 {micro_batch_id} 完成所有计算，总耗时: {completion_time:.3f}s")

    def handle_start_transmission(self, data):
        """处理开始数据传输事件"""
        micro_batch_id = data['micro_batch_id']
        batch_id = data.get('batch_id', 0)  # 默认为批次0
        src_node = data['src_node']
        dest_node = data['dest_node']
        group_id = data.get('group_id', -1)
        size = data['size']
        direction = data['direction']
        is_background = data.get('is_background', False)
        
        # 使用网络管理器开始传输
        success = self.network.start_transmission(
            self.current_time, 
            micro_batch_id, 
            src_node, 
            dest_node, 
            size, 
            direction, 
            group_id=group_id,
            chunk_id=data.get('chunk_id', 0),
            iteration=data.get('iteration', 0),
            is_background=is_background,
            batch_id=batch_id
        )
        
        if not success and not data.get('retransmission', False) and not is_background:
            print(f"⚠️ [{self.current_time:.3f}s] 传输失败: {src_node}→{dest_node}")

    def handle_complete_transmission(self, data):
        """处理完成数据传输事件"""
        link_key = data['link']
        packet = data['packet']
        
        # 使用网络管理器处理传输完成
        success, completed_packet = self.network.handle_transmission_complete(
            self.current_time, 
            link_key, 
            packet
        )
        
        if success:
            # 数据包已到达最终目的地
            micro_batch_id = packet.micro_batch_id
            batch_id = getattr(packet, 'batch_id', 0)  # 默认为批次0
            src_node = packet.src
            dest_node = packet.final_dest
            direction = packet.packet_type
            group_id = packet.group_id

            # 如果是背景流量，不需要进一步处理
            if direction == 'background':
                return
            
            if direction == 'forward':
                # 前向传播数据到达，安排下一阶段的计算
                stage_id = self.node_to_stage[dest_node]
                self.schedule_event(self.current_time, 'start_forward', {
                    'micro_batch_id': micro_batch_id,
                    'batch_id': batch_id,
                    'group_id': group_id,
                    'stage_id': stage_id,
                    'node_id': dest_node,
                    'compute_time': self.stage_compute_times[(group_id, stage_id)]
                })
            elif direction == 'backward':
                # 反向传播数据到达，安排前一阶段的反向计算
                stage_id = self.node_to_stage[dest_node]
                self.schedule_event(self.current_time, 'start_backward', {
                    'micro_batch_id': micro_batch_id,
                    'batch_id': batch_id,
                    'group_id': group_id,
                    'stage_id': stage_id,
                    'node_id': dest_node,
                    'compute_time': self.stage_compute_times[(group_id, stage_id)]
                })
            elif direction in ['ring_reduce', 'ring_gather']:
                # Ring-AllReduce 数据到达，处理相应阶段
                if direction == 'ring_reduce':
                    self.handle_ring_reduce_received(packet)
                else:
                    self.handle_ring_gather_received(packet)
            elif direction == 'parameter':
                # 参数同步数据到达，更新本地参数
                print(f"[{self.current_time:.3f}s] 批次 {batch_id} 参数同步完成: {src_node}→{dest_node}")

    def handle_start_ring_allreduce(self, data):
        """处理开始Ring-AllReduce事件"""
        group_id = data['group_id']
        batch_id = data.get('batch_id', 0)  # 默认为批次0
        
        print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 开始Ring-AllReduce梯度聚合")
        
        # 获取组内所有节点
        nodes = list(self.group_stages[group_id].values())
        num_nodes = len(nodes)
        
        # 确保梯度块数量至少等于节点数量
        if self.num_gradient_chunks < num_nodes:
            print(f"警告: 梯度块数量({self.num_gradient_chunks})小于节点数量({num_nodes})，可能导致不均匀分配")
            # 可以选择调整块数量为节点数量的倍数
            self.num_gradient_chunks = num_nodes
            print(f"已调整梯度块数量为: {self.num_gradient_chunks}")
        
        # 为每个节点初始化梯度块
        for node_id in nodes:
            self.nodes[node_id].gradient_chunks = {}
            for chunk_id in range(self.num_gradient_chunks):
                # 每个节点负责自己的梯度块
                self.nodes[node_id].gradient_chunks[chunk_id] = True
        
        # 每个阶段负责的参数量
        params_per_stage = self.total_params * 1000000 / self.pipeline_parallel_size
        
        # 计算Ring-AllReduce的总通信量 (理论值)
        # Ring-AllReduce算法中，每个节点需要发送和接收(N-1)次，但总参数量被分成了N份
        # 因此总通信量为 2(N-1)/N * 参数量
        total_allreduce_volume = 2 * (num_nodes - 1) / num_nodes * params_per_stage
        
        # 记录总通信量统计 (仅用于统计，不影响实际仿真)
        allreduce_volume_mb = total_allreduce_volume * 4 / (1024 * 1024) * self.precision_factor
        self.parameter_communication_volume += allreduce_volume_mb
        self.total_communication_volume += allreduce_volume_mb
        
        # 开始scatter-reduce阶段
        for node_id in nodes:
            for chunk_id in range(self.num_gradient_chunks):
                # 计算发送目标节点 (环形拓扑中的下一个节点)
                send_to = nodes[(nodes.index(node_id) + 1) % num_nodes]
                
                # 只发送自己负责的块
                if chunk_id % num_nodes == nodes.index(node_id):
                    # 计算每个梯度块的大小
                    chunk_size = (params_per_stage / self.num_gradient_chunks) * 4 / (1024 * 1024) * self.precision_factor
                    print(f"[{self.current_time:.3f}s] 安排节点{node_id}发送块{chunk_id}到节点{send_to}")
                    
                    self.schedule_event(self.current_time, 'start_transmission', {
                        'micro_batch_id': 0,  # 使用固定ID
                        'batch_id': batch_id,
                        'src_node': node_id,
                        'dest_node': send_to,
                        'group_id': group_id,
                        'size': chunk_size,
                        'direction': 'ring_reduce',
                        'chunk_id': chunk_id,
                        'iteration': 0  # 第一次迭代
                    })

    def handle_ring_reduce_received(self, packet):
        """处理接收到Ring-Reduce数据包"""
        dest_node = packet.final_dest
        chunk_id = packet.chunk_id
        iteration = packet.iteration
        group_id = packet.group_id
        batch_id = getattr(packet, 'batch_id', 0)  # 默认为批次0
        
        # 获取组内所有节点
        nodes = list(self.group_stages[group_id].values())
        num_nodes = len(nodes)
        node_index = nodes.index(dest_node)
        
        print(f"[{self.current_time:.3f}s] 块传输完成: {dest_node} 接收块 {chunk_id} (迭代 {iteration})")
        
        # 标记该块已接收
        if not hasattr(self.nodes[dest_node], 'received_gradients'):
            self.nodes[dest_node].received_gradients = {}
        if chunk_id not in self.nodes[dest_node].received_gradients:
            self.nodes[dest_node].received_gradients[chunk_id] = set()
        self.nodes[dest_node].received_gradients[chunk_id].add(iteration)
        
        # 如果不是最后一次迭代，继续传递
        if iteration < num_nodes - 1:  # n-1次迭代完成scatter-reduce
            # 计算发送目标节点
            send_to = nodes[(node_index + 1) % num_nodes]
            
            # 安排下一次传输
            print(f"[{self.current_time:.3f}s] 块传输完成: {dest_node} 发送块 {chunk_id} (迭代 {iteration+1}) 到 {send_to}")  
            self.schedule_event(self.current_time, 'start_transmission', {
                'micro_batch_id': 0,
                'batch_id': batch_id,
                'src_node': dest_node,
                'dest_node': send_to,
                'group_id': group_id,
                'size': packet.size,
                'direction': 'ring_reduce',
                'chunk_id': chunk_id,
                'iteration': iteration + 1
            })
        else:
            # 完成最后一次迭代
            # 检查该节点负责的块是否都已接收完成
            # 在Ring-AllReduce中，每个节点负责处理 chunk_id % num_nodes == node_index 的块
            responsible_chunks = [c_id for c_id in range(self.num_gradient_chunks) if c_id % num_nodes == node_index]
            
            # 检查该节点负责的所有块是否都完成了接收
            all_responsible_complete = True
            for c_id in responsible_chunks:
                # 对于负责的块，检查是否收到了足够的迭代
                if c_id not in self.nodes[dest_node].received_gradients or \
                num_nodes - 1 not in self.nodes[dest_node].received_gradients[c_id]:
                    all_responsible_complete = False
                    break
            
            if all_responsible_complete:
                print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 节点 {dest_node} 完成负责的所有块的Scatter-Reduce")
                # 该节点负责的所有块都完成了scatter-reduce，标记该节点完成
                self.schedule_event(self.current_time, 'complete_ring_reduce', {
                    'node_id': dest_node,
                    'group_id': group_id,
                    'batch_id': batch_id
                })

    def handle_complete_ring_reduce(self, data):
        """处理完成Ring-Reduce阶段事件"""
        node_id = data['node_id']
        group_id = data['group_id']
        batch_id = data.get('batch_id', 0)  # 默认为批次0
        
        # 获取组内所有节点
        nodes = list(self.group_stages[group_id].values())
        num_nodes = len(nodes)
        
        # 标记该节点已完成scatter-reduce
        if not hasattr(self, 'ring_reduce_completed'):
            self.ring_reduce_completed = {}
        if group_id not in self.ring_reduce_completed:
            self.ring_reduce_completed[group_id] = set()
        
        self.ring_reduce_completed[group_id].add(node_id)
        
        # 修正：检查组内所有节点是否都完成了scatter-reduce
        # 应该等待所有节点完成，而不是块数量
        if len(self.ring_reduce_completed[group_id]) == num_nodes:
            print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 完成Ring-AllReduce的Scatter-Reduce阶段")
            
            # 开始allgather阶段 - 每个节点只发送自己负责的块
            for i, n_id in enumerate(nodes):
                # 确定该节点负责的块
                responsible_chunks = [c_id for c_id in range(self.num_gradient_chunks) if c_id % num_nodes == i]
                
                for chunk_id in responsible_chunks:
                    # 计算发送目标节点
                    send_to = nodes[(i + 1) % num_nodes]
                    
                    print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 安排节点 {n_id} 发送块 {chunk_id} 到节点 {send_to} 进行AllGather")
                    
                    # 计算每个梯度块的大小
                    params_per_stage = self.total_params * 1000000 / self.pipeline_parallel_size
                    chunk_size = (params_per_stage / self.num_gradient_chunks) * 4 / (1024 * 1024) * self.precision_factor
                    
                    self.schedule_event(self.current_time, 'start_transmission', {
                        'micro_batch_id': 0,
                        'batch_id': batch_id,
                        'src_node': n_id,
                        'dest_node': send_to,
                        'group_id': group_id,
                        'size': chunk_size,
                        'direction': 'ring_gather',
                        'chunk_id': chunk_id,
                        'iteration': 0
                    })
            
            # 重置状态，为下一次Ring-AllReduce做准备
            self.ring_reduce_completed[group_id] = set()
        else:
            print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 节点 {node_id} 完成Scatter-Reduce，等待其他节点 ({len(self.ring_reduce_completed[group_id])}/{num_nodes})")

    def handle_ring_gather_received(self, packet):
        """处理接收到Ring-Gather数据包"""
        dest_node = packet.final_dest
        chunk_id = packet.chunk_id
        iteration = packet.iteration
        group_id = packet.group_id
        batch_id = getattr(packet, 'batch_id', 0)  # 默认为批次0
        
        # 获取组内所有节点
        nodes = list(self.group_stages[group_id].values())
        num_nodes = len(nodes)
        node_index = nodes.index(dest_node)
        
        print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 节点 {dest_node} 接收块 {chunk_id} 迭代 {iteration}")
        
        # 确保数据结构已初始化
        if not hasattr(self, 'ring_allgather_status'):
            self.ring_allgather_status = {}
        if group_id not in self.ring_allgather_status:
            self.ring_allgather_status[group_id] = {}
        if dest_node not in self.ring_allgather_status[group_id]:
            self.ring_allgather_status[group_id][dest_node] = set()
        
        # 标记该块已接收
        self.ring_allgather_status[group_id][dest_node].add(chunk_id)
        
        # 如果不是最后一次迭代，继续传递
        # 修正：使用 num_nodes - 1 作为迭代终止条件
        if iteration < num_nodes - 1:  # n-1次迭代完成allgather
            # 计算发送目标节点
            send_to = nodes[(node_index + 1) % num_nodes]
            
            # 安排下一次传输
            self.schedule_event(self.current_time, 'start_transmission', {
                'micro_batch_id': 0,
                'batch_id': batch_id,
                'src_node': dest_node,
                'dest_node': send_to,
                'group_id': group_id,
                'size': packet.size,
                'direction': 'ring_gather',
                'chunk_id': chunk_id,
                'iteration': iteration + 1
            })
        
        # 修正：计算节点应该接收的块数量
        # 每个节点应该接收 (num_nodes - 1) 个块，因为每个节点已经有自己负责的块
        # 但需要考虑块分配不均匀的情况
        
        # 计算该节点负责的块
        responsible_chunks = [c_id for c_id in range(self.num_gradient_chunks) if c_id % num_nodes == node_index]
        
        # 计算节点应该接收的块数量 = 总块数 - 该节点负责的块数
        expected_chunks = self.num_gradient_chunks - len(responsible_chunks)
        
        # 修正：检查是否接收了足够的块
        if len(self.ring_allgather_status[group_id][dest_node]) >= expected_chunks:
            print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 节点 {dest_node} 完成AllGather接收 ({len(self.ring_allgather_status[group_id][dest_node])}/{expected_chunks}块)")
            
            # 标记该节点完成AllGather
            self.schedule_event(self.current_time, 'complete_ring_gather', {
                'node_id': dest_node,
                'group_id': group_id,
                'batch_id': batch_id
            })

    def handle_complete_ring_gather(self, data):
        """处理完成Ring-Gather阶段事件"""
        node_id = data['node_id']
        group_id = data['group_id']
        batch_id = data.get('batch_id', 0)  # 默认为批次0
        
        # 获取组内所有节点
        nodes = list(self.group_stages[group_id].values())
        
        # 确保ring_gather_completed存在
        if not hasattr(self, 'ring_gather_completed'):
            self.ring_gather_completed = {}
        if group_id not in self.ring_gather_completed:
            self.ring_gather_completed[group_id] = set()
        
        # 标记该节点已完成allgather
        self.ring_gather_completed[group_id].add(node_id)
        
        print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 节点 {node_id} 完成Ring-AllGather ({len(self.ring_gather_completed[group_id])}/{len(nodes)})")
        
        # 检查组内所有节点是否都完成了allgather
        if len(self.ring_gather_completed[group_id]) == len(nodes):
            print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 完成Ring-AllReduce的AllGather阶段")
            
            # 完成Ring-AllReduce，开始参数更新
            self.schedule_event(self.current_time, 'start_parameter_update', {
                'group_id': group_id,
                'batch_id': batch_id
            })
            
            # 重置Ring-AllGather状态，为下一次做准备
            self.ring_gather_completed[group_id] = set()
            
            # 如果使用了ring_allgather_status，也需要重置
            if hasattr(self, 'ring_allgather_status') and group_id in self.ring_allgather_status:
                for node in nodes:
                    if node in self.ring_allgather_status[group_id]:
                        self.ring_allgather_status[group_id][node] = set()

    def handle_start_parameter_update(self, data):
        """处理开始参数更新事件"""
        group_id = data['group_id']
        batch_id = data.get('batch_id', 0)  # 默认为批次0
        
        print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 开始参数更新")
        
        # 参数更新时间与模型大小相关
        update_time = self.total_params * 0.0001 / 1000  # 假设每百万参数更新需要0.0001秒
        
        # 安排参数更新完成事件
        self.schedule_event(self.current_time + update_time, 'complete_parameter_update', {
            'group_id': group_id,
            'batch_id': batch_id
        })

    def handle_complete_parameter_update(self, data):
        """处理完成参数更新事件"""
        group_id = data['group_id']
        batch_id = data.get('batch_id', 0)  # 默认为批次0
        
        print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 完成参数更新")
        
        # 确保group_updates_completed存在
        if not hasattr(self, 'group_updates_completed'):
            self.group_updates_completed = set()
        
        # 标记该组已完成参数更新
        self.group_updates_completed.add(group_id)
        
        # 如果有多个组，可能需要进行组间参数同步
        if len(self.groups) > 1 and self.parallel_mode == "hybrid":
            # 简单起见，只在第一个组完成时进行组间同步
            if group_id == 0:
                # 获取模型结构参数
                hidden_size = self.config.get("model_config", {}).get("hidden_size", 1024)
                num_layers = self.config.get("model_config", {}).get("num_layers", 24)
                vocab_size = self.config.get("model_config", {}).get("vocab_size", 50000)
                ffn_hidden_size = self.config.get("model_config", {}).get("ffn_hidden_size", hidden_size * 4)
                
                # 计算模型总参数量
                # 1. 自注意力层参数量
                attention_params = 4 * hidden_size * hidden_size * num_layers
                
                # 2. 前馈网络参数量
                ffn_params = (hidden_size * ffn_hidden_size + ffn_hidden_size * hidden_size) * num_layers
                
                # 3. 层归一化参数
                norm_params = 4 * hidden_size * num_layers
                
                # 4. 词嵌入和输出层参数
                embedding_params = vocab_size * hidden_size
                output_params = hidden_size * vocab_size
                
                # 总参数量
                total_params = attention_params + ffn_params + norm_params + embedding_params + output_params
                
                # 计算组间参数同步的总通信量
                # 在混合并行中，需要在数据并行组之间同步参数
                # 每个组需要接收完整的模型参数
                total_sync_volume = 0
                
                for other_group in range(1, len(self.groups)):
                    # 从组0的第一个节点到其他组的第一个节点同步参数
                    src_node = self.group_stages[0][0]
                    dest_node = self.group_stages[other_group][0]
                    
                    print(f"[{self.current_time:.3f}s] 批次 {batch_id} 开始组间参数同步: 组{0}→组{other_group}")
                    
                    # 计算参数同步大小 (MB)
                    # 在流水线并行中，每个组只需要同步其负责的参数部分
                    # 但在混合并行中，可能需要同步全部参数
                    params_size = self.total_params*1000000 * 4 / (1024 * 1024) * self.precision_factor
                    
                    # 累计总同步通信量
                    total_sync_volume += params_size
                    
                    # 安排参数同步传输
                    self.schedule_event(self.current_time, 'start_transmission', {
                        'micro_batch_id': 0,
                        'batch_id': batch_id,
                        'src_node': src_node,
                        'dest_node': dest_node,
                        'group_id': -1,  # 组间传输
                        'size': params_size,
                        'direction': 'parameter'
                    })
                
                # 更新通信统计
                self.parameter_communication_volume += total_sync_volume
                self.total_communication_volume += total_sync_volume
        
        # 检查是否所有组都完成了参数更新
        if len(self.group_updates_completed) == len(self.groups):
            # 记录当前批次的完成时间
            batch_end_time = self.current_time
            if hasattr(self, 'last_batch_end_time'):
                iteration_time = batch_end_time - self.last_batch_end_time
                self.iteration_times.append(iteration_time)
                throughput = self.batch_size / iteration_time
                self.throughput_samples.append((self.current_time, throughput))
                print(f"[{self.current_time:.3f}s] 批次 {batch_id} 完成，耗时: {iteration_time:.3f}s, 吞吐量: {throughput:.2f} 样本/秒")
            
            # 更新最后一个批次的完成时间
            self.last_batch_end_time = batch_end_time
            
            # 重置组更新完成状态
            self.group_updates_completed = set()
            
            # 开始下一个批次
            self.current_batch = batch_id + 1
            if self.current_batch < self.num_batches:
                self.schedule_event(self.current_time, 'start_next_batch', {
                    'batch_id': self.current_batch
                })
            else:
                print(f"[{self.current_time:.3f}s] 所有 {self.num_batches} 个批次训练完成!")


    def handle_start_gradient_aggregation(self, data):
        """处理开始梯度聚合事件"""
        group_id = data['group_id']
        batch_id = data.get('batch_id', 0)
        
        print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 开始梯度聚合")
        
        # 梯度聚合时间与模型大小和数据并行度相关
        aggregation_time = self.total_params * 0.0001 * self.data_parallel_size / 1000  # 假设每百万参数聚合需要0.0001秒
        
        # 安排梯度聚合完成事件
        self.schedule_event(self.current_time + aggregation_time, 'complete_gradient_aggregation', {
            'group_id': group_id,
            'batch_id': batch_id
        })

    def handle_complete_gradient_aggregation(self, data):
        """处理完成梯度聚合事件"""
        group_id = data['group_id']
        batch_id = data.get('batch_id', 0)
        
        print(f"[{self.current_time:.3f}s] 批次 {batch_id} 组 {group_id} 完成梯度聚合")
        
        # 梯度聚合完成后，开始参数更新
        self.schedule_event(self.current_time, 'start_parameter_update', {
            'group_id': group_id,
            'batch_id': batch_id
        })

    def print_statistics(self):
        """打印仿真统计信息"""
        print("\n===== 仿真统计 =====")

        # 添加路由统计信息
        print("\n路由统计:")
        print(f"  路由算法: {self.network_config.get('routing_algorithm', 'dijkstra')}")
        
        if self.network_config.get('routing_algorithm') == 'ecmp':
            print(f"  ECMP策略: {self.network_config.get('ecmp_strategy', 'hash_based')}")
            print(f"  最大等价路径数: {self.network_config.get('ecmp_max_paths', 8)}")
        
        # 从网络管理器获取路由统计
        routing_stats = self.network.get_routing_statistics()
        
        print(f"  平均路径长度: {routing_stats.get('average_path_length', 0):.2f}")
        print(f"  路径多样性: {routing_stats.get('path_diversity', 0):.2f}")
        print(f"  路由计算次数: {routing_stats.get('routing_calculations', 0)}")
        print(f"  链路负载均衡度: {routing_stats.get('load_balance_score', 0):.2f}")
        
        # 训练吞吐量统计
        if self.throughput_samples:
            avg_throughput = sum(t for _, t in self.throughput_samples) / len(self.throughput_samples)
            max_throughput = max(t for _, t in self.throughput_samples)
            min_throughput = min(t for _, t in self.throughput_samples)
            print(f"训练吞吐量: 平均={avg_throughput:.2f} 样本/秒, 最大={max_throughput:.2f} 样本/秒, 最小={min_throughput:.2f} 样本/秒")
        
        # 迭代时间统计
        if self.iteration_times:
            avg_iter_time = sum(self.iteration_times) / len(self.iteration_times)
            max_iter_time = max(self.iteration_times)
            min_iter_time = min(self.iteration_times)
            print(f"迭代时间: 平均={avg_iter_time:.3f}s, 最大={max_iter_time:.3f}s, 最小={min_iter_time:.3f}s")
        
        # 批次完成时间统计
        if self.batch_completion_times:
            avg_time = sum(self.batch_completion_times) / len(self.batch_completion_times)
            max_time = max(self.batch_completion_times)
            min_time = min(self.batch_completion_times)
            print(f"微批次完成时间: 平均={avg_time:.3f}s, 最大={max_time:.3f}s, 最小={min_time:.3f}s")
        
        # 通信量统计
        print(f"\n通信量统计:")
        print(f"  前向传播通信量: {self.forward_communication_volume:.2f} MB")
        print(f"  反向传播通信量: {self.backward_communication_volume:.2f} MB")
        print(f"  参数同步通信量: {self.parameter_communication_volume:.2f} MB")
        print(f"  总通信量: {self.total_communication_volume:.2f} MB")
        
        # 计算通信与计算比率
        total_compute_time = sum(node.compute_time for node in self.nodes.values())
        if total_compute_time > 0:
            comm_comp_ratio = self.total_communication_volume / total_compute_time
            print(f"  通信/计算比率: {comm_comp_ratio:.2f} MB/s")
        
        # 网络统计
        network_stats = self.network.get_network_stats()  # 修改这一行，使用get_network_stats方法
        
        # 获取链路利用率数据
        link_utilization_data = self.network.get_link_utilization()
        
        # 计算平均链路利用率
        if link_utilization_data:
            # 计算每个链路的平均利用率
            link_utilization = {}
            for link_key, samples in link_utilization_data.items():
                if samples:
                    # 计算平均利用率
                    avg_util = sum(sample.get('utilization', 0) for sample in samples) / len(samples)
                    link_utilization[link_key] = avg_util * 100  # 转换为百分比
            
            if link_utilization:
                avg_utilization = sum(link_utilization.values()) / len(link_utilization)
                max_utilization = max(link_utilization.values()) if link_utilization else 0
                min_utilization = min(link_utilization.values()) if link_utilization else 0
                print(f"\n链路利用率: 平均={avg_utilization:.2f}%, 最大={max_utilization:.2f}%, 最小={min_utilization:.2f}%")
                
                # 打印每个链路的利用率
                print("\n链路利用率详情:")
                for link, util in sorted(link_utilization.items(), key=lambda x: x[1], reverse=True)[:10]:  # 只显示前10个
                    print(f"  链路 {link[0]}->{link[1]}: {util:.2f}%")

        # 节点统计
        print("\n节点统计:")
        for node_id, node in sorted(self.nodes.items()):
            compute_percentage = (node.compute_time / self.current_time) * 100 if self.current_time > 0 else 0
            idle_percentage = 100 - compute_percentage
            print(f"  节点 {node_id}: 前向计算={node.forward_count}次, 反向计算={node.backward_count}次, 计算占比={compute_percentage:.2f}%, 空闲占比={idle_percentage:.2f}%")
        
        # 网络拥塞统计
        congestion_events = getattr(self.network, 'congestion_events', 0)
        if congestion_events > 0:
            print(f"\n网络拥塞事件: {congestion_events}次")
        
        # 丢包统计
        packet_loss_count = sum(link.packet_loss_count for link in self.network.links.values() if hasattr(link, 'packet_loss_count'))
        if packet_loss_count > 0:
            print(f"丢包事件: {packet_loss_count}次")
            
            # 详细的丢包统计
            print("\n丢包详情:")
            for link_key, link in sorted(self.network.links.items()):
                if hasattr(link, 'packet_loss_count') and link.packet_loss_count > 0:
                    print(f"  链路 {link_key[0]}->{link_key[1]}: {link.packet_loss_count}个数据包丢失")
        
        # 重传统计
        retransmission_count = getattr(self.network, 'retransmission_count', 0)
        if retransmission_count > 0:
            print(f"重传事件: {retransmission_count}次")
        
        # 背景流量统计
        if self.background_traffic.active:
            bg_mode = self.background_traffic.mode
            bg_intensity = self.background_traffic.intensity
            print(f"\n背景流量: 模式={bg_mode}, 强度={bg_intensity:.2f}")
            
            # 如果网络管理器跟踪了背景流量
            bg_packets = getattr(self.network, 'background_packets_sent', 0)
            if bg_packets > 0:
                print(f"背景流量数据包: {bg_packets}个")
        
        # 并行配置统计
        print(f"\n并行配置:")
        print(f"  并行模式: {self.parallel_mode}")
        print(f"  流水线并行度: {self.pipeline_parallel_size}")
        print(f"  数据并行度: {self.data_parallel_size}")
        print(f"  总参数量: {self.total_params}M")
        print(f"  批次大小: {self.batch_size}")
        print(f"  微批次数量: {self.micro_batch_count}")
        print(f"  微批次大小: {self.micro_batch_size}")
        print(f"  训练精度: {self.precision}")
        print(f"  激活值检查点: {'启用' if self.activation_checkpointing else '禁用'}")
        
        print(f"\n总仿真时间: {self.current_time:.3f}s")
        print(f"完成批次数: {self.current_batch}/{self.num_batches}")


def main():
    # 检查命令行参数
    if len(sys.argv) < 2:
        print("用法: python simulator.py <config_file.yaml> [output_file.txt]")
        sys.exit(1)
    
    config_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    # 创建并运行仿真器
    start_time = time.time()
    
    # 如果指定了输出文件，同时输出到文件和控制台
    original_stdout = sys.stdout
    output_stream = None
    
    try:
        if output_file:
            output_stream = open(output_file, 'w')
            sys.stdout = Tee(original_stdout, output_stream)
        
        simulator = Simulator(config_file)
        simulator.setup_simulation()
        simulator.run_simulation()
        
        # 生成可视化数据并保存
        if output_file:
            viz_data_file = output_file.replace('.txt', '_viz_data.json')
            import json
            with open(viz_data_file, 'w') as f:
                json.dump(simulator.generate_visualization_data(), f, indent=2)
            print(f"可视化数据已保存至: {viz_data_file}")
        
    finally:
        # 恢复标准输出并关闭文件
        if output_stream:
            sys.stdout = original_stdout
            output_stream.close()
    
    end_time = time.time()
    print(f"\n仿真程序运行时间: {end_time - start_time:.3f}s")


if __name__ == "__main__":
    main()
