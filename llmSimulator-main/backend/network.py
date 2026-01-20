import heapq
import random
from collections import defaultdict

class Link:
    """网络链路，用于模拟数据传输"""
    def __init__(self, src, dest, bandwidth, latency=0.0, jitter=0.0, packet_loss=0.0):
        self.src = src
        self.dest = dest
        self.bandwidth = bandwidth  # Gbps
        self.base_latency = latency  # 基础延迟(ms)
        self.jitter = jitter  # 抖动范围(ms)
        self.packet_loss = packet_loss  # 丢包率(0-1)
        self.queue = []
        # 修改：使用列表存储当前正在传输的多个数据包
        self.current_transmissions = []  # 当前正在传输的数据包列表
        self.busy_until = 0  # 链路空闲时间点
        self.active_flows = 0  # 当前活跃的流数量
        self.packet_loss_count = 0  # 丢包计数
        self.congested = False  # 链路是否处于拥塞状态
        # 新增：最大并行传输数量，可以根据需要调整
        self.max_concurrent_transmissions = 10  # 默认允许10个并行传输
        # 新增：当前已分配的带宽
        self.allocated_bandwidth = 0  # 已分配的带宽(Gbps)

    def get_effective_bandwidth(self, packet, congestion_model="fair_share"):
        """获取考虑拥塞后的有效带宽"""
        # 计算剩余可用带宽
        available_bandwidth = self.bandwidth - self.allocated_bandwidth
        
        if available_bandwidth <= 0 or len(self.current_transmissions) >= self.max_concurrent_transmissions:
            # 如果没有可用带宽或达到最大并行传输数，则使用最小带宽
            return min(0.1, self.bandwidth / 20)  # 保证至少有一些带宽
        
        # 根据拥塞模型分配带宽
        if congestion_model == "fair_share":
            # 带宽平均分配给所有活跃流
            total_flows = self.active_flows + 1  # 加上新的流
            return min(available_bandwidth, self.bandwidth / total_flows)
        
        elif congestion_model == "priority":
            # 优先级模型：优先流获取更多带宽
            if packet and packet.packet_type == "parameter":
                # 参数传输优先，获取更多带宽
                return min(available_bandwidth, self.bandwidth * 0.8 / (sum(1 for p in self.current_transmissions if p.packet_type == "parameter") + 1))
            else:
                # 其他类型流量获取较少带宽
                return min(available_bandwidth, self.bandwidth * 0.2 / (sum(1 for p in self.current_transmissions if p.packet_type != "parameter") + 1))
        
        elif congestion_model == "proportional":
            # 按比例分配带宽
            return min(available_bandwidth, available_bandwidth * 0.8)  # 新流可以获取80%的可用带宽
        
        else:  # 默认使用公平分享
            return min(available_bandwidth, self.bandwidth / (len(self.current_transmissions) + 1))
    
    def get_current_latency(self):
        """计算当前延迟，包括基础延迟和随机抖动"""
        if self.jitter <= 0:
            return self.base_latency / 1000.0  # 转换为秒
        
        # 在基础延迟的基础上添加随机抖动
        jitter_value = random.uniform(-self.jitter, self.jitter) / 1000.0  # 转换为秒
        return max(0.001, (self.base_latency / 1000.0) + jitter_value)  # 确保延迟至少为1ms
    
    def will_packet_drop(self):
        """根据丢包率决定数据包是否丢失"""
        if random.random() < self.packet_loss:
            self.packet_loss_count += 1
            return True
        return False
    
    def update_congestion_status(self, queue_threshold=0.8):
        """更新链路的拥塞状态"""
        # 如果队列长度超过阈值，标记为拥塞状态
        if len(self.queue) > queue_threshold * 100:  # 假设最大队列长度为100
            self.congested = True
            return True
        # 如果带宽利用率超过阈值，也标记为拥塞状态
        if self.allocated_bandwidth > self.bandwidth * 0.9:
            self.congested = True
            return True
        self.congested = False
        return False

class Packet:
    """网络数据包"""
    def __init__(self, src, final_dest, size, gen_time, group_id, stage_id, micro_batch_id, packet_type, batch_id=0):
        self.src = src
        self.final_dest = final_dest
        self.size = size  # MB
        self.gen_time = gen_time
        self.start_time = None
        self.end_time = None
        self.group_id = group_id
        self.stage_id = stage_id
        self.micro_batch_id = micro_batch_id
        self.batch_id = batch_id  # 添加批次ID
        self.packet_type = packet_type  # "forward", "backward", "gradient", "parameter"
        self.retransmission_count = 0  # 重传次数
        # 用于Ring-AllReduce
        self.chunk_id = 0
        self.iteration = 0
        self.is_background = False  # 是否为背景流量
        # 新增：记录分配的带宽
        self.allocated_bandwidth = 0  # Gbps

class NetworkManager:
    """网络管理器，处理网络拓扑和数据传输"""
    def __init__(self, simulator, network_config=None):
        self.simulator = simulator  # 仿真器引用
        self.links = {}  # 网络链路
        self.routing_tables = {}  # 路由表
        self.link_utilization = {}  # 链路利用率统计
        self.topology = None  # 网络拓扑
        self.nodes = []  # 节点列表
        
        # 网络配置参数
        self.network_config = network_config or {}
        self.congestion_model = self.network_config.get("congestion_model", "fair_share")
        self.max_retransmissions = self.network_config.get("max_retransmissions", 3)
        self.retransmission_timeout = self.network_config.get("retransmission_timeout", 100) / 1000.0  # 毫秒转秒
        self.queue_size_limit = self.network_config.get("queue_size_limit", 100)  # 队列长度限制
        
        # 路由算法配置
        self.routing_algorithm = self.network_config.get("routing_algorithm", "dijkstra")
        self.ecmp_max_paths = self.network_config.get("ecmp_max_paths", 8)  # 最大等价路径数
        self.ecmp_strategy = self.network_config.get("ecmp_strategy", "hash_based")  # ECMP策略
        
        # 统计数据
        self.retransmission_count = 0  # 重传计数
        self.congestion_events = 0  # 拥塞事件计数
        self.background_packets_sent = 0  # 背景流量包数
        self.background_bytes_sent = 0  # 背景流量字节数
        self.packet_events = []  # 数据包事件记录
        self.total_packets_sent = 0  # 总发送包数
        self.total_bytes_sent = 0  # 总发送字节数
        
        # 路由统计
        self.path_lengths = []  # 记录所有路径长度
        self.path_counts = {}  # 记录每对节点之间使用的路径数量
        self.routing_calculations = 0  # 路由计算次数
        self.routing_performance_samples = []  # 路由性能采样
        
        # ECMP相关
        self.path_weights = {}  # 存储路径权重
        self.ecmp_hash_seed = random.randint(1, 10000)  # ECMP哈希种子
        
        # 路径缓存
        self.path_cache = {}  # 缓存计算过的路径

        
    def read_topology_file(self, filename):
        """读取拓扑文件，构建网络拓扑"""
        import yaml
        try:
            with open(filename, 'r') as f:
                topology_data = yaml.safe_load(f)
            
            self.topology = topology_data
            self.nodes = topology_data.get("nodes", [])
            links_data = topology_data.get("links", [])
            
            # 获取网络参数
            default_bandwidth = self.network_config.get("default_bandwidth", 10)  # Gbps
            default_latency = self.network_config.get("default_latency", 0.1)  # ms
            default_jitter = self.network_config.get("default_jitter", 0.01)  # ms
            default_packet_loss = self.network_config.get("default_packet_loss", 0.0001)  # 0-1
            
            # 创建图结构
            num_nodes = len(self.nodes)
            graph = {node_id: [] for node_id in range(num_nodes)}
            
            # 创建链路
            for link in links_data:
                src = link.get("source")
                dest = link.get("target")
                bandwidth = link.get("bandwidth", default_bandwidth)
                latency = link.get("latency", default_latency)
                jitter = link.get("jitter", default_jitter)
                packet_loss = link.get("packet_loss", default_packet_loss)
                
                # 添加到图中
                graph[src].append(dest)
                
                # 创建链路对象
                self.links[(src, dest)] = Link(src, dest, bandwidth, latency, jitter, packet_loss)
                self.link_utilization[(src, dest)] = []
                
                # 如果是双向链路，添加反向链路
                if link.get("bidirectional", True):
                    graph[dest].append(src)
                    self.links[(dest, src)] = Link(dest, src, bandwidth, latency, jitter, packet_loss)
                    self.link_utilization[(dest, src)] = []
            
            # 计算路由表
            self._compute_routing_tables(graph, num_nodes)
            
            return num_nodes
        except Exception as e:
            print(f"错误：读取拓扑文件 {filename} 失败: {e}")
            raise

    def read_adjacency_matrix(self, filename):
        """读取邻接矩阵文件，构建网络拓扑"""
        try:
            with open(filename, 'r') as f:
                matrix = []
                for line in f:
                    row = list(map(float, line.strip().split()))
                    matrix.append(row)
            
            num_nodes = len(matrix)
            self.nodes = [{"id": i, "type": "node"} for i in range(num_nodes)]
            graph = {node: [] for node in range(num_nodes)}
            
            # 获取网络参数
            default_bandwidth = self.network_config.get("default_bandwidth", 10)  # Gbps
            default_latency = self.network_config.get("default_latency", 0.1)  # ms
            default_jitter = self.network_config.get("default_jitter", 0.01)  # ms
            default_packet_loss = self.network_config.get("default_packet_loss", 0.0001)  # 0-1
            
            # 读取特定链路的配置
            link_configs = self.network_config.get("links", {})
            
            for i in range(num_nodes):
                for j in range(num_nodes):
                    bandwidth = matrix[i][j]
                    if bandwidth > 0:
                        graph[i].append(j)
                        
                        # 检查是否有特定链路配置
                        link_key = f"{i}-{j}"
                        latency = link_configs.get(link_key, {}).get("latency", default_latency)
                        jitter = link_configs.get(link_key, {}).get("jitter", default_jitter)
                        packet_loss = link_configs.get(link_key, {}).get("packet_loss", default_packet_loss)
                        
                        self.links[(i, j)] = Link(i, j, bandwidth*1024, latency, jitter, packet_loss)
                        self.link_utilization[(i, j)] = []
            
            # 计算路由表
            self._compute_routing_tables(graph, num_nodes)
            
            return num_nodes
        except FileNotFoundError:
            print(f"错误：找不到拓扑文件 {filename}")
            raise
    
    def _compute_routing_tables(self, graph, num_nodes):
        """计算路由表"""
        self.routing_tables = {}
        
        # 根据选择的算法计算路由表
        if self.routing_algorithm == "ecmp":
            self._compute_ecmp_routing_tables(graph, num_nodes)
        else:  # 默认使用Dijkstra
            self._compute_dijkstra_routing_tables(graph, num_nodes)
        
        # 计算平均路径长度
        if self.path_lengths:
            self.average_path_length = sum(self.path_lengths) / len(self.path_lengths)
        else:
            self.average_path_length = 0
        
        # 计算路径多样性
        total_pairs = 0
        total_paths = 0
        for src in range(num_nodes):
            for dest in range(num_nodes):
                if src != dest:
                    total_pairs += 1
                    path_key = (src, dest)
                    if path_key in self.path_counts:
                        total_paths += self.path_counts[path_key]
        
        self.path_diversity = total_paths / total_pairs if total_pairs > 0 else 0

    def _compute_dijkstra_routing_tables(self, graph, num_nodes):
        """使用Dijkstra算法计算最短路径路由表"""
        for source in range(num_nodes):
            # 初始化距离和前驱节点
            dist = {node: float('infinity') for node in range(num_nodes)}
            prev = {node: None for node in range(num_nodes)}
            dist[source] = 0
            unvisited = list(range(num_nodes))
            
            while unvisited:
                # 找到距离最小的未访问节点
                current = min(unvisited, key=lambda node: dist[node])
                
                # 如果当前节点距离为无穷大，说明剩余节点不可达
                if dist[current] == float('infinity'):
                    break
                    
                unvisited.remove(current)
                
                # 更新邻居节点的距离
                for neighbor in graph[current]:
                    alt = dist[current] + 1  # 假设所有边权重为1
                    if alt < dist[neighbor]:
                        dist[neighbor] = alt
                        prev[neighbor] = current
            
            # 构建路由表
            for dest in range(num_nodes):
                if source != dest and prev[dest] is not None:
                    # 回溯构建路径
                    path = []
                    current = dest
                    while current != source:
                        path.append(current)
                        current = prev[current]
                    path.reverse()
                    
                    # 记录路径长度
                    self.path_lengths.append(len(path))
                    
                    # 设置路由表
                    if source not in self.routing_tables:
                        self.routing_tables[source] = {}
                    self.routing_tables[source][dest] = path[0] if path else None
                    
                    # 更新路径计数
                    path_key = (source, dest)
                    if path_key not in self.path_counts:
                        self.path_counts[path_key] = 1
                    
            self.routing_calculations += 1

    def _compute_ecmp_routing_tables(self, graph, num_nodes):
        """使用ECMP算法计算等价多路径路由表"""
        for source in range(num_nodes):
            # 初始化距离和前驱节点集合
            dist = {node: float('infinity') for node in range(num_nodes)}
            prev = {node: [] for node in range(num_nodes)}
            dist[source] = 0
            
            # 使用优先队列进行BFS
            queue = [(0, source)]
            
            while queue:
                current_dist, current = heapq.heappop(queue)
                
                # 如果找到了更短的路径，跳过
                if current_dist > dist[current]:
                    continue
                    
                # 更新邻居节点的距离
                for neighbor in graph[current]:
                    weight = 1  # 假设所有边权重为1
                    alt = dist[current] + weight
                    
                    # 如果找到更短的路径
                    if alt < dist[neighbor]:
                        dist[neighbor] = alt
                        prev[neighbor] = [current]  # 重置前驱节点列表
                        heapq.heappush(queue, (alt, neighbor))
                    # 如果找到等价路径
                    elif alt == dist[neighbor]:
                        prev[neighbor].append(current)  # 添加到前驱节点列表
            
            # 构建ECMP路由表
            for dest in range(num_nodes):
                if source != dest and prev[dest]:
                    # 收集所有可能的下一跳
                    next_hops = set()
                    self._collect_next_hops(source, dest, prev, next_hops)
                    
                    # 限制等价路径数量
                    next_hops = list(next_hops)[:self.ecmp_max_paths]
                    
                    # 设置路由表
                    if source not in self.routing_tables:
                        self.routing_tables[source] = {}
                    self.routing_tables[source][dest] = next_hops
                    
                    # 记录路径长度和数量
                    path_length = dist[dest]
                    self.path_lengths.append(path_length)
                    
                    # 更新路径计数
                    path_key = (source, dest)
                    self.path_counts[path_key] = len(next_hops)
                    
            self.routing_calculations += 1

    def _collect_next_hops(self, source, current, prev, next_hops):
        """递归收集所有可能的下一跳节点"""
        if current == source:
            return
            
        for p in prev[current]:
            if p == source:
                next_hops.add(current)
            else:
                self._collect_next_hops(source, p, prev, next_hops)

    def _find_next_hops(self, current, start_node, predecessors, next_hops, visited):
        """递归查找所有可能的下一跳"""
        if current in visited:
            return
        
        visited.add(current)
        
        # 如果找到起点的直接邻居，添加为下一跳
        if start_node in predecessors[current]:
            next_hops.add(current)
            return
        
        # 递归查找所有前驱
        for pred in predecessors[current]:
            if pred == start_node:
                next_hops.add(current)
            else:
                self._find_next_hops(pred, start_node, predecessors, next_hops, visited.copy())

    def _calculate_path_weights(self, src_node, dest_node, next_hops):
        """计算到目标节点的各路径权重（用于加权ECMP）"""
        weights = {}
        total_bandwidth = 0
        
        # 基于链路带宽计算权重
        for next_hop in next_hops:
            link = self.links.get((src_node, next_hop))
            if link:
                bandwidth = link.bandwidth
                total_bandwidth += bandwidth
                weights[next_hop] = bandwidth
        
        # 归一化权重
        if total_bandwidth > 0:
            for next_hop in weights:
                weights[next_hop] /= total_bandwidth
        else:
            # 如果无法获取带宽信息，使用均等权重
            for next_hop in next_hops:
                weights[next_hop] = 1.0 / len(next_hops)
        
        return weights

    def _select_ecmp_path(self, src_node, dest_node, micro_batch_id, direction, batch_id):
        """ECMP路径选择算法"""
        next_hops = self.routing_tables[src_node][dest_node]
        if not next_hops:
            return None
            
        if len(next_hops) == 1:
            return next_hops[0]
        
        # 根据ECMP策略选择路径
        if self.ecmp_strategy == "round_robin":
            # 简单轮询
            index = (micro_batch_id + batch_id) % len(next_hops)
            return next_hops[index]
        
        elif self.ecmp_strategy == "weighted":
            # 加权选择
            weights = self.path_weights[src_node].get(dest_node, {})
            if not weights:
                # 如果没有权重信息，使用均等权重
                weights = {hop: 1.0/len(next_hops) for hop in next_hops}
            
            # 基于权重随机选择
            r = random.random()
            cumulative = 0
            for hop, weight in weights.items():
                cumulative += weight
                if r <= cumulative:
                    return hop
            return next_hops[0]  # 默认返回第一个
        
        elif self.ecmp_strategy == "least_congested":
            # 选择最不拥塞的路径
            min_queue = float('infinity')
            best_hop = next_hops[0]
            
            for hop in next_hops:
                link = self.links.get((src_node, hop))
                if link and len(link.queue) < min_queue:
                    min_queue = len(link.queue)
                    best_hop = hop
            
            return best_hop
        
        else:  # hash_based (默认)
            # 基于流哈希的ECMP
            # 使用5元组哈希（这里简化为源、目标、微批次ID、方向和批次ID）
            hash_key = hash(f"{src_node}_{dest_node}_{micro_batch_id}_{direction}_{batch_id}")
            index = hash_key % len(next_hops)
            return next_hops[index]

    def get_next_hop(self, src, dest, packet=None):
        """根据路由表获取下一跳节点"""
        if src == dest:
            return None
            
        if src not in self.routing_tables or dest not in self.routing_tables[src]:
            return None
            
        next_hop = self.routing_tables[src][dest]
        
        # 如果是ECMP，根据策略选择路径
        if self.routing_algorithm == "ecmp":
            if isinstance(next_hop, list) and len(next_hop) > 1:
                if packet:
                    return self._select_ecmp_path(src, dest, packet.micro_batch_id, packet.packet_type, packet.batch_id)
                else:
                    return next_hop[0]  # 默认返回第一个
            return next_hop[0]
        
        return next_hop

    def start_transmission(self, current_time, micro_batch_id, src_node, dest_node, size, direction, group_id=-1, chunk_id=0, iteration=0, is_background=False, batch_id=0):
        """开始数据传输"""
        # 计算路由
        if dest_node not in self.routing_tables.get(src_node, {}):
            print(f"⚠️ [{current_time:.3f}s] 传输 {src_node}->{dest_node} 路由失败，目标节点不存在")
            return False
            
        next_hop = self.get_next_hop(src_node, dest_node)
        print(src_node,next_hop)
        
        # 检查链路是否存在
        link_key = (src_node, next_hop)
        if link_key not in self.links:
            print(f"⚠️ [{current_time:.3f}s] 链路 {src_node}->{next_hop} 不存在")
            return False
        
        link = self.links[link_key]
        
        # 更新统计信息
        self.total_packets_sent += 1
        self.total_bytes_sent += size
        
        if is_background:
            self.background_packets_sent += 1
            self.background_bytes_sent += size
        
        # 创建数据包
        packet = Packet(src_node, dest_node, size, current_time, 
                        group_id=group_id, stage_id=0, 
                        micro_batch_id=micro_batch_id, packet_type=direction, batch_id=batch_id)
        packet.is_background = is_background
        
        # 对于Ring-AllReduce传输，添加额外信息
        if direction in ['ring_reduce', 'ring_gather']:
            packet.chunk_id = chunk_id
            packet.iteration = iteration
        
        # 模拟丢包
        if link.will_packet_drop():
            if not is_background and direction not in ['ring_reduce', 'ring_gather']:
                print(f"⚠️ [{current_time:.3f}s] {direction} 传输丢包: {src_node}→{next_hop} (目标 {dest_node}) {size}MB")
            
            # 记录丢包事件
            self.packet_events.append({
                'time': current_time,
                'type': 'packet_loss',
                'src': src_node,
                'dest': dest_node,
                'next_hop': next_hop,
                'size': size,
                'direction': direction,
                'group_id': group_id,
                'micro_batch_id': micro_batch_id,
                'batch_id': batch_id,
                'is_background': is_background
            })
            
            # 安排重传
            if not is_background and packet.retransmission_count < self.max_retransmissions:
                packet.retransmission_count += 1
                self.retransmission_count += 1
                
                self.simulator.schedule_event(
                    current_time + self.retransmission_timeout,
                    'start_transmission',
                    {
                        'micro_batch_id': micro_batch_id,
                        'batch_id': batch_id,
                        'src_node': src_node,
                        'dest_node': dest_node,
                        'group_id': group_id,
                        'size': size,
                        'direction': direction,
                        'chunk_id': chunk_id,
                        'iteration': iteration,
                        'retransmission': True
                    }
                )
                return True
            elif not is_background:
                print(f"❌ [{current_time:.3f}s] {direction} 传输失败: {src_node}→{dest_node} 超过最大重传次数")
                return False
            else:
                # 背景流量丢包不重传
                return False
        
        # 记录传输开始事件
        if not is_background and direction not in ['ring_reduce', 'ring_gather']:
            print(f"[{current_time:.3f}s] {direction} 传输启动: {src_node}→{next_hop} (目标 {dest_node}) {size}MB")
        
        self.packet_events.append({
            'time': current_time,
            'type': 'transmission_start',
            'src': src_node,
            'dest': dest_node,
            'next_hop': next_hop,
            'size': size,
            'direction': direction,
            'group_id': group_id,
            'micro_batch_id': micro_batch_id,
            'batch_id': batch_id,
            'is_background': is_background
        })
        
        # 检查队列长度限制
                # 检查队列长度限制
        if len(link.queue) >= self.queue_size_limit and len(link.current_transmissions) >= link.max_concurrent_transmissions:
            if not is_background:
                print(f"⚠️ [{current_time:.3f}s] 链路 {src_node}→{next_hop} 队列已满，数据包被丢弃")
            
            # 记录拥塞丢包事件
            self.congestion_events += 1
            self.packet_events.append({
                'time': current_time,
                'type': 'congestion_drop',
                'src': src_node,
                'dest': dest_node,
                'next_hop': next_hop,
                'size': size,
                'direction': direction,
                'group_id': group_id,
                'micro_batch_id': micro_batch_id,
                'batch_id': batch_id,
                'is_background': is_background,
                'queue_length': len(link.queue)
            })
            
            # 安排重传
            if not is_background and packet.retransmission_count < self.max_retransmissions:
                packet.retransmission_count += 1
                self.retransmission_count += 1
                
                self.simulator.schedule_event(
                    current_time + self.retransmission_timeout,
                    'start_transmission',
                    {
                        'micro_batch_id': micro_batch_id,
                        'batch_id': batch_id,
                        'src_node': src_node,
                        'dest_node': dest_node,
                        'group_id': group_id,
                        'size': size,
                        'direction': direction,
                        'chunk_id': chunk_id,
                        'iteration': iteration,
                        'retransmission': True
                    }
                )
                return True
            return False
        
        # 开始链路传输
        self.start_link_transmission(current_time, link, packet)
        return True
    
    def start_link_transmission(self, current_time, link, packet):
        """开始链路传输"""
        # 检查是否达到最大并行传输数量
        if len(link.current_transmissions) >= link.max_concurrent_transmissions:
            # 如果达到最大并行传输数，将数据包加入队列
            link.queue.append(packet)
            return
        
        # 计算有效带宽
        effective_bandwidth = link.get_effective_bandwidth(packet, self.congestion_model)
        
        # 如果有效带宽太小，也放入队列等待
        if effective_bandwidth < 0.05:  # 小于50Mbps认为带宽不足
            link.queue.append(packet)
            return
        
        # 更新已分配带宽
        link.allocated_bandwidth += effective_bandwidth
        
        # 添加到当前传输列表
        link.current_transmissions.append(packet)
        packet.start_time = current_time
        packet.allocated_bandwidth = effective_bandwidth  # 记录分配的带宽
        link.active_flows += 1
        
        # 计算传输时间
        latency = link.get_current_latency()
        
        # 传输时间 = 延迟 + 数据大小/有效带宽
        # 数据大小单位为MB，带宽单位为Gbps，需要转换
        transmission_time = latency + (packet.size * 8) / (effective_bandwidth * 1000)  # 秒
        
        # 安排传输完成事件
        self.simulator.schedule_event(
            current_time + transmission_time,
            'complete_transmission',
            {'link': (link.src, link.dest), 'packet': packet}
        )
        
        # 记录链路利用率
        self.link_utilization[(link.src, link.dest)].append({
            'time': current_time,
            'utilization': min(1.0, link.allocated_bandwidth / link.bandwidth),
            'active_flows': link.active_flows,
            'bandwidth': effective_bandwidth
        })
    
    def complete_transmission(self, current_time, link_key, packet):
        """完成链路传输"""
        if link_key not in self.links:
            print(f"⚠️ [{current_time:.3f}s] 完成传输失败: 链路 {link_key} 不存在")
            return
        
        link = self.links[link_key]
        
        # 检查数据包是否在当前传输列表中
        if packet not in link.current_transmissions:
            print(f"⚠️ [{current_time:.3f}s] 完成传输失败: 链路 {link_key} 没有该数据包的活跃传输")
            return
        
        # 从当前传输列表中移除
        link.current_transmissions.remove(packet)
        
        # 释放已分配的带宽
        allocated_bandwidth = getattr(packet, 'allocated_bandwidth', 0)
        link.allocated_bandwidth -= allocated_bandwidth
        link.allocated_bandwidth = max(0, link.allocated_bandwidth)  # 确保不会出现负值
        
        packet.end_time = current_time
        
        # 记录链路利用率变化
        self.link_utilization[link_key].append({
            'time': current_time,
            'utilization': min(1.0, link.allocated_bandwidth / link.bandwidth),
            'active_flows': max(0, link.active_flows - 1),
            'bandwidth': link.bandwidth - allocated_bandwidth
        })
        
        link.active_flows = max(0, link.active_flows - 1)
        
        # 如果是最后一跳，传输完成
        if packet.final_dest == link.dest:
            if not packet.is_background and packet.packet_type not in ['ring_reduce', 'ring_gather']:
                print(f"[{current_time:.3f}s] {packet.packet_type} 传输完成: {packet.src}→{packet.final_dest} {packet.size}MB")
            
            # 记录传输完成事件
            self.packet_events.append({
                'time': current_time,
                'type': 'transmission_complete',
                'src': packet.src,
                'dest': packet.final_dest,
                'size': packet.size,
                'direction': packet.packet_type,
                'group_id': packet.group_id,
                'micro_batch_id': packet.micro_batch_id,
                'batch_id': packet.batch_id,
                'start_time': packet.start_time,
                'end_time': packet.end_time,
                'duration': packet.end_time - packet.start_time,
                'is_background': packet.is_background,
                'allocated_bandwidth': allocated_bandwidth
            })
            
            # 通知模拟器传输完成
            self.simulator.notify_transmission_complete(
                current_time, packet.src, packet.final_dest, 
                packet.size, packet.packet_type, packet.group_id, 
                packet.micro_batch_id, packet.is_background, packet.batch_id
            )
        else:
            # 继续路由到下一跳
            self._continue_routing(current_time, link.dest, packet)
        
        # 处理队列中的下一个数据包
        self._process_next_in_queue(current_time, link)
    
    def _continue_routing(self, current_time, current_node, packet):
        """继续将数据包路由到下一跳"""
        next_hop = self.get_next_hop(current_node, packet.final_dest, packet)
        
        if next_hop is None:
            print(f"⚠️ [{current_time:.3f}s] 路由失败: 从 {current_node} 到 {packet.final_dest} 没有有效路径")
            return
        
        # 获取下一跳链路
        link_key = (current_node, next_hop)
        if link_key not in self.links:
            print(f"⚠️ [{current_time:.3f}s] 链路 {link_key} 不存在")
            return
        
        link = self.links[link_key]
        
        # 模拟丢包
        if link.will_packet_drop():
            if not packet.is_background and packet.packet_type not in ['ring_reduce', 'ring_gather']:
                print(f"⚠️ [{current_time:.3f}s] {packet.packet_type} 传输丢包: {current_node}→{next_hop} (目标 {packet.final_dest}) {packet.size}MB")
            
            # 记录丢包事件
            self.packet_events.append({
                'time': current_time,
                'type': 'packet_loss',
                'src': packet.src,
                'dest': packet.final_dest,
                'current_node': current_node,
                'next_hop': next_hop,
                'size': packet.size,
                'direction': packet.packet_type,
                'group_id': packet.group_id,
                'micro_batch_id': packet.micro_batch_id,
                'batch_id': packet.batch_id,
                'is_background': packet.is_background
            })
            
            # 安排重传
            if not packet.is_background and packet.retransmission_count < self.max_retransmissions:
                packet.retransmission_count += 1
                self.retransmission_count += 1
                
                self.simulator.schedule_event(
                    current_time + self.retransmission_timeout,
                    'start_transmission',
                    {
                        'micro_batch_id': packet.micro_batch_id,
                        'batch_id': packet.batch_id,
                        'src_node': packet.src,
                        'dest_node': packet.final_dest,
                        'group_id': packet.group_id,
                        'size': packet.size,
                        'direction': packet.packet_type,
                        'retransmission': True
                    }
                )
                return
            return
        
        # 开始链路传输
        self.start_link_transmission(current_time, link, packet)
    
    def _process_next_in_queue(self, current_time, link):
        """处理队列中的下一个数据包"""
        # 检查是否有足够的带宽和并行传输槽位
        while (link.allocated_bandwidth < link.bandwidth and 
               len(link.current_transmissions) < link.max_concurrent_transmissions and 
               link.queue):
            # 从队列中取出下一个数据包
            next_packet = link.queue.pop(0)
            # 开始传输
            self.start_link_transmission(current_time, link, next_packet)
    
    def handle_transmission_complete(self, current_time, link_key, packet):
        """处理传输完成事件"""
        # 检查链路是否存在
        if link_key not in self.links:
            print(f"警告: 链路 {link_key} 不存在")
            return False, None
            
        link = self.links[link_key]
        
        # 从当前传输列表中移除完成的数据包
        if packet in link.current_transmissions:
            link.current_transmissions.remove(packet)
        
        # 释放已分配的带宽
        link.allocated_bandwidth -= getattr(packet, 'allocated_bandwidth', 0)
        link.allocated_bandwidth = max(0, link.allocated_bandwidth)  # 确保不会出现负值
        
        # 更新链路状态
        link.active_flows -= 1
        link.active_flows = max(0, link.active_flows)  # 确保不会出现负值
        
        is_background = getattr(packet, 'is_background', False)
        direction = packet.packet_type

        if not is_background and direction not in ['ring_reduce', 'ring_gather']:
            print(f"[{current_time:.3f}s] {direction} 传输完成: {link_key[0]}→{link_key[1]} ({packet.size}MB)")
        
        src = link_key[1]  # 当前节点
        dest = packet.final_dest  # 最终目的地
        
        # 如果数据包已到达最终目的地
        if packet.final_dest == link_key[1]:
            # 处理队列中的下一个数据包（尝试启动新的传输）
            self._process_next_in_queue(current_time, link)
            return True, packet
        
        # 否则，继续路由到下一跳
        next_hop = self.get_next_hop(src, dest, packet)
        
        if next_hop is None:
            print(f"警告: 从 {src} 到 {dest} 没有可用路由")
            # 处理队列中的下一个数据包
            self._process_next_in_queue(current_time, link)
            return False, None
        
        # 安排下一跳传输
        next_link_key = (src, next_hop)
        
        # 检查链路是否存在
        if next_link_key not in self.links:
            print(f"警告: 链路 {next_link_key} 不存在")
            # 处理队列中的下一个数据包
            self._process_next_in_queue(current_time, link)
            return False, None
        
        next_link = self.links[next_link_key]
        
        # 尝试在下一个链路上开始传输
        self.start_link_transmission(current_time, next_link, packet)
        
        # 处理当前链路队列中的下一个数据包
        self._process_next_in_queue(current_time, link)
        
        return False, None
    
    def get_network_stats(self):
        """获取网络统计信息"""
        total_links = len(self.links)
        active_links = 0
        congested_links = 0
        total_queued = 0
        max_queue = 0
        total_active_flows = 0
        
        for link_key, link in self.links.items():
            if link.active_flows > 0 or len(link.current_transmissions) > 0:
                active_links += 1
            if link.congested:
                congested_links += 1
            
            queue_length = len(link.queue)
            total_queued += queue_length
            max_queue = max(max_queue, queue_length)
            total_active_flows += link.active_flows
        
        avg_queue = total_queued / total_links if total_links > 0 else 0
        avg_active_flows = total_active_flows / total_links if total_links > 0 else 0
        
        return {
            'total_links': total_links,
            'active_links': active_links,
            'congested_links': congested_links,
            'congestion_percentage': (congested_links / total_links * 100) if total_links > 0 else 0,
            'avg_queue_length': avg_queue,
            'max_queue_length': max_queue,
            'total_packets_sent': self.total_packets_sent,
            'total_bytes_sent': self.total_bytes_sent,
            'retransmissions': self.retransmission_count,
            'congestion_events': self.congestion_events,
            'avg_active_flows': avg_active_flows,
            'background_packets': self.background_packets_sent,
            'background_bytes': self.background_bytes_sent,
            'path_diversity': self.path_diversity,
            'avg_path_length': self.average_path_length
        }
    
    def get_link_utilization(self, link_key):
        """获取链路利用率数据"""
        if link_key in self.link_utilization:
            return self.link_utilization[link_key]
        return []
    
    def get_all_link_utilization(self):
        """获取所有链路的利用率数据"""
        return self.link_utilization
    
    def get_packet_events(self):
        """获取所有数据包事件"""
        return self.packet_events
    
    def clear_stats(self):
        """清除统计数据"""
        self.retransmission_count = 0
        self.congestion_events = 0
        self.packet_events = []
        self.total_packets_sent = 0
        self.total_bytes_sent = 0
        self.background_packets_sent = 0
        self.background_bytes_sent = 0
        
        # 清除链路统计数据
        for link_key in self.link_utilization:
            self.link_utilization[link_key] = []
        
        # 重置链路状态
        for link in self.links.values():
            link.packet_loss_count = 0
            link.congested = False
            link.active_flows = 0
    
    def generate_background_traffic(self, current_time, intensity=0.1, duration=1.0, size_range=(1, 10)):
        """生成背景流量"""
        num_nodes = len(self.nodes)
        if num_nodes < 2:
            return
        
        # 根据强度确定生成的流量数量
        num_flows = max(1, int(num_nodes * intensity))
        
        for _ in range(num_flows):
            # 随机选择源和目标节点
            src = random.randint(0, num_nodes - 1)
            dest = random.randint(0, num_nodes - 1)
            
            # 确保源和目标不同
            while src == dest:
                dest = random.randint(0, num_nodes - 1)
            
            # 随机生成数据包大小
            size = random.uniform(size_range[0], size_range[1])
            
            # 随机选择流量类型
            traffic_type = random.choice(['data', 'parameter', 'gradient'])
            
            # 生成随机的微批次ID
            micro_batch_id = random.randint(0, 1000)
            
            # 开始传输
            self.start_transmission(
                current_time=current_time,
                micro_batch_id=micro_batch_id,
                src_node=src,
                dest_node=dest,
                size=size,
                direction=traffic_type,
                is_background=True
            )
        
        # 安排下一次背景流量生成
        self.simulator.schedule_event(
            current_time + duration,
            'generate_background_traffic',
            {'intensity': intensity, 'duration': duration, 'size_range': size_range}
        )
    
    def get_path(self, src, dest):
        """获取从src到dest的完整路径"""
        if src == dest:
            return [src]
        
        path = [src]
        current = src
        
        # 最大跳数限制，防止循环
        max_hops = len(self.nodes)
        hop_count = 0
        
        while current != dest and hop_count < max_hops:
            next_hop = self.get_next_hop(current, dest)
            if next_hop is None:
                return None  # 没有路径
            
            path.append(next_hop)
            current = next_hop
            hop_count += 1
        
        if current != dest:
            return None  # 路径没有到达目标
            
        return path
    
    def get_all_paths(self):
        """获取所有节点对之间的路径"""
        paths = {}
        for src in range(len(self.nodes)):
            for dest in range(len(self.nodes)):
                if src != dest:
                    path = self.get_path(src, dest)
                    if path:
                        paths[(src, dest)] = path
        return paths
    
    def visualize_network(self, filename='network_topology.png'):
        """可视化网络拓扑"""
        try:
            import networkx as nx
            import matplotlib.pyplot as plt
            
            G = nx.DiGraph()
            
            # 添加节点
            for node in range(len(self.nodes)):
                G.add_node(node)
            
            # 添加边
            for link_key, link in self.links.items():
                src, dest = link_key
                G.add_edge(src, dest, weight=link.bandwidth)
            
            # 创建图形
            plt.figure(figsize=(12, 8))
            pos = nx.spring_layout(G)
            
            # 绘制节点
            nx.draw_networkx_nodes(G, pos, node_size=700, node_color='lightblue')
            
            # 绘制边
            nx.draw_networkx_edges(G, pos, width=1.0, alpha=0.5)
            
            # 添加标签
            nx.draw_networkx_labels(G, pos, font_size=10, font_family='sans-serif')
            
            # 添加边标签（带宽）
            edge_labels = {(u, v): f"{d['weight']}Gbps" for u, v, d in G.edges(data=True)}
            nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=8)
            
            plt.title('Network Topology')
            plt.axis('off')
            plt.tight_layout()
            plt.savefig(filename, dpi=300, bbox_inches='tight')
            plt.close()
            
            return True
        except ImportError:
            print("警告: 需要安装 networkx 和 matplotlib 来可视化网络")
            return False
        except Exception as e:
            print(f"可视化网络时出错: {e}")
            return False
    
    def get_routing_statistics(self):
        """获取路由统计信息"""
        # 计算链路负载均衡度
        load_balance_score = 0
        if self.links:
            link_loads = []
            for link in self.links.values():
                link_loads.append(link.active_flows / max(1, link.bandwidth))
            
            if link_loads:
                avg_load = sum(link_loads) / len(link_loads)
                # 计算标准差
                variance = sum((load - avg_load) ** 2 for load in link_loads) / len(link_loads)
                std_dev = variance ** 0.5
                # 负载均衡度 = 1 - 标准差/平均负载 (标准化到0-1之间)
                load_balance_score = 1.0 - min(1.0, std_dev / (avg_load + 0.001))
        
        # 采样路由性能
        current_time = self.simulator.current_time if hasattr(self.simulator, 'current_time') else 0
        path_utilization = self._calculate_path_utilization()
        self.routing_performance_samples.append((current_time, path_utilization, load_balance_score))
        
        return {
            "algorithm": self.routing_algorithm,
            "ecmp_strategy": self.ecmp_strategy if self.routing_algorithm == "ecmp" else None,
            "average_path_length": getattr(self, 'average_path_length', 0),
            "path_diversity": getattr(self, 'path_diversity', 0),
            "routing_calculations": self.routing_calculations,
            "load_balance_score": load_balance_score
        }

    def _calculate_path_utilization(self):
        """计算路径利用率"""
        # 计算已使用的路径数量与总可能路径数量的比例
        used_paths = 0
        total_paths = 0
        
        for path_key, count in self.path_counts.items():
            src, dest = path_key
            used = 0
            
            # 检查链路是否被使用
            if self.routing_algorithm == "ecmp":
                next_hops = self.routing_tables.get(src, {}).get(dest, [])
                if isinstance(next_hops, list):
                    for hop in next_hops:
                        link_key = (src, hop)
                        if link_key in self.links and self.links[link_key].active_flows > 0:
                            used += 1
                else:
                    link_key = (src, next_hops)
                    if link_key in self.links and self.links[link_key].active_flows > 0:
                        used = 1
            else:
                next_hop = self.routing_tables.get(src, {}).get(dest)
                if next_hop is not None:
                    link_key = (src, next_hop)
                    if link_key in self.links and self.links[link_key].active_flows > 0:
                        used = 1
            
            used_paths += used
            total_paths += count
        
        return used_paths / max(1, total_paths)


    def get_link_utilization(self):
        """获取链路利用率数据"""
        return self.link_utilization

    def reset_stats(self):
        """重置统计信息"""
        self.retransmission_count = 0
        self.congestion_events = 0
        self.background_packets_sent = 0
        self.background_bytes_sent = 0
        self.total_packets_sent = 0
        self.total_bytes_sent = 0
        self.packet_events = []
        
        for link in self.links.values():
            link.packet_loss_count = 0
        
        for link_key in self.link_utilization:
            self.link_utilization[link_key] = []


