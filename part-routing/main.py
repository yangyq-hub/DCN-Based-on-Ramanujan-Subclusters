#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
主程序入口，用于运行网络仿真实验
"""

import os
import numpy as np
import pandas as pd
from tqdm import tqdm

# 导入拓扑模块
from topology.ramanujan import RamanujanTopology
from topology.fat_tree import FatTreeTopology
from topology.jellyfish import JellyfishTopology
from topology.ocs import OCSReconfigurableTopology


# 导入路由模块
from routing.shortest_path import ShortestPathRouting
from routing.ecmp import ECMPRouting
from routing.valiant import ValiantRouting
from routing.spectral import SpectralGapRouting
# 导入流量模块
from traffic.uniform import UniformTraffic
from traffic.hotspot import HotspotTraffic
from traffic.all_reduce import AllReduceTraffic
from traffic.cross import CrossClusterHotspotTraffic

# 导入仿真器
from simulator.simulator import NetworkSimulator

# 导入可视化模块
from visualization.plot import plot_comparison

def run_experiment(experiment_name, topologies, routing_strategies, traffic_pattern,simulation_time=1000, packet_rate=0.1, packet_size=1024,dynamic_topology=False, reconfig_interval=10.0,reconfig_delay=0.1 ) :    # 重构延迟100毫秒:
    """运行单个实验，支持多种路由算法对比"""
    results = []
    
    for topo_name, topo in topologies.items():
        for routing_name, routing_strategy in routing_strategies.items():
            print(f"\n运行实验: {experiment_name} - {topo_name} - {routing_name}")
            
            # 创建仿真器实例
        #     simulator = NetworkSimulator(topo, routing_strategy(topo), 
        #                                 traffic_pattern(topo, packet_rate, packet_size),dynamic_topology=dynamic_topology,  # 启用动态拓扑
        # reconfig_interval=reconfig_interval, # 10秒重构一次
        # reconfig_delay=reconfig_delay )     # 重构延迟100毫秒)

            simulator = NetworkSimulator(topo, routing_strategy(topo), 
                                        traffic_pattern(topo, packet_rate, packet_size),dynamic_topology=False,  # 启用动态拓扑
        reconfig_interval=reconfig_interval, # 10秒重构一次
        reconfig_delay=reconfig_delay )     # 重构延迟100毫秒)
            
            # 运行仿真
            metrics = simulator.run(simulation_time)
            
            # 保存结果p
            metrics['topology'] = topo_name
            metrics['routing'] = routing_name
            metrics['scale'] = experiment_name
            results.append(metrics)

            
            print(f"完成: {topo_name} - {routing_name} - 平均延迟: {metrics['avg_delay']:.3f}ms, "
                  f"吞吐量: {metrics['throughput']:.3f}Gbps")
    
    return pd.DataFrame(results)

def main():
    # 确保输出目录存在
    os.makedirs("results", exist_ok=True)
    
    # 定义实验规模
    scales = {
        'k=4': {'nodes': 20, 'degree': 4, 'k': 4},
        # 'k=8': {'nodes': 80, 'degree': 7, 'k': 8},
        # 'k=12': {'nodes': 180, 'degree': 10, 'k': 12},
        # 'k=16': {'nodes': 320, 'degree': 13, 'k': 16},
        # 'k=20': {'nodes': 500, 'degree': 16, 'k':20},
        # 'k=24': {'nodes': 720, 'degree': 19, 'k':24},
        # 'k=28': {'nodes': 980, 'degree': 22, 'k':28},
    }
    
    # 定义路由策略
    routing_strategies = {
        'ShortestPath': ShortestPathRouting,
        # 'ECMP': ECMPRouting,
        # 'Spectral': SpectralGapRouting,
    }
    
    # 存储所有实验结果
    all_results = []
    
    # 遍历不同规模
    for scale_name, params in scales.items():
        print(f"\n=== 生成{scale_name}规模拓扑 ===")
        
        # 创建不同拓扑
        topologies = {
            'Ramanujan': RamanujanTopology(
                n=params['nodes'], 
                d=params['degree'],
                iterations=3000
            ),
            'Fat-Tree': FatTreeTopology(k=params['k']),
            'Jellyfish': JellyfishTopology(
                n=params['nodes'], 
                k=params['degree']+1, 
                r=params['degree'] 
            ),
            # 'OCS':OCSReconfigurableTopology(
            #     n_tor=128,           # 每个ToR 128个节点
            #     d_tor=6,             # 每个节点度数为6
            #     n_ocs_links=128,     # 128个OCS链路
            #     ocs_reconfiguration_interval=1.0,  # 10秒重构一次
            #     ocs_reconfiguration_delay=0.1       # 重构延迟100毫秒
            # )
        }
        
        # 实验: 热点流量 + 多种路由算法对比
        results = run_experiment(
            f"{scale_name}",
            topologies,
            routing_strategies,  # 使用多个路由算法
            # CrossClusterHotspotTraffic,
            HotspotTraffic,
            # AllReduceTraffic,
            # UniformTraffic,
            simulation_time=20000,
            packet_rate=0.1,
            packet_size=10240,
            dynamic_topology=False,  # 启用动态拓扑
            reconfig_interval=1.0, # 1秒重构一次
            reconfig_delay=0.1      # 重构延迟100毫秒
        )
        all_results.append(results)
    
    # 合并所有结果
    all_df = pd.concat(all_results)
    
    # 保存结果到CSV
    all_df.to_csv("results_new/simulation_results_test.csv", index=False)
    
    # 绘制比较图表
    plot_comparison(all_df)
    
    print("\n所有实验完成! 结果已保存到 results/ 目录")

if __name__ == "__main__":
    main()
