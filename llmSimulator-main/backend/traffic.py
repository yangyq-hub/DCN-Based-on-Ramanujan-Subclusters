import random
class BackgroundTrafficGenerator:
    """背景流量生成器"""
    def __init__(self, simulator, config):
        self.simulator = simulator
        self.mode = config.get("mode", "none")  # none, random, burst
        self.intensity = config.get("intensity", 0.1)  # 流量强度，0-1之间
        self.burst_interval = config.get("burst_interval", 5.0)  # 突发流量间隔时间
        self.burst_duration = config.get("burst_duration", 1.0)  # 突发流量持续时间
        self.packet_size = config.get("packet_size", 0.5)  # 背景流量包大小
        self.active = self.mode != "none"
        self.next_burst_time = 0
        self.burst_active = False
        
    def schedule_background_traffic(self, current_time):
        """根据当前模式安排背景流量"""
        if not self.active:
            return
        
        if self.mode == "random":
            self._schedule_random_traffic(current_time)
        elif self.mode == "burst":
            self._schedule_burst_traffic(current_time)
    
    def _schedule_random_traffic(self, current_time):
        """安排随机背景流量"""
        # 根据流量强度决定是否生成新的背景流量
        if random.random() < self.intensity:
            self._generate_traffic_packet(current_time)
    
    def _schedule_burst_traffic(self, current_time):
        """安排突发背景流量"""
        # 检查是否需要开始新的突发
        if not self.burst_active and current_time >= self.next_burst_time:
            self.burst_active = True
            self.next_burst_time = current_time + self.burst_interval
            
            # 安排突发结束事件
            self.simulator.schedule_event(
                current_time + self.burst_duration,
                'end_traffic_burst',
                {}
            )
            
            # 在突发期间生成大量流量
            for _ in range(int(10 * self.intensity)):  # 突发强度
                self._generate_traffic_packet(current_time)
        
        # 如果突发活跃，生成更多流量
        if self.burst_active:
            if random.random() < self.intensity * 3:  # 突发期间强度更高
                self._generate_traffic_packet(current_time)
    
    def _generate_traffic_packet(self, current_time):
        """生成一个背景流量数据包"""
        # 随机选择源节点和目标节点
        nodes = list(self.simulator.nodes.keys())
        src_node = random.choice(nodes)
        dest_node = random.choice([n for n in nodes if n != src_node])
        
        # 安排背景流量传输
        self.simulator.schedule_event(
            current_time,
            'start_transmission',
            {
                'micro_batch_id': -1,  # 使用-1表示背景流量
                'src_node': src_node,
                'dest_node': dest_node,
                'group_id': -1,  # 背景流量不属于任何组
                'size': self.packet_size,
                'direction': 'background',
                'is_background': True
            }
        )
    
    def end_burst(self):
        """结束当前突发流量"""
        self.burst_active = False