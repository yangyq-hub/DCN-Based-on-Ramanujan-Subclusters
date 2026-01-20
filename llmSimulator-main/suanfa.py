import numpy as np
from sklearn.cluster import SpectralClustering
import heapq

def read_bandwidth_matrix(filename):
    """读取带宽矩阵文件"""
    with open(filename, 'r') as f:
        matrix = [list(map(int, line.strip().split())) for line in f]
    return np.array(matrix, dtype=np.float32)

def generate_congestion_matrix(bandwidth_matrix):
    """生成随机拥塞矩阵"""
    np.random.seed(42)
    congestion = np.random.randint(0, 2, size=bandwidth_matrix.shape)
    congestion[bandwidth_matrix == 0] = 0  # 不连通的链路无拥塞
    return congestion

class GraphAnalyzer:
    def __init__(self, bandwidth, congestion):
        self.n = bandwidth.shape[0]
        self.bandwidth = bandwidth
        self.congestion = congestion
        self.graph = self._build_graph()
        
    def _build_graph(self):
        """构建邻接表"""
        graph = {i: [] for i in range(self.n)}
        for i in range(self.n):
            for j in range(self.n):
                if self.bandwidth[i,j] > 0:
                    graph[i].append(j)
        return graph
    
    def dijkstra(self, start):
        """最短路径算法（基于跳数）"""
        distances = {node: float('inf') for node in range(self.n)}
        distances[start] = 0
        predecessors = {node: None for node in range(self.n)}
        heap = [(0, start)]
        
        while heap:
            current_dist, u = heapq.heappop(heap)
            if current_dist > distances[u]:
                continue
                
            for v in self.graph[u]:
                if distances[v] > current_dist + 1:
                    distances[v] = current_dist + 1
                    predecessors[v] = u
                    heapq.heappush(heap, (distances[v], v))
        return predecessors
    
    def get_path_metrics(self, i, j):
        """获取节点间路径的带宽和拥塞指标"""
        if self.bandwidth[i,j] > 0:
            return {
                'bandwidth': self.bandwidth[i,j],
                'congestion': self.congestion[i,j]
            }
        
        # 寻找最短路径
        predecessors = self.dijkstra(i)
        path = []
        current = j
        while current is not None:
            path.append(current)
            current = predecessors[current]
        path = path[::-1]
        
        if len(path) < 2:  # 无路径
            return {'bandwidth': 0, 'congestion': 0}
        
        # 计算路径指标
        min_bandwidth = float('inf')
        total_congestion = 0
        for u, v in zip(path[:-1], path[1:]):
            min_bandwidth = min(min_bandwidth, self.bandwidth[u,v])
            total_congestion += self.congestion[u,v]
            
        return {
            'bandwidth': min_bandwidth,
            'congestion': total_congestion / (len(path)-1)  # 平均拥塞
        }

def spectral_clustering_grouping(n_groups=2):
    # 读取带宽矩阵
    B = read_bandwidth_matrix('fattree.txt')
    C = generate_congestion_matrix(B)
    
    analyzer = GraphAnalyzer(B, C)
    n = B.shape[0]
    
    # 构建权重矩阵
    W = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            metrics = analyzer.get_path_metrics(i, j)
            W[i,j] = metrics['bandwidth'] / (1 + metrics['congestion'])
    
    # 构建亲和度矩阵
    A = np.exp(W - 1)
    np.fill_diagonal(A, 0)  # 忽略自环
    
    # 谱聚类
    sc = SpectralClustering(n_clusters=n_groups, affinity='precomputed', random_state=42)
    groups = sc.fit_predict(A)
    
    # 输出分组结果
    group_dict = {}
    for node, group in enumerate(groups):
        group_dict.setdefault(group, []).append(node+1)  # 还原为1-based编号
    
    print("节点分组结果：")
    for group_id, members in group_dict.items():
        print(f"组{group_id+1}: {sorted(members)}")

if __name__ == "__main__":
    spectral_clustering_grouping(n_groups=2)