import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from collections import Counter
import matplotlib.dates as mdates
from datetime import datetime, timedelta

def parse_packet_log(file_path):
    """Parse packet log file"""
    pattern = r"Packet ([0-9a-f-]+) delivered at ([0-9.]+), total delay:([0-9.]+)"
    packets = []
    
    with open(file_path, 'r') as f:
        for line in f:
            match = re.match(pattern, line.strip())
            if match:
                packet_id = match.group(1)
                delivery_time = float(match.group(2))
                delay = float(match.group(3))
                start_time = delivery_time - delay
                
                packets.append({
                    'packet_id': packet_id,
                    'delivery_time': delivery_time,
                    'delay': delay,
                    'start_time': start_time
                })
    
    return pd.DataFrame(packets)

def analyze_packets(df):
    """Analyze packet data and generate charts"""
    # 过滤数据，只保留前20000ms的数据
    df_filtered = df[df['delivery_time'] <= 20000].copy()  # 使用copy()避免SettingWithCopyWarning
    
    # 如果过滤后没有数据，则使用原始数据
    if len(df_filtered) == 0:
        print("Warning: No data found within the first 20000ms. Using all available data.")
        df_filtered = df.copy()
    
    # Set chart style
    sns.set(style="whitegrid")
    
    # 定义拓扑重构和流量刷新的时间点
    topology_reconfig_times = np.arange(1000, 20001, 1000)
    traffic_refresh_times = np.arange(7000, 20001, 7000)
    
    # Use English titles to avoid font issues
    plt.figure(figsize=(15, 18))
    
    # 1. Delay distribution histogram
    plt.subplot(3, 1, 1)
    sns.histplot(df_filtered['delay'], kde=True, bins=20)
    plt.title('Packet Delay Distribution ', fontsize=18)
    plt.xlabel('Delay (ms)', fontsize=16)
    plt.ylabel('Count', fontsize=16)
    
    # 2. Raw delay trend over time (scatter plot)
    plt.subplot(3, 1, 2)
    plt.scatter(df_filtered['delivery_time'], df_filtered['delay'], alpha=0.6, label='Individual Packets')
    plt.title('Raw Delay Trend Over Time ', fontsize=18)
    plt.xlabel('Delivery Time (ms)', fontsize=16)
    plt.ylabel('Delay (ms)', fontsize=16)
    plt.xlim(0, 20000)  # 设置x轴范围为0-20000ms
    
    # 添加拓扑重构和流量刷新的垂直线
    for t in topology_reconfig_times:
        plt.axvline(x=t, color='r', linestyle='--', alpha=0.7, linewidth=1)
    
    for t in traffic_refresh_times:
        plt.axvline(x=t, color='g', linestyle='-', alpha=0.7, linewidth=2)
    
    # 添加图例
    plt.plot([], [], 'r--', label='Topology Reconfiguration (every 1000ms)')
    # plt.plot([], [], 'g-', label='Traffic Refresh (every 3000ms)')
    
    plt.legend()
    plt.grid(True)
    
    # 3. Time-binned average delay trend (more intuitive visualization)
    plt.subplot(3, 1, 3)
    
    # 固定bin大小为100ms
    bin_size = 100
    
    # 创建从0到20000ms的时间窗口
    time_bins = np.arange(0, 20000 + bin_size, bin_size)
    
    # Group data by time bins and calculate average delay
    # 使用pd.cut创建分类变量
    df_filtered['time_bin'] = pd.cut(df_filtered['delivery_time'], bins=time_bins, right=False)
    
    # 使用observed=True来避免FutureWarning
    avg_delays = df_filtered.groupby('time_bin', observed=True)['delay'].mean().reset_index()
    
    # Convert the interval index to numeric values for plotting
    avg_delays['time_bin_center'] = avg_delays['time_bin'].apply(lambda x: x.mid)
    
    # Plot the average delay per time bin
    plt.bar(avg_delays['time_bin_center'], avg_delays['delay'], 
            width=bin_size*0.8, alpha=0.7, color='skyblue')
    
    # Add a trend line
    plt.plot(avg_delays['time_bin_center'], avg_delays['delay'], 'ro-', 
             linewidth=2, markersize=6, label='Average Delay Trend')
    
    # 添加拓扑重构和流量刷新的垂直线
    for t in topology_reconfig_times:
        plt.axvline(x=t, color='r', linestyle='--', alpha=0.7, linewidth=1)
    
    for t in traffic_refresh_times:
        plt.axvline(x=t, color='g', linestyle='-', alpha=0.7, linewidth=2)
    
    # 添加图例
    plt.plot([], [], 'r--', label='Topology Reconfiguration (every 1000ms)')
    # plt.plot([], [], 'g-', label='Traffic Refresh (every 3000ms)')

    plt.title('Average Delay by Time Window ', fontsize=18)
    plt.xlabel('Time (ms)', fontsize=16)
    plt.ylabel('Average Delay (ms)', fontsize=16)
    plt.xlim(0, 20000)  # 设置x轴范围为0-20000ms
    plt.legend()
    plt.grid(True)
    
    plt.tight_layout()
    plt.savefig('packet_analysis.png', dpi=300)
    
    # 4. Create a separate figure for detailed time-series analysis
    plt.figure(figsize=(15, 8))
    
    # Sort data by delivery time
    df_sorted = df_filtered.sort_values('delivery_time')
    
    # Plot the data
    plt.scatter(df_sorted['delivery_time'], df_sorted['delay'], 
                alpha=0.4, label='Individual Packets', color='gray')
    
    # 添加拓扑重构和流量刷新的垂直线
    for t in topology_reconfig_times:
        plt.axvline(x=t, color='r', linestyle='--', alpha=0.7, 
                   label='Topology Reconfiguration' if t == topology_reconfig_times[0] else "")
    
    for t in traffic_refresh_times:
        plt.axvline(x=t, color='g', linestyle='-', alpha=0.7, linewidth=2,
                   label='Traffic Refresh' if t == traffic_refresh_times[0] else "")
    
    # 计算每个时间窗口的平均延迟
    window_size = 200  # 200ms窗口
    windows = np.arange(0, 20000, window_size)
    avg_delays_detailed = []
    
    for start in windows:
        end = start + window_size
        window_data = df_filtered[(df_filtered['delivery_time'] >= start) & 
                                 (df_filtered['delivery_time'] < end)]
        if len(window_data) > 0:
            avg_delays_detailed.append((start + window_size/2, window_data['delay'].mean()))
    
    if avg_delays_detailed:
        x_vals, y_vals = zip(*avg_delays_detailed)
        plt.plot(x_vals, y_vals, 'b-', linewidth=2, label='Moving Average (200ms window)')
    
    plt.title('Delay Trend Analysis with Topology and Traffic Events ', fontsize=20)
    plt.xlabel('Time (ms)', fontsize=18)
    plt.ylabel('Delay (ms)', fontsize=18)
    plt.xlim(0, 20000)  # 设置x轴范围为0-20000ms
    plt.grid(True)
    
    # Add horizontal line for overall average
    plt.axhline(y=df_filtered['delay'].mean(), color='purple', linestyle='--', 
                label=f'Overall Average: {df_filtered["delay"].mean():.2f}ms')
    
    # 添加文本标注，解释重构和刷新的影响
    plt.figtext(0.5, 0.01, 
               "Red dashed lines: Topology reconfiguration events (every 1000ms)\n"
               "Green solid lines: Traffic refresh events (every 3000ms)", 
               ha="center", fontsize=14, bbox={"facecolor":"white", "alpha":0.8, "pad":5})
    
    plt.legend(fontsize=12, loc='upper left')
    plt.tight_layout(rect=[0, 0.03, 1, 0.97])  # 为底部文本留出空间
    plt.savefig('delay_trend_analysis.png', dpi=300)
    
    # 5. 创建一个额外的图表，专门分析拓扑重构和流量刷新对延迟的影响
    plt.figure(figsize=(15, 10))
    
    # 5.1 分析拓扑重构前后的延迟变化
    plt.subplot(2, 1, 1)
    
    # 定义重构前后的时间窗口（例如，重构前100ms和重构后100ms）
    window_size = 100
    before_reconfig_delays = []
    after_reconfig_delays = []
    valid_reconfig_times = []
    
    for t in topology_reconfig_times:
        # 重构前的数据
        before_data = df_filtered[(df_filtered['delivery_time'] >= t - window_size) & 
                                 (df_filtered['delivery_time'] < t)]
        # 重构后的数据
        after_data = df_filtered[(df_filtered['delivery_time'] >= t) & 
                               (df_filtered['delivery_time'] < t + window_size)]
        
        # 只有当前后都有数据时才添加到列表
        if len(before_data) > 0 and len(after_data) > 0:
            before_reconfig_delays.append(before_data['delay'].mean())
            after_reconfig_delays.append(after_data['delay'].mean())
            valid_reconfig_times.append(t)
    
    # 确保数组长度一致
    if before_reconfig_delays and after_reconfig_delays:
        x = np.arange(len(before_reconfig_delays))
        width = 0.35
        
        plt.bar(x - width/2, before_reconfig_delays, width, label='Before Reconfiguration')
        plt.bar(x + width/2, after_reconfig_delays, width, label='After Reconfiguration')
        
        plt.xlabel('Reconfiguration Event', fontsize=14)
        plt.ylabel('Average Delay (ms)', fontsize=14)
        plt.title('Delay Before and After Topology Reconfiguration', fontsize=16)
        plt.xticks(x, [f'{t}ms' for t in valid_reconfig_times])
        plt.legend()
    else:
        plt.text(0.5, 0.5, 'Insufficient data for analysis', 
                 horizontalalignment='center', verticalalignment='center',
                 transform=plt.gca().transAxes, fontsize=14)
    
    # 5.2 分析流量刷新前后的延迟变化
    plt.subplot(2, 1, 2)
    
    before_refresh_delays = []
    after_refresh_delays = []
    valid_refresh_times = []
    
    for t in traffic_refresh_times:
        # 刷新前的数据
        before_data = df_filtered[(df_filtered['delivery_time'] >= t - window_size) & 
                                 (df_filtered['delivery_time'] < t)]
        # 刷新后的数据
        after_data = df_filtered[(df_filtered['delivery_time'] >= t) & 
                               (df_filtered['delivery_time'] < t + window_size)]
        
        # 只有当前后都有数据时才添加到列表
        if len(before_data) > 0 and len(after_data) > 0:
            before_refresh_delays.append(before_data['delay'].mean())
            after_refresh_delays.append(after_data['delay'].mean())
            valid_refresh_times.append(t)
    
    # 绘制刷新前后的延迟对比
    if before_refresh_delays and after_refresh_delays:
        x = np.arange(len(before_refresh_delays))
        width = 0.35
        
        plt.bar(x - width/2, before_refresh_delays, width, label='Before Traffic Refresh')
        plt.bar(x + width/2, after_refresh_delays, width, label='After Traffic Refresh')
        
        plt.xlabel('Traffic Refresh Event', fontsize=14)
        plt.ylabel('Average Delay (ms)', fontsize=14)
        plt.title('Delay Before and After Traffic Refresh', fontsize=16)
        plt.xticks(x, [f'{t}ms' for t in valid_refresh_times])
        plt.legend()
    else:
        plt.text(0.5, 0.5, 'Insufficient data for analysis', 
                 horizontalalignment='center', verticalalignment='center',
                 transform=plt.gca().transAxes, fontsize=14)
    
    plt.tight_layout()
    plt.savefig('event_impact_analysis.png', dpi=300)
    
    # Print statistics summary (使用过滤后的数据)
    print("Packet Delay Statistics Summary :")
    print(f"Total packets: {len(df_filtered)}")
    print(f"Average delay: {df_filtered['delay'].mean():.4f} ms")
    print(f"Minimum delay: {df_filtered['delay'].min():.4f} ms")
    print(f"Maximum delay: {df_filtered['delay'].max():.4f} ms")
    print(f"Median delay: {df_filtered['delay'].median():.4f} ms")
    print(f"Delay standard deviation: {df_filtered['delay'].std():.4f} ms")
    
    # Calculate and print additional metrics
    print("\nAdditional Metrics:")
    print(f"95th percentile delay: {df_filtered['delay'].quantile(0.95):.4f} ms")
    print(f"99th percentile delay: {df_filtered['delay'].quantile(0.99):.4f} ms")
    
    # Calculate jitter (variation in delay)
    if len(df_filtered) > 1:
        df_sorted = df_filtered.sort_values('start_time')
        df_sorted['delay_diff'] = df_sorted['delay'].diff().abs()
        avg_jitter = df_sorted['delay_diff'].mean()
        print(f"Average jitter: {avg_jitter:.4f} ms")
    
    # 分析拓扑重构和流量刷新对延迟的影响
    print("\nImpact Analysis:")
    
    # 拓扑重构影响
    if before_reconfig_delays and after_reconfig_delays:
        avg_before_reconfig = np.mean(before_reconfig_delays)
        avg_after_reconfig = np.mean(after_reconfig_delays)
        change_pct = ((avg_after_reconfig - avg_before_reconfig) / avg_before_reconfig) * 100
        
        print(f"Topology Reconfiguration Impact:")
        print(f"  Average delay before reconfiguration: {avg_before_reconfig:.4f} ms")
        print(f"  Average delay after reconfiguration: {avg_after_reconfig:.4f} ms")
        print(f"  Change: {change_pct:.2f}%")
    
    # 流量刷新影响
    if before_refresh_delays and after_refresh_delays:
        avg_before_refresh = np.mean(before_refresh_delays)
        avg_after_refresh = np.mean(after_refresh_delays)
        change_pct = ((avg_after_refresh - avg_before_refresh) / avg_before_refresh) * 100
        
        print(f"Traffic Refresh Impact:")
        print(f"  Average delay before traffic refresh: {avg_before_refresh:.4f} ms")
        print(f"  Average delay after traffic refresh: {avg_after_refresh:.4f} ms")
        print(f"  Change: {change_pct:.2f}%")
    
    return

def main():
    # Parse and analyze data
    log_file = "packet_delivery.log"
    df = parse_packet_log(log_file)
    analyze_packets(df)
    
    print(f"Analysis complete! Charts saved as packet_analysis.png, delay_trend_analysis.png, and event_impact_analysis.png")

if __name__ == "__main__":
    main()
