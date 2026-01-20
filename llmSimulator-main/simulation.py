import heapq
import random
import sys
import os
import time

class Tee:
    """同时将输出写入文件和标准输出"""
    def __init__(self, *files):
        self.files = files
    
    def write(self, text):
        for f in self.files:
            f.write(text)
    
    def flush(self):
        for f in self.files:
            if hasattr(f, 'flush'):
                f.flush()

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

class Link:
    """网络链路，用于模拟数据传输"""
    def __init__(self, src, dest, bandwidth):
        self.src = src
        self.dest = dest
        self.bandwidth = bandwidth  # Mbps
        self.queue = []
        self.current_transmission = None
        self.busy_until = 0  # 链路空闲时间点

class Packet:
    """网络数据包"""
    def __init__(self, src, final_dest, size, gen_time, group_id, stage_id, micro_batch_id, packet_type):
        self.src = src
        self.final_dest = final_dest
        self.size = size  # MB
        self.gen_time = gen_time
        self.start_time = None
        self.end_time = None
        self.group_id = group_id
        self.stage_id = stage_id
        self.micro_batch_id = micro_batch_id
        self.packet_type = packet_type  # "forward", "backward", "gradient", "parameter"

class ComputeNode:
    """计算节点，管理计算资源"""
    def __init__(self, node_id):
        self.node_id = node_id
        self.busy = False
        self.busy_until = 0
        self.current_task = None
        # 当前节点所处理的任务队列
        self.task_queue = []
        # 用于Ring-AllReduce的状态
        self.received_gradients = {}  # {group_id: {chunk_id: received}}
        self.gradient_chunks = {}  # 存储梯度分块

class Simulator:
    """分布式训练仿真器"""
    def __init__(self, parallel_mode="pipeline"):
        self.parallel_mode = parallel_mode  # "pipeline", "data", "hybrid"
        self.event_heap = []
        self.current_time = 0
        self.nodes = {}  # 计算节点
        self.links = {}  # 网络链路
        self.routing_tables = {}  # 路由表
        self.stage_compute_times = {}  # 每个阶段的计算时间
        
        self.micro_batch_status = {}  # 追踪每个微批次的状态
        self.stage_dependencies = {}  # 阶段间依赖关系
        
        # 性能指标
        self.batch_completion_times = []
        self.link_utilization = {}
        self.node_utilization = {}
        
        # 用于数据并行的特定属性
        self.gradient_aggregation_stages = {}  # 记录需要梯度聚合的阶段
        self.parameter_sync_frequency = 1  # 参数同步频率（每多少批次同步一次）
        self.scheduled_transmissions = set()  # 记录已经调度的传输任务
        
        # 组信息
        self.groups = []  # 存储所有组
        self.group_stages = {}  # 每个组内的流水线阶段
        self.node_to_group = {}  # 节点到组的映射
        self.node_to_stage = {}  # 节点到阶段的映射
        self.micro_batch_count = 0  # 微批次数量
        
        # Ring-AllReduce 相关
        self.ring_allreduce_status = {}  # 记录每个组的Ring-AllReduce状态
        self.num_gradient_chunks = 4  # 梯度分块数量
        
        # 随机种子固定，确保结果可重现
        random.seed(42)

    def read_adjacency_matrix(self, filename):
        """读取邻接矩阵文件，构建网络拓扑"""
        try:
            with open(filename, 'r') as f:
                matrix = []
                for line in f:
                    row = list(map(int, line.strip().split()))
                    matrix.append(row)
            
            num_nodes = len(matrix)
            graph = {node: [] for node in range(num_nodes)}
            
            for i in range(num_nodes):
                # 初始化计算节点
                self.nodes[i] = ComputeNode(i)
                for j in range(num_nodes):
                    bandwidth = matrix[i][j]
                    if bandwidth > 0:
                        graph[i].append(j)
                        self.links[(i, j)] = Link(i, j, bandwidth)
                        self.link_utilization[(i, j)] = []
            
            # 计算路由表
            for node in range(num_nodes):
                self.routing_tables[node] = self.dijkstra(graph, node)
                
            return num_nodes
        except FileNotFoundError:
            print(f"错误：找不到拓扑文件 {filename}")
            sys.exit(1)

    def dijkstra(self, graph, start_node):
        """改进的Dijkstra算法，考虑链路带宽"""
        distances = {node: float('infinity') for node in graph}
        distances[start_node] = 0
        predecessors = {node: None for node in graph}
        visited = set()
        priority_queue = [(0, start_node)]
        
        while priority_queue:
            current_distance, current_node = heapq.heappop(priority_queue)
            
            if current_node in visited:
                continue
                
            visited.add(current_node)
            
            for neighbor in graph[current_node]:
                # 使用带宽的倒数作为权重（带宽越大，权重越小）
                weight = 1.0 / self.links[(current_node, neighbor)].bandwidth
                distance = current_distance + weight
                
                if distance < distances[neighbor]:
                    distances[neighbor] = distance
                    predecessors[neighbor] = current_node
                    heapq.heappush(priority_queue, (distance, neighbor))
        
        # 计算从start_node到每个节点的下一跳
        next_hop = {}
        for node in graph:
            if node == start_node:
                next_hop[node] = None
                continue
                
            if predecessors[node] is None:
                next_hop[node] = None
                continue
                
            # 回溯找到下一跳
            current = node
            while predecessors[current] != start_node and predecessors[current] is not None:
                current = predecessors[current]
            
            next_hop[node] = current
        
        return next_hop

    def read_training_config(self, filename, num_nodes):
        """读取训练配置，支持组内流水线并行和组间数据并行"""
        try:
            with open(filename, 'r') as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
            
            if not lines:
                # 默认配置
                return 1, [0.1], 8, [], {}, {}
            
            first_line = lines[0].split()
            packet_size = int(first_line[0])  # 数据包大小(MB)
            
            # 解析计算时间，支持每阶段不同的计算时间
            if len(first_line) > 1:
                compute_times = [float(t) for t in first_line[1].split(',')]
            else:
                compute_times = [0.1]  # 默认计算时间
                
            self.micro_batch_count = int(first_line[2]) if len(first_line) > 2 else 8  # 微批次数量
            
            # 解析并行类型和配置
            if len(first_line) > 3:
                self.parallel_mode = first_line[3]
                
            if self.parallel_mode == "data" and len(first_line) > 4:
                self.parameter_sync_frequency = int(first_line[4])
            
            if len(first_line) > 5:
                self.num_gradient_chunks = int(first_line[5])
            
            # 解析分组信息 (每行是一个数据并行组，组内节点按流水线阶段排序)
            groups = []
            node_to_group = {}
            node_to_stage = {}
            group_stages = {}
            
            for group_id, line in enumerate(lines[1:]):
                nodes = list(map(int, line.split()))
                nodes = [n-1 if n > 0 else n for n in nodes]  # 调整为0-indexed
                groups.append(nodes)
                
                # 记录组内流水线阶段
                group_stages[group_id] = {}
                for stage_id, node in enumerate(nodes):
                    node_to_group[node] = group_id
                    node_to_stage[node] = stage_id
                    group_stages[group_id][stage_id] = node
            
            self.groups = groups
            self.node_to_group = node_to_group
            self.node_to_stage = node_to_stage
            self.group_stages = group_stages
            
            return packet_size, compute_times, self.micro_batch_count, groups, node_to_group, node_to_stage
        except FileNotFoundError:
            print(f"错误：找不到训练配置文件 {filename}")
            sys.exit(1)

    def schedule_initial_events(self, packet_size, compute_times, micro_batch_count, groups, node_to_group, node_to_stage):
        """根据并行策略安排初始事件"""
        self.node_to_group = node_to_group
        self.node_to_stage = node_to_stage
        
        # 为每个组和阶段分配计算时间
        for group_id, stages in self.group_stages.items():
            for stage_id in stages:
                # 确保计算时间索引在范围内
                compute_time_idx = min(stage_id, len(compute_times) - 1)
                self.stage_compute_times[(group_id, stage_id)] = compute_times[compute_time_idx]
                print(f"组 {group_id} 阶段 {stage_id} (节点: {stages[stage_id]}) 计算时间: {compute_times[compute_time_idx]}s")
        
        # 初始化微批次状态
        for group_id in self.group_stages:
            for micro_batch_id in range(micro_batch_count):
                key = (group_id, micro_batch_id)
                self.micro_batch_status[key] = {
                    "current_stage": -1,  # -1表示尚未开始
                    "forward_complete": set(),  # 完成前向传播的阶段
                    "backward_complete": set(),  # 完成反向传播的阶段
                    "start_time": None,
                    "end_time": None
                }
        
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
                'group_id': group_id,
                'stage_id': 0,
                'node_id': first_stage_node,
                'compute_time': self.stage_compute_times[(group_id, 0)]
            }, priority=1)

    def schedule_event(self, time, event_type, data, priority=0):
        """安排新事件"""
        heapq.heappush(self.event_heap, Event(time, event_type, data, priority))

    def run_simulation(self):
        """运行仿真"""
        while self.event_heap:
            event = heapq.heappop(self.event_heap)
            self.current_time = event.time
            
            # 处理事件
            if event.event_type == 'start_forward':
                self.handle_start_forward(event)
            elif event.event_type == 'complete_forward':
                self.handle_complete_forward(event)
            elif event.event_type == 'start_backward':
                self.handle_start_backward(event)
            elif event.event_type == 'complete_backward':
                self.handle_complete_backward(event)
            elif event.event_type == 'start_transmission':
                self.handle_start_transmission(event)
            elif event.event_type == 'complete_transmission':
                self.handle_complete_transmission(event)
            elif event.event_type == 'start_ring_allreduce':
                self.handle_start_ring_allreduce(event)
            elif event.event_type == 'ring_scatter_reduce':
                self.handle_ring_scatter_reduce(event)
            elif event.event_type == 'ring_allgather':
                self.handle_ring_allgather(event)
            elif event.event_type == 'complete_ring_allreduce':
                self.handle_complete_ring_allreduce(event)
        
        self.print_statistics()

    def handle_start_forward(self, event):
        """处理开始前向传播事件"""
        data = event.data
        micro_batch_id = data['micro_batch_id']
        group_id = data['group_id']
        stage_id = data['stage_id']
        node_id = data['node_id']
        compute_time = data['compute_time']
        
        key = (group_id, micro_batch_id)
        
        # 更新微批次状态
        if self.micro_batch_status[key]["start_time"] is None and stage_id == 0:
            self.micro_batch_status[key]["start_time"] = self.current_time
        
        self.micro_batch_status[key]["current_stage"] = stage_id
        
        print(f"[{self.current_time:.3f}s] 组 {group_id} 微批次 {micro_batch_id} 开始前向传播 阶段 {stage_id} 节点 {node_id}")
        
        # 调度计算完成事件
        self.schedule_event(self.current_time + compute_time, 'complete_forward', {
            'micro_batch_id': micro_batch_id,
            'group_id': group_id,
            'stage_id': stage_id,
            'node_id': node_id,
            'compute_time': compute_time
        })

    def handle_complete_forward(self, event):
        """处理完成前向传播事件"""
        data = event.data
        micro_batch_id = data['micro_batch_id']
        group_id = data['group_id']
        stage_id = data['stage_id']
        node_id = data['node_id']
        
        key = (group_id, micro_batch_id)
        
        # 更新节点状态
        node = self.nodes[node_id]
        node.busy = False
        
        print(f"[{self.current_time:.3f}s] 组 {group_id} 微批次 {micro_batch_id} 完成前向传播 阶段 {stage_id} 节点 {node_id}")
        
        # 更新微批次状态
        self.micro_batch_status[key]["forward_complete"].add(stage_id)
        
        # 检查是否有排队任务
        if node.task_queue:
            next_task_type, next_task_data = node.task_queue.pop(0)
            if next_task_type == 'start_forward':
                self.handle_start_forward(Event(self.current_time, 'start_forward', next_task_data))
            elif next_task_type == 'start_backward':
                self.handle_start_backward(Event(self.current_time, 'start_backward', next_task_data))
        
        # 流水线逻辑：如果不是最后一个阶段，将数据传递到下一个阶段
        num_stages = len(self.group_stages[group_id])
        if stage_id < num_stages - 1:
            # 调度数据传输到下一个阶段
            next_stage = stage_id + 1
            next_node = self.group_stages[group_id][next_stage]
            
            self.schedule_event(self.current_time, 'start_transmission', {
                'micro_batch_id': micro_batch_id,
                'src_node': node_id,
                'dest_node': next_node,
                'group_id': group_id,
                'src_stage': stage_id,
                'dest_stage': next_stage,
                'size': 1.0,  # 假设前向传播数据大小为1MB
                'direction': 'forward'
            })
        else:
            # 如果是最后一个阶段，开始反向传播
            self.schedule_event(self.current_time, 'start_backward', {
                'micro_batch_id': micro_batch_id,
                'group_id': group_id,
                'stage_id': stage_id,
                'node_id': node_id,
                'compute_time': self.stage_compute_times[(group_id, stage_id)]
            }, priority=2)
        
        # 流水线效率：如果当前阶段完成了前向传播，且是第一个阶段，安排下一个微批次
        if stage_id == 0 and micro_batch_id < self.micro_batch_count - 1:
            next_micro_batch = micro_batch_id + 1
            next_key = (group_id, next_micro_batch)
            if self.micro_batch_status[next_key]["current_stage"] == -1:
                self.schedule_event(self.current_time, 'start_forward', {
                    'micro_batch_id': next_micro_batch,
                    'group_id': group_id,
                    'stage_id': 0,
                    'node_id': node_id,
                    'compute_time': self.stage_compute_times[(group_id, 0)]
                }, priority=3)

    def handle_start_backward(self, event):
        """处理开始反向传播事件"""
        data = event.data
        micro_batch_id = data['micro_batch_id']
        group_id = data['group_id']
        stage_id = data['stage_id']
        node_id = data['node_id']
        compute_time = data['compute_time']
        
        print(f"[{self.current_time:.3f}s] 组 {group_id} 微批次 {micro_batch_id} 开始反向传播 阶段 {stage_id} 节点 {node_id}")
        
        # 调度反向传播完成事件
        self.schedule_event(self.current_time + compute_time, 'complete_backward', {
            'micro_batch_id': micro_batch_id,
            'group_id': group_id,
            'stage_id': stage_id,
            'node_id': node_id,
            'compute_time': compute_time
        })

    def handle_complete_backward(self, event):
        """处理完成反向传播事件"""
        data = event.data
        micro_batch_id = data['micro_batch_id']
        group_id = data['group_id']
        stage_id = data['stage_id']
        node_id = data['node_id']
        
        key = (group_id, micro_batch_id)
        
        # 更新节点状态
        node = self.nodes[node_id]
        node.busy = False
        
        print(f"[{self.current_time:.3f}s] 组 {group_id} 微批次 {micro_batch_id} 完成反向传播 阶段 {stage_id} 节点 {node_id}")
        
        # 更新微批次状态
        self.micro_batch_status[key]["backward_complete"].add(stage_id)
        
        # 检查是否有排队任务
        if node.task_queue:
            next_task_type, next_task_data = node.task_queue.pop(0)
            if next_task_type == 'start_forward':
                self.handle_start_forward(Event(self.current_time, 'start_forward', next_task_data))
            elif next_task_type == 'start_backward':
                self.handle_start_backward(Event(self.current_time, 'start_backward', next_task_data))
        
        # 流水线逻辑：如果不是第一个阶段，将梯度传递到上一个阶段
        if stage_id > 0:
            # 调度梯度传输到上一个阶段
            prev_stage = stage_id - 1
            prev_node = self.group_stages[group_id][prev_stage]
            
            self.schedule_event(self.current_time, 'start_transmission', {
                'micro_batch_id': micro_batch_id,
                'src_node': node_id,
                'dest_node': prev_node,
                'group_id': group_id,
                'src_stage': stage_id,
                'dest_stage': prev_stage,
                'size': 0.5,  # 假设反向传播梯度大小为0.5MB
                'direction': 'backward'
            })
        
        # 检查该组的所有微批次是否都完成了所有阶段的反向传播
        all_complete = True
        num_stages = len(self.group_stages[group_id])
        
        for mb_id in range(self.micro_batch_count):
            mb_key = (group_id, mb_id)
            if len(self.micro_batch_status[mb_key]["backward_complete"]) < num_stages:
                all_complete = False
                break
        
        # 如果所有微批次都完成了反向传播，开始Ring-AllReduce
        if all_complete and not self.ring_allreduce_status[group_id]["scatter_reduce_complete"]:
            print(f"✅ [{self.current_time:.3f}s] 组 {group_id} 所有微批次完成! 开始Ring-AllReduce")
            
            # 记录组内训练完成时间
            completion_time = self.current_time - self.micro_batch_status[(group_id, 0)]['start_time']
            self.batch_completion_times.append(completion_time)
            
            # 开始Ring-AllReduce
            self.schedule_event(self.current_time, 'start_ring_allreduce', {
                'group_id': group_id
            })

    def handle_start_ring_allreduce(self, event):
        """处理开始Ring-AllReduce事件"""
        data = event.data
        group_id = data['group_id']
        
        print(f"[{self.current_time:.3f}s] 组 {group_id} 开始Ring-AllReduce")
        
        # 获取组内所有节点
        nodes = list(self.group_stages[group_id].values())
        num_nodes = len(nodes)
        
        # 初始化每个节点的梯度分块
        for i, node_id in enumerate(nodes):
            node = self.nodes[node_id]
            node.gradient_chunks = {chunk_id: f"grad_{node_id}_{chunk_id}" 
                                   for chunk_id in range(self.num_gradient_chunks)}
            
            # 为每个节点安排第一次scatter-reduce
            next_node_idx = (i + 1) % num_nodes
            next_node_id = nodes[next_node_idx]
            chunk_to_send = i % self.num_gradient_chunks
            
            self.schedule_event(self.current_time, 'ring_scatter_reduce', {
                'group_id': group_id,
                'src_node': node_id,
                'dest_node': next_node_id,
                'chunk_id': chunk_to_send,
                'iteration': 0
            })

    def handle_ring_scatter_reduce(self, event):
        """处理Ring-AllReduce的Scatter-Reduce阶段"""
        data = event.data
        group_id = data['group_id']
        src_node_id = data['src_node']
        dest_node_id = data['dest_node']
        chunk_id = data['chunk_id']
        iteration = data['iteration']
        
        # 获取组内所有节点
        nodes = list(self.group_stages[group_id].values())
        num_nodes = len(nodes)
        
        # 传输梯度分块
        self.schedule_event(self.current_time, 'start_transmission', {
            'micro_batch_id': -1,  # 特殊值表示这是Ring-AllReduce传输
            'src_node': src_node_id,
            'dest_node': dest_node_id,
            'group_id': group_id,
            'size': 0.5 / self.num_gradient_chunks,  # 梯度分块大小
            'direction': 'ring_reduce',
            'chunk_id': chunk_id,
            'iteration': iteration
        })
        
        print(f"[{self.current_time:.3f}s] Ring-Reduce: 节点 {src_node_id} 发送分块 {chunk_id} 到节点 {dest_node_id} (迭代 {iteration})")
        
        # 如果已完成所有迭代，开始AllGather阶段
        if iteration == num_nodes - 2:  # 完成n-1次迭代
            if not self.ring_allreduce_status[group_id]["scatter_reduce_complete"]:
                self.ring_allreduce_status[group_id]["scatter_reduce_complete"] = True
                
                # 开始AllGather阶段
                for i, node_id in enumerate(nodes):
                    next_node_idx = (i + 1) % num_nodes
                    next_node_id = nodes[next_node_idx]
                    chunk_to_send = (i - 1) % self.num_gradient_chunks
                    if chunk_to_send < 0:
                        chunk_to_send += self.num_gradient_chunks
                    
                    self.schedule_event(self.current_time, 'ring_allgather', {
                        'group_id': group_id,
                        'src_node': node_id,
                        'dest_node': next_node_id,
                        'chunk_id': chunk_to_send,
                        'iteration': 0
                    })

    def handle_ring_allgather(self, event):
        """处理Ring-AllReduce的AllGather阶段"""
        data = event.data
        group_id = data['group_id']
        src_node_id = data['src_node']
        dest_node_id = data['dest_node']
        chunk_id = data['chunk_id']
        iteration = data['iteration']
        
        # 获取组内所有节点
        nodes = list(self.group_stages[group_id].values())
        num_nodes = len(nodes)
        
        # 传输梯度分块
        self.schedule_event(self.current_time, 'start_transmission', {
            'micro_batch_id': -1,  # 特殊值表示这是Ring-AllReduce传输
            'src_node': src_node_id,
            'dest_node': dest_node_id,
            'group_id': group_id,
            'size': 0.5 / self.num_gradient_chunks,  # 梯度分块大小
            'direction': 'ring_gather',
            'chunk_id': chunk_id,
            'iteration': iteration
        })
        
        print(f"[{self.current_time:.3f}s] Ring-Gather: 节点 {src_node_id} 发送分块 {chunk_id} 到节点 {dest_node_id} (迭代 {iteration})")
        
        # 如果已完成所有迭代，完成Ring-AllReduce
        if iteration == num_nodes - 2:  # 完成n-1次迭代
            if not self.ring_allreduce_status[group_id]["allgather_complete"]:
                self.ring_allreduce_status[group_id]["allgather_complete"] = True
                
                # 完成Ring-AllReduce
                self.schedule_event(self.current_time, 'complete_ring_allreduce', {
                    'group_id': group_id
                })

    def handle_complete_ring_allreduce(self, event):
        """处理完成Ring-AllReduce事件"""
        data = event.data
        group_id = data['group_id']
        
        print(f"[{self.current_time:.3f}s] 组 {group_id} 完成Ring-AllReduce")
        
        # 记录完成时间
        completion_time = self.current_time - self.micro_batch_status[(group_id, 0)]['start_time']
        print(f"组 {group_id} 总用时: {completion_time:.3f}s")
        
        # 这里可以添加参数更新和下一轮训练的逻辑

    def handle_start_transmission(self, event):
        """处理开始传输事件"""
        data = event.data
        micro_batch_id = data['micro_batch_id']
        src_node = data['src_node']
        dest_node = data['dest_node']
        size = data['size']
        direction = data.get('direction', 'forward')
        group_id = data.get('group_id', -1)
        
        # 特殊处理Ring-AllReduce传输
        if direction in ['ring_reduce', 'ring_gather']:
            chunk_id = data.get('chunk_id', 0)
            iteration = data.get('iteration', 0)
        
        # 计算路由
        next_hop = self.routing_tables[src_node][dest_node]
        if next_hop is None:
            print(f"⚠️ [{self.current_time:.3f}s] 传输 {src_node}->{dest_node} 路由失败")
            return
        
        # 检查链路是否存在
        link_key = (src_node, next_hop)
        if link_key not in self.links:
            print(f"⚠️ [{self.current_time:.3f}s] 链路 {src_node}->{next_hop} 不存在")
            return
        
        link = self.links[link_key]
        
        # 创建数据包
        packet = Packet(src_node, dest_node, size, self.current_time, 
                        group_id=group_id, stage_id=0, 
                        micro_batch_id=micro_batch_id, packet_type=direction)
        
        # 对于Ring-AllReduce传输，添加额外信息
        if direction in ['ring_reduce', 'ring_gather']:
            packet.chunk_id = chunk_id
            packet.iteration = iteration
        
        if direction not in ['ring_reduce', 'ring_gather']:
            print(f"[{self.current_time:.3f}s] {direction} 传输启动: {src_node}→{next_hop} (目标 {dest_node}) {size}MB")
        
        # 如果链路空闲，立即开始传输
        if link.current_transmission is None:
            self.start_link_transmission(link, packet)
        else:
            link.queue.append(packet)

    def start_link_transmission(self, link, packet):
        """开始在链路上传输数据包"""
        # 计算传输时间 (考虑单位换算: MB * 8 / Mbps = 秒)
        transmission_time = packet.size * 8 / link.bandwidth
        end_time = self.current_time + transmission_time
        
        # 设置链路状态
        packet.start_time = self.current_time
        packet.end_time = end_time
        link.current_transmission = packet
        link.busy_until = end_time
        
        # 记录链路利用率
        self.link_utilization[(link.src, link.dest)].append((self.current_time, end_time))
    
        self.schedule_event(end_time, 'complete_transmission', {
            'link': (link.src, link.dest),
            'packet': packet
        })

    def handle_complete_transmission(self, event):
        """处理完成传输事件"""
        data = event.data
        link_key = data['link']
        packet = data['packet']
        
        # 更新链路状态
        link = self.links[link_key]
        link.current_transmission = None
        
        micro_batch_id = packet.micro_batch_id
        src_node = link_key[0]
        current_node = link_key[1]  # 当前数据包到达的节点
        dest_node = packet.final_dest
        direction = packet.packet_type
        group_id = packet.group_id
        
        if direction not in ['ring_reduce', 'ring_gather']:
            print(f"[{self.current_time:.3f}s] {direction} 传输完成: {src_node}→{current_node} ({packet.size}MB)")
        
        # 如果链路队列中有其他数据包，启动下一个传输
        if link.queue:
            next_packet = link.queue.pop(0)
            self.start_link_transmission(link, next_packet)
        
        # 检查数据包是否到达最终目的地
        if current_node == dest_node:
            # 处理不同类型的数据包
            if direction == 'forward':
                # 处理前向传播数据包
                dest_stage = self.node_to_stage[dest_node]
                self.handle_forward_arrival(packet, dest_node, dest_stage)
            elif direction == 'backward':
                # 处理反向传播数据包
                dest_stage = self.node_to_stage[dest_node]
                self.handle_backward_arrival(packet, dest_node, dest_stage)
            elif direction == 'ring_reduce':
                # 处理Ring-AllReduce的Scatter-Reduce阶段
                self.handle_ring_reduce_arrival(packet, dest_node)
            elif direction == 'ring_gather':
                # 处理Ring-AllReduce的AllGather阶段
                self.handle_ring_gather_arrival(packet, dest_node)
        else:
            # 数据包需要继续路由
            next_hop = self.routing_tables[current_node][dest_node]
            if next_hop is None:
                print(f"⚠️ [{self.current_time:.3f}s] 路由失败: {current_node}→{dest_node}")
                return
                
            # 创建到下一跳的传输事件
            self.schedule_event(self.current_time, 'start_transmission', {
                'micro_batch_id': micro_batch_id,
                'src_node': current_node,
                'dest_node': dest_node,
                'group_id': group_id,
                'size': packet.size,
                'direction': direction,
                'chunk_id': getattr(packet, 'chunk_id', 0) if direction in ['ring_reduce', 'ring_gather'] else 0,
                'iteration': getattr(packet, 'iteration', 0) if direction in ['ring_reduce', 'ring_gather'] else 0
            })

    def handle_forward_arrival(self, packet, node_id, stage_id):
        """处理前向传播数据包到达事件"""
        micro_batch_id = packet.micro_batch_id
        group_id = packet.group_id
        
        print(f"[{self.current_time:.3f}s] 组 {group_id} 微批次 {micro_batch_id} 前向数据到达 阶段 {stage_id} 节点 {node_id}")
        
        # 开始当前阶段的前向传播
        self.schedule_event(self.current_time, 'start_forward', {
            'micro_batch_id': micro_batch_id,
            'group_id': group_id,
            'stage_id': stage_id,
            'node_id': node_id,
            'compute_time': self.stage_compute_times[(group_id, stage_id)]
        })

    def handle_backward_arrival(self, packet, node_id, stage_id):
        """处理反向传播数据包到达事件"""
        micro_batch_id = packet.micro_batch_id
        group_id = packet.group_id
        
        print(f"[{self.current_time:.3f}s] 组 {group_id} 微批次 {micro_batch_id} 反向梯度到达 阶段 {stage_id} 节点 {node_id}")
        
        # 开始当前阶段的反向传播
        self.schedule_event(self.current_time, 'start_backward', {
            'micro_batch_id': micro_batch_id,
            'group_id': group_id,
            'stage_id': stage_id,
            'node_id': node_id,
            'compute_time': self.stage_compute_times[(group_id, stage_id)]
        })

    def handle_ring_reduce_arrival(self, packet, node_id):
        """处理Ring-AllReduce的Scatter-Reduce数据包到达事件"""
        group_id = packet.group_id
        chunk_id = packet.chunk_id
        iteration = packet.iteration
        
        # 获取组内所有节点
        nodes = list(self.group_stages[group_id].values())
        num_nodes = len(nodes)
        node_idx = nodes.index(node_id)
        
        # 记录接收到的梯度分块
        self.ring_allreduce_status[group_id]["chunks_received"][node_id].add(chunk_id)
        
        # 模拟reduce计算时间
        reduce_time = 0.01  # 假设reduce操作需要0.01秒
        
        # 如果不是最后一次迭代，继续scatter-reduce
        if iteration < num_nodes - 2:
            next_node_idx = (node_idx + 1) % num_nodes
            next_node_id = nodes[next_node_idx]
            
            self.schedule_event(self.current_time + reduce_time, 'ring_scatter_reduce', {
                'group_id': group_id,
                'src_node': node_id,
                'dest_node': next_node_id,
                'chunk_id': chunk_id,
                'iteration': iteration + 1
            })

    def handle_ring_gather_arrival(self, packet, node_id):
        """处理Ring-AllReduce的AllGather数据包到达事件"""
        group_id = packet.group_id
        chunk_id = packet.chunk_id
        iteration = packet.iteration
        
        # 获取组内所有节点
        nodes = list(self.group_stages[group_id].values())
        num_nodes = len(nodes)
        node_idx = nodes.index(node_id)
        
        # 记录接收到的梯度分块
        self.ring_allreduce_status[group_id]["chunks_processed"][node_id].add(chunk_id)
        
        # 如果不是最后一次迭代，继续allgather
        if iteration < num_nodes - 2:
            next_node_idx = (node_idx + 1) % num_nodes
            next_node_id = nodes[next_node_idx]
            
            self.schedule_event(self.current_time, 'ring_allgather', {
                'group_id': group_id,
                'src_node': node_id,
                'dest_node': next_node_id,
                'chunk_id': chunk_id,
                'iteration': iteration + 1
            })
    
    def print_statistics(self):
        """打印统计信息"""
        print("\n" + "="*60)
        print("仿真完成统计")
        print("="*60)
        
        if self.batch_completion_times:
            avg_completion_time = sum(self.batch_completion_times) / len(self.batch_completion_times)
            max_completion_time = max(self.batch_completion_times)
            min_completion_time = min(self.batch_completion_times)
            print(f"组完成时间统计:")
            print(f"  平均: {avg_completion_time:.3f}s")
            print(f"  最大: {max_completion_time:.3f}s")
            print(f"  最小: {min_completion_time:.3f}s")
        
        # 计算链路利用率
        print("\n链路利用率:")
        for link_key, usage_periods in self.link_utilization.items():
            if not usage_periods:
                continue
            
            total_busy_time = sum(end - start for start, end in usage_periods)
            utilization = total_busy_time / self.current_time if self.current_time > 0 else 0
            print(f"  链路 {link_key[0]}->{link_key[1]}: {utilization*100:.2f}%")
        
        print("\n总仿真时间: {:.3f} 秒".format(self.current_time))
        print("="*60)

def main():
    # 设置日志输出
    original_stdout = sys.stdout
    if not os.path.exists('logs'):
        os.makedirs('logs')
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    log_file = open(f'logs/simulation_{timestamp}.txt', 'w')
    sys.stdout = Tee(original_stdout, log_file)
    
    try:
        # 解析命令行参数，如果有的话
        parallel_mode = "hybrid"  # 默认为混合并行
        if len(sys.argv) > 1:
            parallel_mode = sys.argv[1]
        
        # 创建仿真器
        simulator = Simulator(parallel_mode=parallel_mode)
        
        # 读取网络拓扑
        topology_file = "fattree.txt"
        if len(sys.argv) > 2:
            topology_file = sys.argv[2]
        
        num_nodes = simulator.read_adjacency_matrix(topology_file)
        
        # 读取训练配置
        config_file = "tliuliang.txt"
        if len(sys.argv) > 3:
            config_file = sys.argv[3]
        
        packet_size, compute_times, micro_batch_count, groups, node_to_group, node_to_stage = simulator.read_training_config(config_file, num_nodes)
        
        # 设置仿真初始事件
        simulator.schedule_initial_events(packet_size, compute_times, micro_batch_count, groups, node_to_group, node_to_stage)
        
        # 运行仿真
        print(f"开始仿真 - 并行模式: {parallel_mode}")
        simulator.run_simulation()
        
    except Exception as e:
        print(f"仿真过程中出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # 恢复标准输出并关闭文件
        sys.stdout = original_stdout
        log_file.close()

if __name__ == "__main__":
    main()

        
        
