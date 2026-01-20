# run_scheduler.py
import sys
sys.path.append('/Users/bytedance/Desktop/myenv/lib/python3.13/site-packages')
import json
from schedule import QuantumInspiredTopoScheduler

def main():
    if len(sys.argv) != 5:
        print("Usage: python run_scheduler.py <topology_file> <parallel_mode> <num_stages> <num_groups>")
        sys.exit(1)
        
    topology_file = sys.argv[1]
    parallel_mode = sys.argv[2]
    num_stages = int(sys.argv[3])
    num_groups = int(sys.argv[4])
    
    # 创建调度器
    scheduler = QuantumInspiredTopoScheduler(f"topo/{topology_file}")
    
    # 进行调度
    groups = scheduler.schedule(num_stages,parallel_mode,num_groups)
    
    # 输出JSON格式的分组结果
    print(json.dumps(groups))

if __name__ == "__main__":
    main()
