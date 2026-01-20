import heapq
import random
import sys

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
    def __lt__(self, other):
        return self.time < other.time

    def __init__(self, time, event_type, data):
        self.time = time
        self.event_type = event_type
        self.data = data

class Link:
    def __init__(self, src, dest, bandwidth):
        self.src = src
        self.dest = dest
        self.bandwidth = bandwidth
        self.queue = []
        self.current_transmission = None

class Packet:
    def __init__(self, src, final_dest, size, gen_time, group_id, step_index, batch_id):
        self.src = src
        self.final_dest = final_dest
        self.size = size
        self.gen_time = gen_time
        self.start_time = None
        self.end_time = None
        self.group_id = group_id
        self.step_index = step_index
        self.batch_id = batch_id

def read_adjacency_matrix(filename):
    matrix = []
    with open(filename, 'r') as f:
        for line in f:
            row = list(map(int, line.strip().split()))
            matrix.append(row)
    return matrix

def read_traffic_config(filename):
    with open(filename, 'r') as f:
        lines = [l.strip() for l in f.readlines() if l.strip()]
    
    if not lines:
        return 1, 0.0, 1, []
    
    first_line = lines[0].split()
    packet_size = int(first_line[0])
    compute_time = float(first_line[1]) if len(first_line) > 1 else 0.0
    mini_batch_count = int(first_line[2]) if len(first_line) > 2 else 1
    
    groups = []
    for line in lines[1:]:
        nodes = list(map(int, line.split()))
        groups.append([n-1 for n in nodes])
    
    return packet_size, compute_time, mini_batch_count, groups

def dijkstra(graph, start_node):
    distances = {node: float('infinity') for node in graph}
    distances[start_node] = 0
    predecessors = {node: None for node in graph}
    priority_queue = [(0, start_node)]
    
    while priority_queue:
        current_distance, current_node = heapq.heappop(priority_queue)
        if current_distance > distances[current_node]:
            continue
            
        for neighbor in graph[current_node]:
            distance = current_distance + 1
            if distance < distances[neighbor]:
                distances[neighbor] = distance
                predecessors[neighbor] = current_node
                heapq.heappush(priority_queue, (distance, neighbor))
    
    next_hop = {}
    for node in graph:
        if node == start_node:
            next_hop[node] = None
            continue
            
        current = node
        while predecessors[current] != start_node and predecessors[current] is not None:
            current = predecessors[current]
        
        next_hop[node] = current if predecessors[current] is not None else None
    
    return next_hop

def main():
    # 设置日志输出
    original_stdout = sys.stdout
    log_file = open('results.txt', 'w')
    sys.stdout = Tee(original_stdout, log_file)
    
    try:
        adj_matrix = read_adjacency_matrix('fattree.txt')
        num_nodes = len(adj_matrix)
        
        graph = {node: [] for node in range(num_nodes)}
        links = {}
        for i in range(num_nodes):
            for j in range(num_nodes):
                bandwidth = adj_matrix[i][j]
                if bandwidth > 0:
                    graph[i].append(j)
                    links[(i, j)] = Link(i, j, bandwidth)

        routing_tables = {}
        for node in range(num_nodes):
            routing_tables[node] = dijkstra(graph, node)

        packet_size, compute_time, mini_batch_count, traffic_groups = read_traffic_config('liuliang.txt')
        print(f"全局配置 | 包大小: {packet_size}MB | 计算时间: {compute_time}s | Mini-batch数: {mini_batch_count}")

        groups_info = []
        for group in traffic_groups:
            steps = []
            for i in range(len(group)-1):
                steps.append((group[i], group[i+1]))
            for i in range(len(group)-1, 0, -1):
                steps.append((group[i], group[i-1]))
            groups_info.append({'steps': steps})

        event_heap = []
        
        # 初始化第一个mini-batch
        for group_id, group_info in enumerate(groups_info):
            if not group_info['steps']:
                continue
            first_src, first_dest = group_info['steps'][0]
            heapq.heappush(event_heap, Event(0.0, 'group_step', {
                'group_id': group_id,
                'step_index': 0,
                'src': first_src,
                'final_dest': first_dest,
                'size': packet_size,
                'compute_time': compute_time,
                'batch_id': 0
            }))

        total_simulation_time = 0.0
        batch_status = {}

        while event_heap:
            event = heapq.heappop(event_heap)
            total_simulation_time = event.time

            if event.event_type == 'group_step':
                data = event.data
                current_time = event.time
                group_id = data['group_id']
                step_index = data['step_index']
                src = data['src']
                final_dest = data['final_dest']
                size = data['size']
                compute_time = data['compute_time']
                batch_id = data['batch_id']

                adjusted_size = size * random.uniform(0.7, 1.3)
                adjusted_size = round(adjusted_size, 2)

                next_hop = routing_tables[src][final_dest]
                if next_hop is None:
                    print(f"[{current_time:.2f}s] 组 {group_id} 步骤 {step_index} 批 {batch_id} 路由失败: {src}->{final_dest}")
                    continue

                if (src, next_hop) not in links:
                    print(f"[{current_time:.2f}s] 组 {group_id} 步骤 {step_index} 批 {batch_id} 链路 {src}->{next_hop} 不存在")
                    continue

                packet = Packet(src, final_dest, adjusted_size, current_time, group_id, step_index, batch_id)
                link = links[(src, next_hop)]

                print(f"[{current_time:.2f}s] 组 {group_id} 步骤 {step_index} 批 {batch_id}: "
                      f"{src}->{next_hop} (目标 {final_dest}) 发送 {adjusted_size}MB")

                link.queue.append(packet)
                print(f"[{current_time:.2f}s] 链路 {src}->{next_hop} 队列长度: {len(link.queue)}")

                if link.current_transmission is None:
                    transmission_time = adjusted_size / link.bandwidth
                    end_time = current_time + transmission_time
                    packet.start_time = current_time
                    packet.end_time = end_time
                    link.current_transmission = packet
                    
                    heapq.heappush(event_heap, Event(end_time, 'transmit_complete', {
                        'link': (src, next_hop),
                        'packet': packet,
                        'is_group': True,
                        'current_node': next_hop,
                        'compute_time': compute_time
                    }))
                    print(f"[{current_time:.2f}s] 传输开始 (带宽 {link.bandwidth}Mbps)")

                # 安排计算事件
                if step_index == 0 and src == groups_info[group_id]['steps'][0][0]:
                    compute_end_time = current_time + compute_time
                    heapq.heappush(event_heap, Event(compute_end_time, 'compute_complete_batch', {
                        'group_id': group_id,
                        'current_batch': batch_id,
                        'src': src,
                        'final_dest': final_dest
                    }))
                    print(f"[{current_time:.2f}s] 节点 {src} 开始计算批次 {batch_id}，预计完成时间 {compute_end_time:.2f}s")

            elif event.event_type == 'transmit_complete':
                data = event.data
                current_time = event.time
                link_key = data['link']
                packet = data['packet']
                current_node = data['current_node']
                compute_time = data['compute_time']
                link = links[link_key]

                print(f"[{current_time:.2f}s] 传输完成: {link_key[0]}->{link_key[1]} ({packet.size}MB) 批 {packet.batch_id}")
                link.current_transmission = None

                if link.queue:
                    next_packet = link.queue.pop(0)
                    transmission_time = next_packet.size / link.bandwidth
                    end_time = current_time + transmission_time
                    next_packet.start_time = current_time
                    next_packet.end_time = end_time
                    link.current_transmission = next_packet
                    
                    heapq.heappush(event_heap, Event(end_time, 'transmit_complete', {
                        'link': link_key,
                        'packet': next_packet,
                        'is_group': False,
                        'current_node': link_key[1],
                        'compute_time': compute_time
                    }))
                    print(f"[{current_time:.2f}s] 链路 {link_key} 继续传输队列 (预计 {end_time:.2f}s)")

                if data.get('is_group', False):
                    if current_node == packet.final_dest:
                        print(f"✓ [{current_time:.2f}s] 组 {packet.group_id} 步骤 {packet.step_index} 批 {packet.batch_id} 完成")
                        group_info = groups_info[packet.group_id]
                        next_step = packet.step_index + 1
                        if next_step < len(group_info['steps']):
                            next_src, next_dest = group_info['steps'][next_step]
                            heapq.heappush(event_heap, Event(current_time, 'group_step', {
                                'group_id': packet.group_id,
                                'step_index': next_step,
                                'src': next_src,
                                'final_dest': next_dest,
                                'size': packet_size,
                                'compute_time': compute_time,
                                'batch_id': packet.batch_id
                            }))
                            print(f"→ [{current_time:.2f}s] 组 {packet.group_id} 批 {packet.batch_id} 进入步骤 {next_step}: {next_src}→{next_dest}")
                    else:
                        compute_end_time = current_time + compute_time
                        heapq.heappush(event_heap, Event(compute_end_time, 'compute_complete', {
                            'packet': packet,
                            'current_node': current_node,
                            'final_dest': packet.final_dest,
                            'group_id': packet.group_id,
                            'step_index': packet.step_index,
                            'compute_time': compute_time
                        }))
                        print(f"[{current_time:.2f}s] 节点 {current_node} 开始计算批 {packet.batch_id}，预计完成时间 {compute_end_time:.2f}s")

            elif event.event_type == 'compute_complete_batch':
                data = event.data
                current_time = event.time
                group_id = data['group_id']
                current_batch = data['current_batch']
                src = data['src']
                final_dest = data['final_dest']

                next_batch = current_batch + 1
                if next_batch < mini_batch_count:
                    heapq.heappush(event_heap, Event(current_time, 'group_step', {
                        'group_id': group_id,
                        'step_index': 0,
                        'src': src,
                        'final_dest': final_dest,
                        'size': packet_size,
                        'compute_time': compute_time,
                        'batch_id': next_batch
                    }))
                    print(f"[{current_time:.2f}s] 组 {group_id} 批 {current_batch} 计算完成，安排批 {next_batch} 的发送")

            elif event.event_type == 'compute_complete':
                data = event.data
                current_time = event.time
                packet = data['packet']
                current_node = data['current_node']
                final_dest = data['final_dest']
                compute_time = data['compute_time']

                print(f"[{current_time:.2f}s] 节点 {current_node} 完成批 {packet.batch_id} 的计算，开始转发")

                next_hop = routing_tables[current_node][final_dest]
                if next_hop is None:
                    print(f"✗ [{current_time:.2f}s] 路由失败: {current_node}->{final_dest}")
                    continue
                
                if (current_node, next_hop) not in links:
                    print(f"✗ [{current_time:.2f}s] 链路不存在: {current_node}->{next_hop}")
                    continue

                new_link = links[(current_node, next_hop)]
                print(f"↪ [{current_time:.2f}s] 节点 {current_node} 转发批 {packet.batch_id} 到 {next_hop}")

                new_link.queue.append(packet)
                if new_link.current_transmission is None:
                    transmission_time = packet.size / new_link.bandwidth
                    end_time = current_time + transmission_time
                    packet.start_time = current_time
                    packet.end_time = end_time
                    new_link.current_transmission = packet
                    
                    heapq.heappush(event_heap, Event(end_time, 'transmit_complete', {
                        'link': (current_node, next_hop),
                        'packet': packet,
                        'is_group': True,
                        'current_node': next_hop,
                        'compute_time': compute_time
                    }))
                    print(f"[{current_time:.2f}s] 转发开始 (带宽 {new_link.bandwidth}Mbps)")

        print(f"\n总仿真时间: {total_simulation_time:.2f} 秒")

    finally:
        # 恢复标准输出并关闭文件
        sys.stdout = original_stdout
        log_file.close()

if __name__ == "__main__":
    main()