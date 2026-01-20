import numpy as np
import random
import logging
from typing import List, Dict, Tuple, Optional, Union
from sklearn.cluster import KMeans
import time

class QuantumInspiredTopoScheduler:
    """
    拓扑感知调度器，根据网络拓扑优化分布式训练的节点分配
    """
    
    def __init__(self, topology_file: str, logger=None):
        """
        初始化调度器
        
        Args:
            topology: 带宽矩阵，topology[i][j]表示节点i和j之间的带宽
            logger: 日志记录器
        """
        self.topology = self._load_topology(topology_file)
        self.n = len(self.topology)
        
        if logger is None:
            self.logger = logging.getLogger("TopologyAwareScheduler")
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        else:
            self.logger = logger

    def _load_topology(self, topology_file: str) -> np.ndarray:
        """加载拓扑文件并返回带宽邻接矩阵"""
        with open(topology_file, 'r') as f:
            lines = f.readlines()
            
        matrix = []
        for line in lines:
            row = [float(x) for x in line.strip().split()]
            matrix.append(row)
            
        return np.array(matrix)
    
    def schedule(self, num_stages: int, method: str = "hybrid", num_groups: int = 0) -> List[List[int]]:
        """
        调度节点到不同组和阶段
        
        Args:
            num_groups: 分组数量
            num_stages: 每组的阶段数量
            method: 调度方法，可选值：
                    - "kmeans": K-means聚类分组
                    - "greedy": 贪婪带宽优先分组
                    - "sa": 模拟退火优化
                    - "kmeans_sa": K-means初始化+模拟退火优化
                    - "tensor_flow": 量子启发式算法
                    
        Returns:
            分组结果，每个元素是一个节点列表
        """
        start_time = time.time()
        
        if method == "kmeans":
            return self._kmeans_grouping(num_groups, num_stages)
        elif method == "greedy":
            return self._greedy_grouping(num_groups, num_stages)
        elif method == "sa":
            return self._simulated_annealing_grouping(num_groups, num_stages)
        elif method == "kmeans_sa":
            # K-means初始化+模拟退火优化
            return self._kmeans_sa_grouping(num_groups, num_stages)
        elif method == "quantum":
            return self._quantum_grouping(num_groups, num_stages)
        elif method == "random":
            return self._random_grouping(num_groups, num_stages)
        else:
            self.logger.warning(f"未知的调度方法: {method}，将使用K-means")
            return self._kmeans_grouping(num_groups, num_stages)
        
        end_time = time.time()
        self.logger.info(f"调度完成，使用方法: {method}，耗时: {end_time - start_time:.4f}秒")
        
        # 验证结果
        self._validate_groups(groups, num_stages)
        
        return groups
    
    def _random_grouping(self, num_groups: int, num_stages: int) -> List[List[int]]:
        """
        随机分组算法 - 完全随机地将节点分配到各个组中
        
        Args:
            num_groups: 分组数量
            num_stages: 每组的阶段数（节点数）
            
        Returns:
            分组结果，每个组是一个节点ID列表
        """
        self.logger.info("使用随机分组算法")
        
        # 检查参数有效性
        total_nodes_needed = num_groups * num_stages
        if total_nodes_needed > self.n:
            self.logger.warning(f"请求的节点数 {total_nodes_needed} 超过可用节点数 {self.n}")
            # 调整分组参数
            if num_stages > num_groups:
                num_stages = self.n // num_groups
                if num_stages == 0:
                    num_stages = 1
                    num_groups = min(self.n, num_groups)
            else:
                num_groups = self.n // num_stages
                if num_groups == 0:
                    num_groups = 1
                    num_stages = min(self.n, num_stages)
            
            self.logger.info(f"调整为 {num_groups} 组，每组 {num_stages} 个节点")
        
        # 创建节点列表并随机打乱
        nodes = list(range(self.n))
        random.shuffle(nodes)
        
        # 分配节点到各组
        groups = []
        node_index = 0
        
        for _ in range(num_groups):
            if node_index + num_stages <= len(nodes):
                group = nodes[node_index:node_index + num_stages]
                groups.append(group)
                node_index += num_stages
            else:
                # 如果剩余节点不足，使用可用的节点
                remaining = len(nodes) - node_index
                if remaining > 0:
                    group = nodes[node_index:]
                    groups.append(group)
                break
        
        # 评估随机分组的质量
        if self.logger:
            avg_intra_group_bw = self._calculate_avg_intra_group_bandwidth(groups)
            self.logger.info(f"随机分组完成，组内平均带宽: {avg_intra_group_bw:.2f}")
        
        return groups

    def _calculate_avg_intra_group_bandwidth(self, groups: List[List[int]]) -> float:
        """
        计算组内平均带宽
        
        Args:
            groups: 分组结果
            
        Returns:
            组内平均带宽
        """
        total_bw = 0.0
        total_pairs = 0
        
        for group in groups:
            for i in range(len(group)):
                for j in range(i+1, len(group)):
                    total_bw += self.topology[group[i]][group[j]]
                    total_pairs += 1
        
        if total_pairs > 0:
            return total_bw / total_pairs
        else:
            return 0.0

    
    def _validate_groups(self, groups: List[List[int]], num_stages: int) -> None:
        """
        验证分组结果是否合法
        
        Args:
            groups: 分组结果
            num_stages: 每组的阶段数量
        """
        # 检查每个组的大小
        for i, group in enumerate(groups):
            if len(group) != num_stages:
                self.logger.warning(f"组 {i} 的大小 ({len(group)}) 不等于期望的阶段数 ({num_stages})")
        
        # 检查节点是否被重复分配
        all_nodes = [node for group in groups for node in group]
        if len(all_nodes) != len(set(all_nodes)):
            self.logger.warning("存在被重复分配的节点")
        
        # 检查节点是否超出范围
        for node in all_nodes:
            if node < 0 or node >= self.n:
                self.logger.warning(f"节点 {node} 超出范围 [0, {self.n-1}]")
    
    def _kmeans_grouping(self, num_groups: int, num_stages: int) -> List[List[int]]:
        """
        使用K-means进行拓扑感知分组，组内优先使用高带宽（数据并行）
        
        Args:
            num_groups: 分组数量
            num_stages: 每组的阶段数量
            
        Returns:
            分组结果
        """
        # 检查是否有足够的节点
        if self.n < num_groups * num_stages:
            self.logger.warning(f"节点数量 {self.n} 小于请求的组数 {num_groups} * 阶段数 {num_stages}")
            # 调整组数
            num_groups = self.n // num_stages
            if num_groups == 0:
                num_groups = 1
                num_stages = min(num_stages, self.n)
        
        # 创建带宽特征矩阵
        features = []
        for i in range(self.n):
            # 使用节点的带宽连接情况作为特征
            features.append(self.topology[i])
        
        # 应用K-means聚类
        kmeans = KMeans(n_clusters=num_groups, random_state=42, n_init=10)
        cluster_labels = kmeans.fit_predict(features)
        
        # 按聚类标签分配节点到不同组
        groups = [[] for _ in range(num_groups)]
        for i in range(self.n):
            cluster = cluster_labels[i]
            if len(groups[cluster]) < num_stages:
                groups[cluster].append(i)
        
        # 确保每个组都有足够的节点
        unassigned_nodes = []
        for i in range(self.n):
            if all(i not in group for group in groups):
                unassigned_nodes.append(i)
        
        # 为不满的组添加节点
        for group in groups:
            while len(group) < num_stages and unassigned_nodes:
                # 找到与当前组连接最好的节点
                best_node = None
                best_score = float('-inf')
                
                for node in unassigned_nodes:
                    # 计算节点与组内所有节点的带宽和
                    score = sum(self.topology[node][g] for g in group)
                    if score > best_score:
                        best_score = score
                        best_node = node
                
                if best_node is not None:
                    group.append(best_node)
                    unassigned_nodes.remove(best_node)
                else:
                    break
        
        # 过滤掉空组或不完整的组
        groups = [group for group in groups if len(group) == num_stages]
        
        # 对每个组应用高带宽优先的组内排序（数据并行）
        final_groups = []
        for group in groups:
            ordered_group = self._pipeline_aware_ordering_high_bandwidth(group)
            final_groups.append(ordered_group)
        
        return final_groups
    
    def _pipeline_aware_ordering_high_bandwidth(self, group: List[int]) -> List[int]:
        """
        基于流水线通信模式优化组内顺序，优先使用高带宽链路（组内数据并行）
        
        Args:
            group: 组内节点列表
            
        Returns:
            优化后的节点顺序
        """
        if len(group) <= 2:
            return group
        
        n = len(group)
        # 创建通信成本矩阵
        costs = np.zeros((n, n))
        
        for i in range(n):
            for j in range(n):
                if i != j:
                    # 流水线通信模式：相邻阶段(|i-j|=1)通信最频繁
                    # 使用指数衰减模拟通信频率
                    comm_frequency = np.exp(-0.5 * abs(i-j))
                    
                    # 获取节点间的带宽
                    bandwidth = self.topology[group[i]][group[j]]
                    if bandwidth > 0:
                        # 使用带宽倒数作为成本（高带宽 = 低成本）
                        costs[i][j] = comm_frequency * (1.0 / bandwidth)
                    else:
                        costs[i][j] = comm_frequency * 1000  # 无连接 = 高成本
        
        # 使用匈牙利算法求解最优分配
        from scipy.optimize import linear_sum_assignment
        row_ind, col_ind = linear_sum_assignment(costs)
        
        # 根据分配结果重排节点
        ordered_group = [group[i] for i in col_ind]
        return ordered_group
    
    def _greedy_grouping(self, num_groups: int, num_stages: int) -> List[List[int]]:
        """
        使用贪婪算法进行带宽优先分组，组内高带宽（数据并行），组间低带宽（流水线并行）
        
        Args:
            num_groups: 分组数量
            num_stages: 每组的阶段数量
            
        Returns:
            分组结果
        """
        # 检查是否有足够的节点
        if self.n < num_groups * num_stages:
            self.logger.warning(f"节点数量 {self.n} 小于请求的组数 {num_groups} * 阶段数 {num_stages}")
            # 调整组数
            num_groups = self.n // num_stages
            if num_groups == 0:
                num_groups = 1
                num_stages = min(num_stages, self.n)
        
        # 初始化分组
        groups = [[] for _ in range(num_groups)]
        assigned_nodes = set()
        
        # 获取所有边及其带宽
        edges = []
        for i in range(self.n):
            for j in range(i+1, self.n):
                if self.topology[i][j] > 0:
                    edges.append((i, j, self.topology[i][j]))
        
        # 按带宽降序排序边
        edges.sort(key=lambda x: x[2], reverse=True)
        
        # 首先为每个组选择一个起始节点（尽量选择高带宽连接的节点）
        nodes_by_bandwidth = sorted(range(self.n), 
                                  key=lambda i: sum(self.topology[i]), 
                                  reverse=True)
        
        for i in range(min(num_groups, len(nodes_by_bandwidth))):
            groups[i].append(nodes_by_bandwidth[i])
            assigned_nodes.add(nodes_by_bandwidth[i])
        
        # 使用高带宽边填充组内节点（数据并行）
        for u, v, bw in edges:
            if len(assigned_nodes) >= num_groups * num_stages:
                break
                
            # 检查这两个节点是否可以放在同一组
            for group in groups:
                if len(group) < num_stages:
                    if u in group and v not in assigned_nodes:
                        group.append(v)
                        assigned_nodes.add(v)
                        break
                    elif v in group and u not in assigned_nodes:
                        group.append(u)
                        assigned_nodes.add(u)
                        break
        
        # 如果还有组不满，添加剩余节点
        remaining_nodes = set(range(self.n)) - assigned_nodes
        for group in groups:
            while len(group) < num_stages and remaining_nodes:
                # 找到与当前组连接最好的节点
                best_node = None
                best_score = float('-inf')
                
                for node in remaining_nodes:
                    score = sum(self.topology[node][g] for g in group)
                    if score > best_score:
                        best_score = score
                        best_node = node
                
                if best_node is not None:
                    group.append(best_node)
                    remaining_nodes.remove(best_node)
                    assigned_nodes.add(best_node)
                else:
                    # 如果没有连接好的节点，选择任意一个
                    node = next(iter(remaining_nodes))
                    group.append(node)
                    remaining_nodes.remove(node)
                    assigned_nodes.add(node)
        
        # 过滤掉不完整的组
        groups = [group for group in groups if len(group) == num_stages]
        
        # 对每个组应用高带宽优先的排序（数据并行）
        final_groups = []
        for group in groups:
            ordered_group = self._pipeline_aware_ordering_high_bandwidth(group)
            final_groups.append(ordered_group)
        
        return final_groups
    
    def _simulated_annealing_ordering_high_bandwidth(self, group: List[int]) -> List[int]:
        """
        使用模拟退火优化组内节点顺序，优先使用高带宽链路（组内数据并行）
        
        Args:
            group: 组内节点列表
            
        Returns:
            优化后的节点顺序
        """
        if len(group) <= 2:
            return group
        
        # 初始解
        current_solution = group.copy()
        current_energy = self._calculate_ordering_energy_high_bandwidth(current_solution)
        
        # 模拟退火参数
        temp = 1.0
        cooling_rate = 0.95
        steps = 500
        
        best_solution = current_solution.copy()
        best_energy = current_energy
        
        # 模拟退火过程
        for step in range(steps):
            # 生成新解：随机交换两个位置
            new_solution = current_solution.copy()
            i, j = random.sample(range(len(new_solution)), 2)
            new_solution[i], new_solution[j] = new_solution[j], new_solution[i]
            
            # 计算新解的能量
            new_energy = self._calculate_ordering_energy_high_bandwidth(new_solution)
            
            # 决定是否接受新解
            if new_energy < current_energy:
                # 更好的解，直接接受
                current_solution = new_solution
                current_energy = new_energy
                
                # 更新最佳解
                if current_energy < best_energy:
                    best_solution = current_solution.copy()
                    best_energy = current_energy
            else:
                # 较差的解，以一定概率接受
                delta_e = new_energy - current_energy
                if random.random() < np.exp(-delta_e / temp):
                    current_solution = new_solution
                    current_energy = new_energy
            
            # 降温
            temp *= cooling_rate
        
        return best_solution
    
    def _calculate_ordering_energy_high_bandwidth(self, ordered_group: List[int]) -> float:
        """
        计算组内顺序的能量（通信成本），优先使用高带宽链路（组内数据并行）
        
        Args:
            ordered_group: 有序的节点列表
            
        Returns:
            能量值（较低表示更好的顺序）
        """
        energy = 0.0
        n = len(ordered_group)
        
        # 计算相邻阶段之间的通信成本
        for i in range(n-1):
            node_i = ordered_group[i]
            node_j = ordered_group[i+1]
            
            # 获取带宽，使用带宽倒数作为成本（高带宽=低成本）
            bandwidth = self.topology[node_i][node_j]
            if bandwidth > 0:
                energy += 1.0 / bandwidth  # 高带宽链路有低能量（低成本）
            else:
                energy += 1000  # 无连接时使用高能量（高成本）
        
        # 考虑非相邻阶段之间的通信（权重较小）
        for i in range(n):
            for j in range(i+2, n):
                node_i = ordered_group[i]
                node_j = ordered_group[j]
                
                # 流水线中，远距离阶段通信频率降低
                stage_distance = j - i
                comm_frequency = np.exp(-0.5 * stage_distance)
                
                # 获取带宽，考虑通信频率
                bandwidth = self.topology[node_i][node_j]
                if bandwidth > 0:
                    energy += comm_frequency * (1.0 / bandwidth)  # 高带宽=低成本
                else:
                    energy += comm_frequency * 1000  # 无连接=高成本
        
        return energy
    
    def _kmeans_sa_grouping(self, num_groups: int, num_stages: int) -> List[List[int]]:
        """
        使用K-means进行初始分组，然后用模拟退火优化组内顺序
        
        Args:
            num_groups: 分组数量
            num_stages: 每组的阶段数量
            
        Returns:
            分组结果
        """
        # 先使用K-means进行分组
        groups = self._kmeans_grouping(num_groups, num_stages)
        
        # 然后使用模拟退火优化每个组的顺序
        final_groups = []
        for group in groups:
            ordered_group = self._simulated_annealing_ordering_high_bandwidth(group)
            final_groups.append(ordered_group)
        
        return final_groups
    
    def _simulated_annealing_grouping(self, num_groups: int, num_stages: int) -> List[List[int]]:
        """
        使用纯模拟退火进行分组和组内顺序优化，组内高带宽（数据并行），组间低带宽（流水线并行）
        
        Args:
            num_groups: 分组数量
            num_stages: 每组的阶段数量
            
        Returns:
            分组结果
        """
        # 检查是否有足够的节点
        if self.n < num_groups * num_stages:
            self.logger.warning(f"节点数量 {self.n} 小于请求的组数 {num_groups} * 阶段数 {num_stages}")
            # 调整组数
            num_groups = self.n // num_stages
            if num_groups == 0:
                num_groups = 1
                num_stages = min(num_stages, self.n)
        
        # 初始解：随机分配节点到组
        all_nodes = list(range(self.n))
        random.shuffle(all_nodes)
        
        current_solution = []
        node_idx = 0
        
        for _ in range(num_groups):
            if node_idx + num_stages <= len(all_nodes):
                group = all_nodes[node_idx:node_idx + num_stages]
                current_solution.append(group)
                node_idx += num_stages
        
        # 计算初始解的能量
        current_energy = self._calculate_grouping_energy_data_parallel_intra(current_solution)
        
        # 保存最佳解
        best_solution = [group.copy() for group in current_solution]
        best_energy = current_energy
        
        # 模拟退火参数
        temp = 10.0  # 初始温度
        cooling_rate = 0.97
        steps = 2000
        
        # 模拟退火过程
        for step in range(steps):
            # 生成新解
            new_solution = [group.copy() for group in current_solution]
            
            # 随机选择操作类型
            op_type = random.random()
            
            if op_type < 0.4:  # 40%概率：交换两个组内的节点位置（优化组内顺序）
                group_idx = random.randrange(len(new_solution))
                group = new_solution[group_idx]
                if len(group) >= 2:
                    i, j = random.sample(range(len(group)), 2)
                    group[i], group[j] = group[j], group[i]
            
            elif op_type < 0.8:  # 40%概率：交换两个不同组的节点（改变分组）
                if len(new_solution) >= 2:
                    group1_idx, group2_idx = random.sample(range(len(new_solution)), 2)
                    group1 = new_solution[group1_idx]
                    group2 = new_solution[group2_idx]
                    
                    if len(group1) > 0 and len(group2) > 0:
                        pos1 = random.randrange(len(group1))
                        pos2 = random.randrange(len(group2))
                        group1[pos1], group2[pos2] = group2[pos2], group1[pos1]
            
            else:  # 20%概率：重新排序一个组
                group_idx = random.randrange(len(new_solution))
                random.shuffle(new_solution[group_idx])
            
            # 计算新解的能量
            new_energy = self._calculate_grouping_energy_data_parallel_intra(new_solution)
            
            # 决定是否接受新解
            if new_energy < current_energy:
                # 更好的解，直接接受
                current_solution = new_solution
                current_energy = new_energy
                
                # 更新最佳解
                if current_energy < best_energy:
                    best_solution = [group.copy() for group in current_solution]
                    best_energy = current_energy
            else:
                # 较差的解，以一定概率接受
                delta_e = new_energy - current_energy
                if random.random() < np.exp(-delta_e / temp):
                    current_solution = new_solution
                    current_energy = new_energy
            
            # 降温
            temp *= cooling_rate
        
        # 确保节点唯一分配（最终检查）
        final_solution = []
        assigned_nodes = set()
        
        for group in best_solution:
            unique_group = []
            for node in group:
                if node not in assigned_nodes:
                    unique_group.append(node)
                    assigned_nodes.add(node)
            
            # 如果组不完整，尝试添加未分配的节点
            remaining_nodes = set(range(self.n)) - assigned_nodes
            while len(unique_group) < num_stages and remaining_nodes:
                # 找到与当前组连接最好的节点
                best_node = None
                best_score = float('-inf')
                
                for node in remaining_nodes:
                    score = sum(self.topology[node][g] for g in unique_group)
                    if score > best_score:
                        best_score = score
                        best_node = node
                
                if best_node is not None:
                    unique_group.append(best_node)
                    remaining_nodes.remove(best_node)
                    assigned_nodes.add(best_node)
                else:
                    break
            
            if len(unique_group) == num_stages:
                # 对组内节点进行高带宽优先排序（数据并行）
                ordered_group = self._pipeline_aware_ordering_high_bandwidth(unique_group)
                final_solution.append(ordered_group)
        
        return final_solution
    
    def _calculate_grouping_energy_data_parallel_intra(self, groups: List[List[int]]) -> float:
        """
        计算整体分组方案的能量，优先使用高带宽链路进行组内数据并行，低带宽链路进行组间流水线
        
        Args:
            groups: 分组方案，每个元素是一个节点列表
            
        Returns:
            能量值（较低表示更好的方案）
        """
        total_energy = 0.0
        
        # 计算每个组内的通信成本（优先高带宽 - 数据并行）
        for group in groups:
            # 组内顺序能量 - 使用高带宽优先的能量计算
            group_energy = 0.0
            for i in range(len(group) - 1):
                node_i = group[i]
                node_j = group[i + 1]
                bandwidth = self.topology[node_i][node_j]
                if bandwidth > 0:
                    group_energy += 1.0 / bandwidth  # 高带宽 = 低成本
                else:
                    group_energy += 1000.0  # 无连接 = 高成本
            
            total_energy += group_energy
        
        # 计算组间通信成本（优先低带宽 - 流水线并行）
        for i, group1 in enumerate(groups):
            for j, group2 in enumerate(groups):
                if i < j:  # 避免重复计算
                    # 计算组间通信带宽
                    inter_group_bandwidth = 0.0
                    for node1 in group1:
                        for node2 in group2:
                            inter_group_bandwidth += self.topology[node1][node2]
                    
                    # 惩罚高组间带宽（流水线应该使用低带宽）
                    total_energy += 0.1 * inter_group_bandwidth
        
        return total_energy
    
    def _tensor_flow_optimization(self, num_groups: int, num_stages: int) -> List[List[int]]:
        """
        使用量子启发式算法进行分组和排序优化
        
        Args:
            num_groups: 分组数量
            num_stages: 每组的阶段数量
            
        Returns:
            分组结果
        """
        # 检查是否有足够的节点
        if self.n < num_groups * num_stages:
            self.logger.warning(f"节点数量 {self.n} 小于请求的组数 {num_groups} * 阶段数 {num_stages}")
            # 调整组数
            num_groups = self.n // num_stages
            if num_groups == 0:
                num_groups = 1
                num_stages = min(num_stages, self.n)
        
        # 步骤1: 计算拉普拉斯矩阵
        degree_matrix = np.diag(np.sum(self.topology, axis=1))
        laplacian = degree_matrix - self.topology
        
        # 步骤2: 计算拉普拉斯矩阵的特征值和特征向量
        eigenvalues, eigenvectors = np.linalg.eigh(laplacian)
        
        # 步骤3: 使用前k个非零特征向量作为特征
        k = min(num_groups + 1, self.n)
        features = eigenvectors[:, 1:k]  # 跳过第一个特征向量（对应特征值0）
        
        # 步骤4: 应用K-means聚类
        kmeans = KMeans(n_clusters=num_groups, random_state=42, n_init=10)
        cluster_labels = kmeans.fit_predict(features)
        
        # 步骤5: 初始分组
        groups = [[] for _ in range(num_groups)]
        for i in range(self.n):
            cluster = cluster_labels[i]
            if len(groups[cluster]) < num_stages:
                groups[cluster].append(i)
        
        # 步骤6: 量子扰动 - 模拟量子叠加效应
        # 随机交换一些节点的分组，增加搜索多样性
        for _ in range(int(self.n * 0.1)):  # 扰动10%的节点
            if len(groups) >= 2:  # 至少需要两个组才能交换
                group1_idx, group2_idx = random.sample(range(len(groups)), 2)
                group1, group2 = groups[group1_idx], groups[group2_idx]
                
                if group1 and group2:  # 确保两个组都不为空
                    node1_idx = random.randrange(len(group1))
                    node2_idx = random.randrange(len(group2))
                    group1[node1_idx], group2[node2_idx] = group2[node2_idx], group1[node1_idx]
        
        # 步骤7: 量子模拟退火 - 优化未分配节点的选择
        unassigned_nodes = []
        for i in range(self.n):
            if all(i not in group for group in groups):
                unassigned_nodes.append(i)
        
        # 为不满的组添加节点
        for group in groups:
            while len(group) < num_stages and unassigned_nodes:
                # 量子概率分配 - 使用带宽加权概率选择节点
                weights = []
                for node in unassigned_nodes:
                    # 计算节点与组内所有节点的带宽和
                    weight = sum(self.topology[node][g] for g in group) + 1e-6  # 避免零权重
                    weights.append(weight)
                
                # 归一化权重作为概率
                total_weight = sum(weights)
                probs = [w / total_weight for w in weights]
                
                # 基于概率选择节点
                selected_idx = np.random.choice(range(len(unassigned_nodes)), p=probs)
                selected_node = unassigned_nodes[selected_idx]
                
                group.append(selected_node)
                unassigned_nodes.remove(selected_node)
        
        # 步骤8: 组内节点排序优化
        final_groups = []
        for group in groups:
            if len(group) == num_stages:
                # 使用量子启发式算法优化组内顺序
                ordered_group = self._quantum_inspired_ordering(group)
                final_groups.append(ordered_group)
        
        return final_groups
    
    def _quantum_inspired_ordering(self, group: List[int]) -> List[int]:
        """
        使用量子启发式算法优化组内节点顺序
        
        Args:
            group: 组内节点列表
            
        Returns:
            优化后的节点顺序
        """
        if len(group) <= 2:
            return group
        
        n = len(group)
        # 创建带宽矩阵子集
        bandwidth_submatrix = np.zeros((n, n))
        for i in range(n):
            for j in range(n):
                bandwidth_submatrix[i][j] = self.topology[group[i]][group[j]]
        
        # 量子启发式算法 - 模拟量子退火过程
        # 初始解 - 随机排列
        current_solution = list(range(n))
        random.shuffle(current_solution)
        
        # 计算初始解的能量
        current_energy = self._calculate_quantum_energy(current_solution, bandwidth_submatrix)
        
        # 量子退火参数
        temp = 2.0
        cooling_rate = 0.95
        steps = 200
        
        best_solution = current_solution.copy()
        best_energy = current_energy
        
        # 量子退火过程
        for step in range(steps):
            # 量子叠加 - 生成多个候选解
            num_candidates = 5
            candidates = []
            
            for _ in range(num_candidates):
                # 生成扰动解：交换两个位置
                candidate = current_solution.copy()
                i, j = random.sample(range(n), 2)
                candidate[i], candidate[j] = candidate[j], candidate[i]
                
                # 计算能量
                energy = self._calculate_quantum_energy(candidate, bandwidth_submatrix)
                candidates.append((candidate, energy))
            
            # 量子坍缩 - 以概率选择一个候选解
            candidates.sort(key=lambda x: x[1])  # 按能量排序
            
            # 计算选择概率（能量越低，概率越高）
            energies = [c[1] for c in candidates]
            min_energy = min(energies)
            exp_energies = [np.exp(-(e - min_energy) / temp) for e in energies]
            total = sum(exp_energies)
            probs = [e / total for e in exp_energies]
            
            # 根据概率选择候选解
            selected_idx = np.random.choice(range(num_candidates), p=probs)
            new_solution, new_energy = candidates[selected_idx]
            
            # 更新当前解
            current_solution = new_solution
            current_energy = new_energy
            
            # 更新最佳解
            if current_energy < best_energy:
                best_solution = current_solution.copy()
                best_energy = current_energy
            
            # 降温
            temp *= cooling_rate
        
        # 将最佳索引解转换回原始节点ID
        return [group[i] for i in best_solution]
    
    def _calculate_quantum_energy(self, solution: List[int], bandwidth_matrix: np.ndarray) -> float:
        """
        计算量子能量函数
        
        Args:
            solution: 节点索引的排列
            bandwidth_matrix: 带宽子矩阵
            
        Returns:
            能量值（较低表示更好的顺序）
        """
        energy = 0.0
        n = len(solution)
        
        # 计算相邻节点之间的通信成本
        for i in range(n-1):
            idx_i = solution[i]
            idx_j = solution[i+1]
            
            bandwidth = bandwidth_matrix[idx_i][idx_j]
            if bandwidth > 0:
                energy += 1.0 / bandwidth  # 高带宽 = 低成本
            else:
                energy += 1000.0  # 无连接 = 高成本
        
        # 考虑非相邻节点之间的通信（权重较小）
        for i in range(n):
            for j in range(i+2, n):
                idx_i = solution[i]
                idx_j = solution[j]
                
                # 流水线中，远距离阶段通信频率降低
                stage_distance = j - i
                comm_frequency = np.exp(-0.5 * stage_distance)
                
                bandwidth = bandwidth_matrix[idx_i][idx_j]
                if bandwidth > 0:
                    energy += comm_frequency * (1.0 / bandwidth)
                else:
                    energy += comm_frequency * 1000.0
        
        return energy
    
    def evaluate_schedule(self, groups: List[List[int]]) -> Dict[str, float]:
        """
        评估调度结果的质量
        
        Args:
            groups: 分组结果
            
        Returns:
            包含各项指标的字典
        """
        results = {}
        
        # 1. 组内平均带宽（越高越好）
        intra_group_bandwidths = []
        for group in groups:
            total_bw = 0.0
            count = 0
            for i in range(len(group)):
                for j in range(i+1, len(group)):
                    total_bw += self.topology[group[i]][group[j]]
                    count += 1
            if count > 0:
                avg_bw = total_bw / count
                intra_group_bandwidths.append(avg_bw)
        
        if intra_group_bandwidths:
            results['avg_intra_group_bandwidth'] = sum(intra_group_bandwidths) / len(intra_group_bandwidths)
        else:
            results['avg_intra_group_bandwidth'] = 0.0
        
        # 2. 组间平均带宽（越低越好 - 流水线并行）
        inter_group_bandwidths = []
        for i in range(len(groups)):
            for j in range(i+1, len(groups)):
                total_bw = 0.0
                count = 0
                for node_i in groups[i]:
                    for node_j in groups[j]:
                        total_bw += self.topology[node_i][node_j]
                        count += 1
                if count > 0:
                    avg_bw = total_bw / count
                    inter_group_bandwidths.append(avg_bw)
        
        if inter_group_bandwidths:
            results['avg_inter_group_bandwidth'] = sum(inter_group_bandwidths) / len(inter_group_bandwidths)
        else:
            results['avg_inter_group_bandwidth'] = 0.0
        
        # 3. 组内/组间带宽比（越高越好）
        if results['avg_inter_group_bandwidth'] > 0:
            results['intra_inter_bandwidth_ratio'] = results['avg_intra_group_bandwidth'] / results['avg_inter_group_bandwidth']
        else:
            results['intra_inter_bandwidth_ratio'] = float('inf')
        
        # 4. 组内相邻节点带宽（流水线通信效率）
        adjacent_bandwidths = []
        for group in groups:
            for i in range(len(group) - 1):
                adjacent_bandwidths.append(self.topology[group[i]][group[i+1]])
        
        if adjacent_bandwidths:
            results['avg_adjacent_bandwidth'] = sum(adjacent_bandwidths) / len(adjacent_bandwidths)
        else:
            results['avg_adjacent_bandwidth'] = 0.0
        
        return results

