<template src="./App.html"></template>
<script>
import * as d3 from 'd3';

export default {
  name: 'SimulationVisualization',
  data() {
    return {
      showConfig: true,
      simulationRunning: false,
      loading: false,
      error: null,
      simulationData: null,
      rawLogData: null, // 存储原始日志数据
      currentTopologyFile: null, // 存储当前选择的拓扑文件

      // 配置相关
      availableTopologies: [],
      showNodePowerConfig: false,
      showGroupConfig: false,
      showModelStructureConfig: true,

      config: {
        topology_file: 'ring.yaml',
        parallel_mode: 'hybrid',
        scheduling_mode:'random',
        num_batches: 2,
        total_params: 1000,  // 百万参数
        batch_size: 32,
        micro_batch_count: 32,
        precision: 'fp16',
        activation_checkpointing: false,
        sparsity_ratio: 0,
        data_parallel_size: 16,
        parameter_sync_frequency: 1,
        random_seed: 42,
        compute_times: [1, 1, 1, 1,1, 1, 1, 1],  // 流水线各阶段计算时间
        node_compute_power: {
          0: 1.0,
          1: 1.0,
          2: 1.0,
          3: 1.0
        },
        packet_size: 1.0,
        num_gradient_chunks: 4,
        network: {
          routing_algorithm: 'dijkstra',
          congestion_model: 'fair_share',
          default_bandwidth: 10,
          default_latency: 0.1,
          default_jitter: 0.01,
          default_packet_loss: 0.0001,
          retransmission_timeout: 100,
          max_retransmissions: 3
        },
        model_config: {
          hidden_size: 10240,
          num_layers: 96,
          num_attention_heads: 16,
          seq_length: 1024,
          vocab_size: 50000,
          mlp_ratio: 4
        },
        background_traffic: {
          mode: 'none',
          intensity: 0.2,
          packet_size: 0.5,
          burst_interval: 5.0,
          burst_duration: 1.0
        },
        parameterCommunicationVolume: 0,
        groups: [
          [0, 1, 2, 3]  // 默认一个数据并行组
        ]
      },

      // 可视化相关
      currentTime: 0,
      maxTime: 100,
      isPlaying: false,
      playbackSpeed: 1.0,
      playbackInterval: null,
      progressPercentage: 0,
      selectedGroup: 'all',
      selectedBatch: 'all',
      selectedEventType: 'all',
      showRingEvents: true,
      showStatsEvents: true,

      forwardColor: '#3498db',  // 前向传播颜色
      backwardColor: '#e74c3c', // 反向传播颜色
      ringColor: '#9b59b6',     // Ring通信颜色
      packetLossColor: '#f39c12', // 丢包颜色
      groupColors: {},          // 组颜色映射

      // 统计数据
      simulationStats: {},
      batchColors: {},
      availableGroups: [],
      availableBatches: [],
      activeNodeCount: 0,
      totalNodeCount: 0,
      computeNodeCount: 0,
      nodeUtilization: 0,
      activeLinkCount: 0,
      totalLinkCount: 0,
      congestedLinkCount: 0,
      linkUtilization: 0,
      completedBatchCount: 0,
      groupCount: 0,
      stageCount: 0,
      totalCommunicationVolume: 0,
      forwardCommunicationVolume: 0,
      backwardCommunicationVolume: 0,
      parameterCommunicationVolume: 0,
      averageThroughput: 0,
      averageIterationTime: 0,
      communicationComputeRatio: 0,
      backgroundPacketsCount: 0,

      // 路由统计数据
      averagePathLength: 0,
      pathDiversity: 0,
      routingCalculations: 0,
      loadBalanceScore: 0,

      // 存储节点和链路状态
      nodeStateMap: {},
      linkStateMap: {},
      packetElements: [],

      // 拓扑数据
      topologyData: null,

      // 解析后的事件数据
      parsedEvents: {
        forward: [],
        backward: [],
        ring: [],
        stats: []
      }
    };
  },

  computed: {
    filteredEvents() {
      if (!this.parsedEvents) {
        return [];
      }

      // 合并所有事件类型
      let allEvents = [];

      // 检查并添加各类事件
      if (Array.isArray(this.parsedEvents.forward)) {
        allEvents = allEvents.concat(this.parsedEvents.forward);
      }

      if (Array.isArray(this.parsedEvents.backward)) {
        allEvents = allEvents.concat(this.parsedEvents.backward);
      }

      if (Array.isArray(this.parsedEvents.ring) && this.showRingEvents) {
        allEvents = allEvents.concat(this.parsedEvents.ring);
      }

      if (Array.isArray(this.parsedEvents.stats) && this.showStatsEvents) {
        allEvents = allEvents.concat(this.parsedEvents.stats);
      }

      // 首先按时间戳筛选
      let events = allEvents.filter(event =>
        event.timestamp <= this.currentTime
      );

      // 按组筛选
      if (this.selectedGroup !== 'all') {
        events = events.filter(event =>
          event.group === parseInt(this.selectedGroup) ||
          event.group_id === parseInt(this.selectedGroup) ||
          event.group === undefined
        );
      }

      // 按批次筛选
      if (this.selectedBatch !== 'all') {
        events = events.filter(event =>
          event.batch === parseInt(this.selectedBatch) ||
          event.batch_id === parseInt(this.selectedBatch) ||
          event.batch === undefined
        );
      }

      // 按事件类型筛选
      if (this.selectedEventType !== 'all') {
        events = events.filter(event => {
          if (this.selectedEventType === 'forward') {
            return event.type?.includes('forward') || event.eventType?.includes('forward');
          } else if (this.selectedEventType === 'backward') {
            return event.type?.includes('backward') || event.eventType?.includes('backward');
          } else if (this.selectedEventType === 'transmission') {
            return event.type?.includes('transmission') || event.eventType?.includes('transfer');
          } else if (this.selectedEventType === 'parameter') {
            return event.type?.includes('parameter') || event.eventType?.includes('parameter');
          } else if (this.selectedEventType === 'gradient') {
            return event.type?.includes('gradient') || event.eventType?.includes('gradient') ||
              event.ringType !== undefined;
          }
          return true;
        });
      }

      // 按时间戳降序排序，使最新事件显示在前面
      events.sort((a, b) => b.timestamp - a.timestamp);

      // 最多显示最近的100个事件
      return events.slice(0, 100);
    }
  },

  mounted() {
    this.fetchAvailableTopologies();
  },

  beforeUnmount() {
    // 清理动画帧
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }

    // 清理D3事件监听器
    if (this.simulation) {
      this.simulation.stop();
    }
  },

  methods: {
    toggleModelStructureConfig() {
      this.showModelStructureConfig = !this.showModelStructureConfig;
    },
    getRoutingAlgorithmName() {
      const algorithm = this.config.network.routing_algorithm;
      switch (algorithm) {
        case 'dijkstra': return 'Dijkstra最短路径';
        case 'ecmp': return 'ECMP等价多路径';
        default: return algorithm;
      }
    },

    // 获取ECMP策略名称
    getEcmpStrategyName() {
      const strategy = this.config.network.ecmp_strategy;
      switch (strategy) {
        case 'hash_based': return '基于哈希';
        case 'round_robin': return '轮询';
        case 'weighted': return '加权选择';
        case 'least_congested': return '最小拥塞';
        default: return strategy;
      }
    },
    getBackgroundTrafficModeName() {
      const modeMap = {
        'none': '无背景流量',
        'random': '随机背景流量',
        'burst': '突发背景流量'
      };
      return modeMap[this.config.background_traffic.mode] || this.config.background_traffic.mode;
    },

    async fetchAvailableTopologies() {
      try {
        const response = await fetch('http://localhost:3000/api/available_topologies');
        if (!response.ok) {
          throw new Error('获取拓扑列表失败');
        }

        const data = await response.json();
        this.availableTopologies = data.topologies || [];

        if (this.availableTopologies.length > 0) {
          this.config.topology_file = this.availableTopologies[0];
        }
      } catch (err) {
        console.error('获取拓扑列表错误:', err);
      }
    },

    // 从日志文本解析事件数据
    parseLogData(logText) {
      // 存储原始日志
      this.rawLogData = logText;

      // 初始化解析后的事件数据
      const parsedData = {
        forward: [],
        backward: [],
        ring: [],
        stats: [],
        config: {}
      };

      // 解析配置信息
      const configLines = logText.split('\n').filter(line =>
        line.includes('阶段') && line.includes('组') && line.includes('计算时间')
      );

      // 解析流水线阶段配置
      const stagesConfig = [];
      configLines.forEach(line => {
        const match = line.match(/组\s+(\d+)\s+阶段\s+(\d+)\s+\(节点:\s+(\d+)\)\s+计算时间:\s+([\d.]+)s/);
        if (match) {
          stagesConfig.push({
            group: parseInt(match[1]),
            stage: parseInt(match[2]),
            node: parseInt(match[3]),
            computeTime: parseFloat(match[4])
          });
        }
      });

      parsedData.stagesConfig = stagesConfig;

      // 提取并行配置
      const parallelConfigMatch = logText.match(/并行模式:\s+(\w+)/);
      const pipelineParallelMatch = logText.match(/流水线并行度:\s+(\d+)/);
      const dataParallelMatch = logText.match(/数据并行度:\s+(\d+)/);

      if (parallelConfigMatch) {
        parsedData.config.parallelMode = parallelConfigMatch[1];
      }

      if (pipelineParallelMatch) {
        parsedData.config.pipelineParallel = parseInt(pipelineParallelMatch[1]);
      }

      if (dataParallelMatch) {
        parsedData.config.dataParallel = parseInt(dataParallelMatch[1]);
      }

      // 提取模型配置
      const totalParamsMatch = logText.match(/总参数量:\s+(\d+)M/);
      const batchSizeMatch = logText.match(/批次大小:\s+(\d+)/);
      const microBatchMatch = logText.match(/微批次数量:\s+(\d+)/);

      if (totalParamsMatch) {
        parsedData.config.totalParams = parseInt(totalParamsMatch[1]);
      }

      if (batchSizeMatch) {
        parsedData.config.batchSize = parseInt(batchSizeMatch[1]);
      }

      if (microBatchMatch) {
        parsedData.config.microBatchCount = parseInt(microBatchMatch[1]);
      }

      // 解析事件行
      const eventLines = logText.split('\n').filter(line => line.match(/^\[\d+\.\d+s\]/));

      eventLines.forEach(line => {
        // 提取时间戳
        const timeMatch = line.match(/^\[(\d+\.\d+)s\]/);
        if (!timeMatch) return;

        const timestamp = parseFloat(timeMatch[1]);

        // 前向计算开始事件
        const forwardStartMatch = line.match(/批次\s+(\d+)\s+组\s+(\d+)\s+微批次\s+(\d+)\s+在节点\s+(\d+)\s+开始前向计算\s+\(阶段\s+(\d+)\)/);
        if (forwardStartMatch) {
          parsedData.forward.push({
            eventType: 'start_compute',
            timestamp,
            batch: parseInt(forwardStartMatch[1]),
            group: parseInt(forwardStartMatch[2]),
            microbatch: parseInt(forwardStartMatch[3]),
            sourceNode: parseInt(forwardStartMatch[4]),
            stage: parseInt(forwardStartMatch[5]),
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // 前向计算完成事件
        const forwardEndMatch = line.match(/批次\s+(\d+)\s+组\s+(\d+)\s+微批次\s+(\d+)\s+在节点\s+(\d+)\s+完成前向计算\s+\(阶段\s+(\d+)\)/);
        if (forwardEndMatch) {
          parsedData.forward.push({
            eventType: 'end_compute',
            timestamp,
            batch: parseInt(forwardEndMatch[1]),
            group: parseInt(forwardEndMatch[2]),
            microbatch: parseInt(forwardEndMatch[3]),
            sourceNode: parseInt(forwardEndMatch[4]),
            stage: parseInt(forwardEndMatch[5]),
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // 前向传输启动事件
        const forwardTransferStartMatch = line.match(/forward\s+传输启动:\s+(\d+)→(\d+)\s+\(目标\s+(\d+)\)\s+([\d.]+)MB/);
        if (forwardTransferStartMatch) {
          parsedData.forward.push({
            eventType: 'start_transfer',
            timestamp,
            sourceNode: parseInt(forwardTransferStartMatch[1]),
            targetNode: parseInt(forwardTransferStartMatch[2]),
            destNode: parseInt(forwardTransferStartMatch[3]),
            dataSize: parseFloat(forwardTransferStartMatch[4]),
            isBackward: false,
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // 前向传输完成事件
        const forwardTransferEndMatch = line.match(/forward\s+传输完成:\s+(\d+)→(\d+)\s+\(([\d.]+)MB\)/);
        if (forwardTransferEndMatch) {
          parsedData.forward.push({
            eventType: 'end_transfer',
            timestamp,
            sourceNode: parseInt(forwardTransferEndMatch[1]),
            targetNode: parseInt(forwardTransferEndMatch[2]),
            dataSize: parseFloat(forwardTransferEndMatch[3]),
            isBackward: false,
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // 反向计算开始事件
        const backwardStartMatch = line.match(/批次\s+(\d+)\s+组\s+(\d+)\s+微批次\s+(\d+)\s+在节点\s+(\d+)\s+开始反向计算\s+\(阶段\s+(\d+)\)/);
        if (backwardStartMatch) {
          parsedData.backward.push({
            eventType: 'start_backward_compute',
            timestamp,
            batch: parseInt(backwardStartMatch[1]),
            group: parseInt(backwardStartMatch[2]),
            microbatch: parseInt(backwardStartMatch[3]),
            sourceNode: parseInt(backwardStartMatch[4]),
            stage: parseInt(backwardStartMatch[5]),
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // 反向计算完成事件
        const backwardEndMatch = line.match(/批次\s+(\d+)\s+组\s+(\d+)\s+微批次\s+(\d+)\s+在节点\s+(\d+)\s+完成反向计算\s+\(阶段\s+(\d+)\)/);
        if (backwardEndMatch) {
          parsedData.backward.push({
            eventType: 'end_backward_compute',
            timestamp,
            batch: parseInt(backwardEndMatch[1]),
            group: parseInt(backwardEndMatch[2]),
            microbatch: parseInt(backwardEndMatch[3]),
            sourceNode: parseInt(backwardEndMatch[4]),
            stage: parseInt(backwardEndMatch[5]),
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // 反向传输启动事件
        const backwardTransferStartMatch = line.match(/backward\s+传输启动:\s+(\d+)→(\d+)\s+\(目标\s+(\d+)\)\s+([\d.]+)MB/);
        if (backwardTransferStartMatch) {
          parsedData.backward.push({
            eventType: 'start_transfer',
            timestamp,
            sourceNode: parseInt(backwardTransferStartMatch[1]),
            targetNode: parseInt(backwardTransferStartMatch[2]),
            destNode: parseInt(backwardTransferStartMatch[3]),
            dataSize: parseFloat(backwardTransferStartMatch[4]),
            isBackward: true,
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // 反向传输完成事件
        const backwardTransferEndMatch = line.match(/backward\s+传输完成:\s+(\d+)→(\d+)\s+\(([\d.]+)MB\)/);
        if (backwardTransferEndMatch) {
          parsedData.backward.push({
            eventType: 'end_transfer',
            timestamp,
            sourceNode: parseInt(backwardTransferEndMatch[1]),
            targetNode: parseInt(backwardTransferEndMatch[2]),
            dataSize: parseFloat(backwardTransferEndMatch[3]),
            isBackward: true,
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // 微批次完成事件
        const microbatchCompleteMatch = line.match(/批次\s+(\d+)\s+组\s+(\d+)\s+微批次\s+(\d+)\s+完成所有计算，总耗时:\s+([\d.]+)s/);
        if (microbatchCompleteMatch) {
          parsedData.stats.push({
            eventType: 'complete_batch',
            timestamp,
            batch: parseInt(microbatchCompleteMatch[1]),
            group: parseInt(microbatchCompleteMatch[2]),
            microbatch: parseInt(microbatchCompleteMatch[3]),
            totalTime: parseFloat(microbatchCompleteMatch[4]),
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // Ring-AllReduce开始事件
        const ringStartMatch = line.match(/批次\s+(\d+)\s+组\s+(\d+)\s+开始Ring-AllReduce梯度聚合/);
        if (ringStartMatch) {
          parsedData.ring.push({
            eventType: 'start_ring_allreduce',
            timestamp,
            batch: parseInt(ringStartMatch[1]),
            group: parseInt(ringStartMatch[2]),
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // Ring-AllReduce块传输事件
        const ringBlockMatch = line.match(/块传输完成:\s+(\d+)\s+接收块\s+(\d+)\s+\(迭代\s+(\d+)\)/);
        if (ringBlockMatch) {
          parsedData.ring.push({
            eventType: 'ring_communication',
            timestamp,
            targetNode: parseInt(ringBlockMatch[1]),
            chunkId: parseInt(ringBlockMatch[2]),
            iteration: parseInt(ringBlockMatch[3]),
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // 参数同步事件
        const parameterSyncMatch = line.match(/parameter\s+传输启动:\s+(\d+)→(\d+)\s+\(目标\s+(\d+)\)\s+([\d.]+)MB/);
        if (parameterSyncMatch) {
          parsedData.stats.push({
            eventType: 'parameter_sync',
            timestamp,
            sourceNode: parseInt(parameterSyncMatch[1]),
            targetNode: parseInt(parameterSyncMatch[2]),
            destNode: parseInt(parameterSyncMatch[3]),
            dataSize: parseFloat(parameterSyncMatch[4]),
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // 参数同步完成事件
        const parameterSyncCompleteMatch = line.match(/parameter\s+传输完成:\s+(\d+)→(\d+)\s+\(([\d.]+)MB\)/);
        if (parameterSyncCompleteMatch) {
          parsedData.stats.push({
            eventType: 'parameter_sync_complete',
            timestamp,
            sourceNode: parseInt(parameterSyncCompleteMatch[1]),
            targetNode: parseInt(parameterSyncCompleteMatch[2]),
            dataSize: parseFloat(parameterSyncCompleteMatch[3]),
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }

        // 批次完成事件
        const batchCompleteMatch = line.match(/批次\s+(\d+)\s+完成，耗时:\s+([\d.]+)s,\s+吞吐量:\s+([\d.]+)\s+样本\/秒/);
        if (batchCompleteMatch) {
          parsedData.stats.push({
            eventType: 'batch_complete',
            timestamp,
            batch: parseInt(batchCompleteMatch[1]),
            time: parseFloat(batchCompleteMatch[2]),
            throughput: parseFloat(batchCompleteMatch[3]),
            description: line.substring(timeMatch[0].length).trim()
          });
          return;
        }
      });

      // 解析统计信息部分
      const statsSectionMatch = logText.match(/===== 仿真统计 =====\n([\s\S]+)$/);
      if (statsSectionMatch) {
        const statsSection = statsSectionMatch[1];

        // 提取训练吞吐量
        const throughputMatch = statsSection.match(/训练吞吐量:\s+平均=([\d.]+)\s+样本\/秒,\s+最大=([\d.]+)\s+样本\/秒,\s+最小=([\d.]+)\s+样本\/秒/);
        if (throughputMatch) {
          parsedData.stats.push({
            eventType: 'stats',
            statType: '训练吞吐量',
            timestamp: this.maxTime,
            statValue: `平均=${throughputMatch[1]} 样本/秒, 最大=${throughputMatch[2]} 样本/秒, 最小=${throughputMatch[3]} 样本/秒`
          });
          this.averageThroughput = parseFloat(throughputMatch[1]);
        }

        // 提取迭代时间
        const iterTimeMatch = statsSection.match(/迭代时间:\s+平均=([\d.]+)s,\s+最大=([\d.]+)s,\s+最小=([\d.]+)s/);
        if (iterTimeMatch) {
          parsedData.stats.push({
            eventType: 'stats',
            statType: '迭代时间',
            timestamp: this.maxTime,
            statValue: `平均=${iterTimeMatch[1]}s, 最大=${iterTimeMatch[2]}s, 最小=${iterTimeMatch[3]}s`
          });
          this.averageIterationTime = parseFloat(iterTimeMatch[1]);
        }

        // 提取微批次完成时间
        const microBatchTimeMatch = statsSection.match(/微批次完成时间:\s+平均=([\d.]+)s,\s+最大=([\d.]+)s,\s+最小=([\d.]+)s/);
        if (microBatchTimeMatch) {
          parsedData.stats.push({
            eventType: 'stats',
            statType: '微批次完成时间',
            timestamp: this.maxTime,
            statValue: `平均=${microBatchTimeMatch[1]}s, 最大=${microBatchTimeMatch[2]}s, 最小=${microBatchTimeMatch[3]}s`
          });
        }

        // 提取通信量统计
        // 在parseLogData方法中，修改通信量统计的解析
        const commStatsMatch = statsSection.match(/通信量统计:\n\s+前向传播通信量:\s+([\d.]+)\s+MB\n\s+反向传播通信量:\s+([\d.]+)\s+MB\n\s+参数同步通信量:\s+([\d.]+)\s+MB\n\s+总通信量:\s+([\d.]+)\s+MB\n\s+通信\/计算比率:\s+([\d.]+)/);
        if (commStatsMatch) {
          this.forwardCommunicationVolume = parseFloat(commStatsMatch[1]);
          this.backwardCommunicationVolume = parseFloat(commStatsMatch[2]);
          this.parameterCommunicationVolume = parseFloat(commStatsMatch[3]);
          this.totalCommunicationVolume = parseFloat(commStatsMatch[4]);
          this.communicationComputeRatio = parseFloat(commStatsMatch[5]);

          parsedData.stats.push({
            eventType: 'stats',
            statType: '通信量统计',
            timestamp: this.maxTime,
            statValue: `前向=${commStatsMatch[1]} MB, 反向=${commStatsMatch[2]} MB, 参数=${commStatsMatch[3]} MB, 总计=${commStatsMatch[4]} MB`
          });
        }

        // 解析节点统计信息
        const nodeStatsSection = statsSection.match(/节点统计:([\s\S]+?)(?=\n\n|\n$)/);
        if (nodeStatsSection) {
          const nodeLines = nodeStatsSection[1].match(/\s+节点\s+\d+:.+/g);
          if (nodeLines) {
            let activeNodes = 0;
            let totalNodes = nodeLines.length;

            nodeLines.forEach(line => {
              const computeMatch = line.match(/计算占比=(\d+\.\d+)%/);
              if (computeMatch && parseFloat(computeMatch[1]) > 0) {
                activeNodes++;
              }
            });

            this.activeNodeCount = activeNodes;
            this.totalNodeCount = totalNodes;
            this.nodeUtilization = totalNodes > 0 ? activeNodes / totalNodes : 0;
          }
        }

        // 解析链路利用率详情
        const linkUtilSection = statsSection.match(/链路利用率详情:([\s\S]+?)(?=\n\n|\n链路延迟详情|\n$)/);
        if (linkUtilSection) {
          const linkLines = linkUtilSection[1].match(/\s+链路\s+.+:\s+(\d+\.\d+)%/g);
          if (linkLines) {
            let activeLinks = 0;
            let congestedLinks = 0;

            linkLines.forEach(line => {
              const utilMatch = line.match(/:\s+(\d+\.\d+)%/);
              if (utilMatch && parseFloat(utilMatch[1]) > 0) {
                activeLinks++;
                if (parseFloat(utilMatch[1]) > 50) { // 假设利用率超过50%为拥塞
                  congestedLinks++;
                }
              }
            });

            this.activeLinkCount = activeLinks;
            this.totalLinkCount = this.topologyData.links.length;
            this.congestedLinkCount = congestedLinks;
          }
        }

        // 提取完成批次数
        const completedBatchesMatch = statsSection.match(/完成批次数:\s+(\d+)\/(\d+)/);
        if (completedBatchesMatch) {
          this.completedBatchCount = parseInt(completedBatchesMatch[1]);
          this.config.num_batches = parseInt(completedBatchesMatch[2]);

          parsedData.stats.push({
            eventType: 'stats',
            statType: '完成批次数',
            timestamp: this.maxTime,
            statValue: `${completedBatchesMatch[1]}/${completedBatchesMatch[2]}`
          });
        }
        // 解析路由统计信息
        const routingStatsMatch = statsSection.match(/路由统计:\n\s+路由算法:\s+(\w+)(?:\n\s+ECMP策略:\s+(\w+))?(?:\n\s+最大等价路径数:\s+(\d+))?\n\s+平均路径长度:\s+([\d.]+)\n\s+路径多样性:\s+([\d.]+)\n\s+路由计算次数:\s+(\d+)\n\s+链路负载均衡度:\s+([\d.]+)/);

        if (routingStatsMatch) {
          const routingAlgorithm = routingStatsMatch[1];
          const ecmpStrategy = routingStatsMatch[2] || null;
          const ecmpMaxPaths = routingStatsMatch[3] ? parseInt(routingStatsMatch[3]) : null;
          this.averagePathLength = parseFloat(routingStatsMatch[4]);
          this.pathDiversity = parseFloat(routingStatsMatch[5]);
          this.routingCalculations = parseInt(routingStatsMatch[6]);
          this.loadBalanceScore = parseFloat(routingStatsMatch[7]);

          // 更新网络配置
          if (this.config.network) {
            this.config.network.routing_algorithm = routingAlgorithm;
            if (ecmpStrategy) {
              this.config.network.ecmp_strategy = ecmpStrategy;
            }
            if (ecmpMaxPaths) {
              this.config.network.ecmp_max_paths = ecmpMaxPaths;
            }
          }

          parsedData.stats.push({
            eventType: 'stats',
            statType: '路由统计',
            timestamp: this.maxTime,
            statValue: `平均路径长度=${this.averagePathLength.toFixed(2)}, 路径多样性=${this.pathDiversity.toFixed(2)}, 负载均衡度=${this.loadBalanceScore.toFixed(2)}`
          });
        }
      }

      // 提取所有可用的组和批次
      const groups = new Set();
      const batches = new Set();

      [...parsedData.forward, ...parsedData.backward].forEach(event => {
        if (event.group !== undefined) groups.add(event.group);
        if (event.batch !== undefined) batches.add(event.batch);
      });

      this.availableGroups = Array.from(groups).sort((a, b) => a - b);
      this.availableBatches = Array.from(batches).sort((a, b) => a - b);

      // 设置组和批次颜色
      const batchColorScale = d3.scaleOrdinal(d3.schemeCategory10);
      batches.forEach(batch => {
        this.batchColors[`批次 ${batch}`] = batchColorScale(batch);
      });

      const groupColorScale = d3.scaleOrdinal(d3.schemePaired);
      this.availableGroups.forEach(group => {
        this.groupColors[`组 ${group}`] = groupColorScale(group);
      });

      const totalSimTimeMatch = logText.match(/总仿真时间:\s+([\d.]+)s/);
      if (totalSimTimeMatch) {
        this.maxTime = parseFloat(totalSimTimeMatch[1]);
      } else {
        // 如果没有找到总时间，使用事件的最大时间戳
        const allEvents = [
          ...(this.simulationData.events.forward || []),
          ...(this.simulationData.events.backward || []),
          ...(this.simulationData.events.ring || []),
          ...(this.simulationData.events.stats || [])
        ];

        if (allEvents.length > 0) {
          this.maxTime = Math.max(...allEvents.map(e => e.timestamp || 0));
        }
      }

      // 设置流水线阶段数
      if (parsedData.stagesConfig && parsedData.stagesConfig.length > 0) {
        const stages = new Set(parsedData.stagesConfig.map(s => s.stage));
        this.stageCount = stages.size;
      }

      // 设置组数
      this.groupCount = this.availableGroups.length;

      return parsedData;
    },

    async loadTopology(topologyFile) {
      try {
        this.loading = true;
        this.error = null;

        // 如果没有提供拓扑文件，使用当前选择的或默认值
        const filename = topologyFile || this.currentTopologyFile || 'fattree.txt';

        const response = await fetch(`http://localhost:3000/api/topology?file=${filename}`);
        if (!response.ok) {
          throw new Error(`加载拓扑失败: ${response.statusText}`);
        }

        const data = await response.json();
        this.topologyData = data;

        // 初始化节点和链路状态
        this.initializeStates();

        // 重新初始化可视化
        this.$nextTick(() => {
          this.initializeVisualization();
          this.updateSimulationState();
        });

        this.loading = false;
      } catch (err) {
        console.error('加载拓扑错误:', err);
        this.error = '加载拓扑错误: ' + err.message;
        this.loading = false;
      }
    },
    async loadSimulationResult(logText) {
      try {
        this.loading = true;
        this.error = null;

        if (this.currentTopologyFile) {
          await this.loadTopology(this.currentTopologyFile);
        }

        // 解析日志数据
        const parsedData = this.parseLogData(logText);
        this.simulationData = {
          events: {
            forward: parsedData.forward,
            backward: parsedData.backward,
            ring: parsedData.ring,
            stats: parsedData.stats
          },
          stagesConfig: parsedData.stagesConfig,
          config: parsedData.config
        };

        this.parsedEvents = {
          forward: parsedData.forward,
          backward: parsedData.backward,
          ring: parsedData.ring,
          stats: parsedData.stats
        };

        // 初始化节点和链路状态
        this.initializeStates();

        this.loading = false;

        // 确保在DOM更新后初始化可视化
        this.$nextTick(() => {
          this.initializeVisualization();
          this.updateSimulationState();
          // this.initializeThroughputChart();
          // this.initializeCommunicationChart();
          // this.initializeNodeUtilizationChart();
          // this.initializeLinkUtilizationChart();
          this.initializeRoutingPerformanceChart(); // 添加路由性能图表初始化

        });

      } catch (err) {
        console.error('解析日志数据错误:', err);
        this.error = '解析日志数据时发生错误: ' + err.message;
        this.loading = false;
      }
    },

    initializeRoutingPerformanceChart() {
      if (!this.$refs.routingPerformanceChart) return;

      // 假设从simulationData中获取路由性能数据
      const routingData = this.simulationData?.routingPerformance || {
        timestamps: [],
        path_utilization: [],
        load_balance: []
      };

      // 使用D3.js或其他图表库创建路由性能图表
      // 这里只是一个简化的示例
      const width = this.$refs.routingPerformanceChart.clientWidth;
      const height = this.$refs.routingPerformanceChart.clientHeight;

      const svg = d3.select(this.$refs.routingPerformanceChart)
        .append('svg')
        .attr('width', width)
        .attr('height', height);

      // 如果有足够的数据点，绘制路径利用率和负载均衡曲线
      if (routingData.timestamps && routingData.timestamps.length > 0) {
        const xScale = d3.scaleLinear()
          .domain([0, d3.max(routingData.timestamps)])
          .range([40, width - 20]);

        const yScale = d3.scaleLinear()
          .domain([0, 1])
          .range([height - 30, 20]);

        // 绘制路径利用率曲线
        if (routingData.path_utilization && routingData.path_utilization.length > 0) {
          const line = d3.line()
            .x((d, i) => xScale(routingData.timestamps[i]))
            .y(d => yScale(d));

          svg.append('path')
            .datum(routingData.path_utilization)
            .attr('fill', 'none')
            .attr('stroke', '#3498db')
            .attr('stroke-width', 2)
            .attr('d', line);
        }

        // 绘制负载均衡曲线
        if (routingData.load_balance && routingData.load_balance.length > 0) {
          const line = d3.line()
            .x((d, i) => xScale(routingData.timestamps[i]))
            .y(d => yScale(d));

          svg.append('path')
            .datum(routingData.load_balance)
            .attr('fill', 'none')
            .attr('stroke', '#e74c3c')
            .attr('stroke-width', 2)
            .attr('d', line);
        }

        // 添加坐标轴
        const xAxis = d3.axisBottom(xScale);
        const yAxis = d3.axisLeft(yScale);

        svg.append('g')
          .attr('transform', `translate(0, ${height - 30})`)
          .call(xAxis);

        svg.append('g')
          .attr('transform', 'translate(40, 0)')
          .call(yAxis);

        // 添加图例
        svg.append('circle')
          .attr('cx', 60)
          .attr('cy', 15)
          .attr('r', 5)
          .attr('fill', '#3498db');

        svg.append('text')
          .attr('x', 70)
          .attr('y', 18)
          .text('路径利用率')
          .attr('font-size', '10px');

        svg.append('circle')
          .attr('cx', 150)
          .attr('cy', 15)
          .attr('r', 5)
          .attr('fill', '#e74c3c');

        svg.append('text')
          .attr('x', 160)
          .attr('y', 18)
          .text('负载均衡度')
          .attr('font-size', '10px');
      } else {
        // 如果没有数据，显示提示信息
        svg.append('text')
          .attr('x', width / 2)
          .attr('y', height / 2)
          .attr('text-anchor', 'middle')
          .text('无路由性能数据')
          .attr('font-size', '14px')
          .attr('fill', '#999');
      }
    },

    addComputeStage() {
      this.config.compute_times.push(1.0);
    },

    removeComputeStage() {
      if (this.config.compute_times.length > 1) {
        this.config.compute_times.pop();
      }
    },

    toggleNodePowerConfig() {
      this.showNodePowerConfig = !this.showNodePowerConfig;
    },

    addNodePower() {
      const nextNodeId = Object.keys(this.config.node_compute_power).length;
      this.$set(this.config.node_compute_power, nextNodeId, 1.0);
    },

    toggleGroupConfig() {
      this.showGroupConfig = !this.showGroupConfig;
    },

    addGroup() {
      this.config.groups.push([0]);
    },

    removeGroup(groupIndex) {
      if (this.config.groups.length > 1) {
        this.config.groups.splice(groupIndex, 1);
      }
    },

    addNodeToGroup(groupIndex) {
      this.config.groups[groupIndex].push(0);
    },

    removeNodeFromGroup(groupIndex) {
      if (this.config.groups[groupIndex].length > 1) {
        this.config.groups[groupIndex].pop();
      }
    },

    async runSimulation() {
      try {
        this.loading = true;
        this.error = null;
        this.simulationRunning = true;
        this.currentTopologyFile = this.config.topology_file;

        // 发送配置到后端API
        const response = await fetch('http://localhost:3000/api/run_simulation', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(this.config),
        });

        if (!response.ok) {
          throw new Error('仿真请求失败');
        }

        const result = await response.json();

        if (!result.success) {
          throw new Error(result.error || '仿真执行失败');
        }

        // 仿真成功完成，加载结果
        if (result.logData) {
          // 隐藏配置面板，显示结果
          this.showConfig = false;
          await this.loadSimulationResult(result.logData);
        } else if (result.resultFile) {
          // 如果返回的是文件路径，则需要再发起一个请求获取日志内容
          const logResponse = await fetch(`http://localhost:3000/api/log?file=${result.resultFile}`);
          if (!logResponse.ok) {
            throw new Error('获取日志数据失败');
          }
          const logData = await logResponse.text();
          this.showConfig = false;
          await this.loadSimulationResult(logData);
        } else {
          throw new Error('未获取到仿真结果数据');
        }


      } catch (err) {
        console.error('仿真错误:', err);
        this.error = '仿真错误: ' + err.message;
      } finally {
        this.loading = false;
        this.simulationRunning = false;
      }
    },

    initializeStates() {
      // 初始化节点状态
      this.nodeStateMap = {};
      if (this.topologyData && this.topologyData.nodes) {
        this.topologyData.nodes.forEach(node => {
          this.nodeStateMap[node.id] = {
            busy: false,
            currentBatch: null,
            currentGroup: null,
            isBackward: false,
            isRingNode: false
          };
        });
      }

      // 初始化链路状态
      this.linkStateMap = {};
      if (this.topologyData && this.topologyData.links) {
        this.topologyData.links.forEach(link => {
          const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
          const targetId = typeof link.target === 'object' ? link.target.id : link.target;

          const linkId = `${sourceId}-${targetId}`;
          this.linkStateMap[linkId] = {
            active: false,
            packets: [],
            congested: false,
            isBackward: false,
            isRing: false
          };

          // 添加反向链接
          const reverseLinkId = `${targetId}-${sourceId}`;
          this.linkStateMap[reverseLinkId] = {
            active: false,
            packets: [],
            congested: false,
            isBackward: false,
            isRing: false
          };
        });
      }
    },

    initializeVisualization() {
      const topologyViz = this.$refs.topologyViz;
      console.log(this.$refs.topologyViz)
      if (!topologyViz || !this.topologyData) return;

      // 清除现有的可视化
      if (this.svg) {
        d3.select(topologyViz).selectAll("*").remove();
      }

      const width = topologyViz.clientWidth || 600;
      const height = topologyViz.clientHeight || 400;

      // 创建SVG元素
      this.svg = d3.select(topologyViz)
        .append('svg')
        .attr('width', width)
        .attr('height', height);

      // 创建箭头标记
      this.svg.append('defs').append('marker')
        .attr('id', 'arrowhead')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 20)
        .attr('refY', 0)
        .attr('orient', 'auto')
        .attr('markerWidth', 2)
        .attr('markerHeight', 2)
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#999');

      // 预先计算节点位置以减少摇摆
      this.precomputeNodePositions(width, height);

      // 创建力导向图 - 使用预先计算的位置和较高的alpha衰减
      this.simulation = d3.forceSimulation(this.topologyData.nodes)
        .force('link', d3.forceLink(this.topologyData.links).id(d => d.id).distance(100))
        .force('charge', d3.forceManyBody().strength(-300))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .alphaDecay(0.1) // 增加alpha衰减速率，使布局更快稳定
        .velocityDecay(0.4) // 增加速度衰减，减少振荡
        .on('tick', this.ticked);

      // 创建链路
      this.linkElements = this.svg.append('g')
        .selectAll('line')
        .data(this.topologyData.links)
        .enter().append('line')
        .attr('class', 'link')
        .attr('stroke', '#999')
        .attr('stroke-width', d => 1)
        .attr('marker-end', 'url(#arrowhead)');

      // 创建节点
      this.nodeElements = this.svg.append('g')
        .selectAll('circle')
        .data(this.topologyData.nodes)
        .enter().append('circle')
        .attr('class', 'node')
        .attr('r', d => this.getNodeRadius(d))
        .attr('fill', d => this.getNodeColor(d))
        .call(d3.drag()
          .on('start', this.dragstarted)
          .on('drag', this.dragged)
          .on('end', this.dragended));

      // 添加节点标签
      const nodeLabels = this.svg.append('g')
        .selectAll('text')
        .data(this.topologyData.nodes)
        .enter().append('text')
        .text(d => d.id)
        .attr('font-size', 10)
        .attr('dx', 12)
        .attr('dy', 4);

      this.packetElements = [];

      // 悬停提示
      const tooltip = d3.select('body').append('div')
        .attr('class', 'tooltip')
        .style('opacity', 0)
        .style('position', 'absolute')
        .style('background', 'white')
        .style('border', '1px solid #ddd')
        .style('border-radius', '4px')
        .style('padding', '8px')
        .style('pointer-events', 'none')
        .style('z-index', 1000);

      const zoom = d3.zoom()
        .scaleExtent([0.1, 4])
        .on('zoom', (event) => {
          this.svg.selectAll('g').attr('transform', event.transform);
        });

      this.svg.call(zoom);

      this.nodeElements
        .on('mouseover', (event, d) => {
          const nodeState = this.nodeStateMap[d.id];
          let tooltipHtml = `节点ID: ${d.id}<br/>类型: ${d.type || '未知'}<br/>状态: ${nodeState.busy ? '忙' : '闲'}`;

          if (nodeState.busy) {
            if (nodeState.currentGroup !== null) {
              tooltipHtml += `<br/>组: ${nodeState.currentGroup}`;
            }
            if (nodeState.currentBatch !== null) {
              tooltipHtml += `<br/>微批次: ${nodeState.currentBatch}`;
            }
          }

          tooltip.transition()
            .duration(200)
            .style('opacity', .9);
          tooltip.html(tooltipHtml)
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY - 28) + 'px');
        })
        .on('mouseout', () => {
          tooltip.transition()
            .duration(500)
            .style('opacity', 0);
        });

      // 运行几次模拟迭代以快速稳定布局
      for (let i = 0; i < 100; i++) {
        this.simulation.tick();
      }

      // 更新初始位置
      this.ticked();
    },

    precomputeNodePositions(width, height) {
      if (!this.topologyData || !this.topologyData.nodes) return;

      // 根据拓扑结构预先计算节点位置
      // 这里使用简单的网格布局作为初始位置
      const nodeCount = this.topologyData.nodes.length;
      const cols = Math.ceil(Math.sqrt(nodeCount));
      const rows = Math.ceil(nodeCount / cols);

      const cellWidth = width / (cols + 1);
      const cellHeight = height / (rows + 1);

      // 为每个节点分配初始位置
      this.topologyData.nodes.forEach((node, i) => {
        const row = Math.floor(i / cols);
        const col = i % cols;

        // 添加一点随机偏移以避免完全重叠
        const jitter = 5;
        node.x = cellWidth * (col + 1) + (Math.random() * jitter - jitter / 2);
        node.y = cellHeight * (row + 1) + (Math.random() * jitter - jitter / 2);

        // 固定位置以加快稳定
        if (node.type === 'switch') {
          node.fx = node.x;
          node.fy = node.y;
        }
      });
    },

    ticked() {
      // 安全检查，确保元素存在
      if (!this.linkElements || !this.nodeElements) return;

      this.linkElements
        .attr('x1', d => d.source.x || 0)
        .attr('y1', d => d.source.y || 0)
        .attr('x2', d => d.target.x || 0)
        .attr('y2', d => d.target.y || 0);

      this.nodeElements
        .attr('cx', d => d.x || 0)
        .attr('cy', d => d.y || 0)
        .attr('class', d => {
          return this.nodeStateMap[d.id] && this.nodeStateMap[d.id].busy ? 'node busy-node' : 'node';
        });

      // 更新标签位置
      this.svg.selectAll('text')
        .attr('x', d => d.x || 0)
        .attr('y', d => d.y || 0);

      // 更新包的位置
      this.updatePacketsPosition();
    },

    updatePacketsPosition() {
      // 更新所有数据包的位置
      this.packetElements.forEach(packet => {
        // 安全检查，确保节点存在
        if (!packet.sourceId || !packet.targetId || !packet.element) return;

        const sourceNode = this.topologyData.nodes.find(n => n.id === packet.sourceId);
        const targetNode = this.topologyData.nodes.find(n => n.id === packet.targetId);

        if (sourceNode && targetNode &&
          sourceNode.x !== undefined && targetNode.x !== undefined) {
          // 计算在链接上的位置（基于进度）
          const progress = packet.progress || 0;
          const x = sourceNode.x + (targetNode.x - sourceNode.x) * progress;
          const y = sourceNode.y + (targetNode.y - sourceNode.y) * progress;

          packet.element
            .attr('cx', x)
            .attr('cy', y);
        }
      });
    },

    getNodeRadius(node) {
      return node.type === 'switch' ? 8 : 6;
    },

    getNodeColor(node) {
      return node.type === 'switch' ? '#3498db' : '#2ecc71';
    },

    dragstarted(event) {
      if (!event.active) this.simulation.alphaTarget(0.3).restart();
      event.subject.fx = event.subject.x;
      event.subject.fy = event.subject.y;
    },

    dragged(event) {
      event.subject.fx = event.x;
      event.subject.fy = event.y;
    },

    dragended(event) {
      if (!event.active) this.simulation.alphaTarget(0);
      // 不释放固定位置，保持节点稳定
      // event.subject.fx = null;
      // event.subject.fy = null;
    },

    startPlayback() {
      if (this.isPlaying) return;

      this.isPlaying = true;
      this.lastTimestamp = performance.now();
      this.animationFrameId = requestAnimationFrame(this.animate);
    },

    pausePlayback() {
      this.isPlaying = false;
      if (this.animationFrameId) {
        cancelAnimationFrame(this.animationFrameId);
        this.animationFrameId = null;
      }
    },

    resetPlayback() {
      this.pausePlayback();
      this.currentTime = 0;
      this.updateSimulationState();
    },

    seekProgress(event) {
      if (!this.$refs.progressBar) return;

      const rect = this.$refs.progressBar.getBoundingClientRect();
      const clickPosition = (event.clientX - rect.left) / rect.width;
      this.currentTime = clickPosition * this.maxTime;
      this.updateSimulationState();
    },

    animate(timestamp) {
      if (!this.isPlaying) return;

      const deltaTime = (timestamp - this.lastTimestamp) / 1000;
      this.lastTimestamp = timestamp;

      this.currentTime += deltaTime * this.playbackSpeed;
      if (this.currentTime >= this.maxTime) {
        this.currentTime = this.maxTime;
        this.pausePlayback();
      }

      this.updateSimulationState();

      if (this.isPlaying) {
        this.animationFrameId = requestAnimationFrame(this.animate);
      }
    },

    updateSimulationState() {
      if (!this.simulationData || !this.topologyData) return;

      // 重置所有状态
      Object.values(this.nodeStateMap).forEach(state => {
        state.busy = false;
        state.currentBatch = null;
        state.currentGroup = null;
        state.isBackward = false;
        state.isRingNode = false;
      });

      Object.values(this.linkStateMap).forEach(state => {
        state.active = false;
        state.packets = [];
        state.congested = false;
        state.isBackward = false;
        state.isRing = false;
      });

      // 移除所有数据包
      this.packetElements.forEach(packet => {
        if (packet.element) {
          packet.element.remove();
        }
      });
      this.packetElements = [];

      // 获取当前时间点之前的所有事件
      const currentEvents = [];

      // 根据选择的组过滤事件
      const groupFilter = this.selectedGroup === 'all' ? null : parseInt(this.selectedGroup);
      const batchFilter = this.selectedBatch === 'all' ? null : parseInt(this.selectedBatch);

      // 处理前向传播事件
      if (this.parsedEvents.forward) {
        let forwardEvents = this.parsedEvents.forward.filter(e => e.timestamp <= this.currentTime);

        if (groupFilter !== null) {
          forwardEvents = forwardEvents.filter(e => e.group === groupFilter || e.group === undefined);
        }

        if (batchFilter !== null) {
          forwardEvents = forwardEvents.filter(e => e.batch === batchFilter || e.batch === undefined);
        }

        currentEvents.push(...forwardEvents);
      }

      // 处理反向传播事件
      if (this.parsedEvents.backward) {
        let backwardEvents = this.parsedEvents.backward.filter(e => e.timestamp <= this.currentTime);

        if (groupFilter !== null) {
          backwardEvents = backwardEvents.filter(e => e.group === groupFilter || e.group === undefined);
        }

        if (batchFilter !== null) {
          backwardEvents = backwardEvents.filter(e => e.batch === batchFilter || e.batch === undefined);
        }

        currentEvents.push(...backwardEvents);
      }

      // 处理环通信事件
      if (this.parsedEvents.ring && this.showRingEvents) {
        let ringEvents = this.parsedEvents.ring.filter(e => e.timestamp <= this.currentTime);

        if (groupFilter !== null) {
          ringEvents = ringEvents.filter(e => e.group === groupFilter || e.group === undefined);
        }

        if (batchFilter !== null) {
          ringEvents = ringEvents.filter(e => e.batch === batchFilter || e.batch === undefined);
        }

        currentEvents.push(...ringEvents);
      }

      // 处理统计事件
      if (this.parsedEvents.stats && this.showStatsEvents) {
        let statsEvents = this.parsedEvents.stats.filter(e =>
          e.timestamp !== undefined && e.timestamp <= this.currentTime
        );

        if (groupFilter !== null) {
          statsEvents = statsEvents.filter(e => e.group === groupFilter || e.group === undefined);
        }

        if (batchFilter !== null) {
          statsEvents = statsEvents.filter(e => e.batch === batchFilter || e.batch === undefined);
        }

        currentEvents.push(...statsEvents);
      }

      // 处理计算和传输事件
      const activeComputations = new Map();
      const activeTransfers = new Map();

      // 处理所有事件
      for (const event of currentEvents) {
        if (event.eventType === 'start_compute') {
          activeComputations.set(event.sourceNode, {
            startTime: event.timestamp,
            batch: event.batch,
            group: event.group,
            isBackward: false
          });
        } else if (event.eventType === 'end_compute') {
          activeComputations.delete(event.sourceNode);
        } else if (event.eventType === 'start_backward_compute') {
          activeComputations.set(event.sourceNode, {
            startTime: event.timestamp,
            batch: event.batch,
            group: event.group,
            isBackward: true
          });
        } else if (event.eventType === 'end_backward_compute') {
          activeComputations.delete(event.sourceNode);
        } else if (event.eventType === 'start_transfer') {
          const transferKey = `${event.sourceNode}-${event.targetNode}`;
          activeTransfers.set(transferKey, {
            startTime: event.timestamp,
            endTime: null,
            sourceId: event.sourceNode,
            targetId: event.targetNode,
            destId: event.destNode || event.targetNode,
            batch: event.batch,
            group: event.group,
            dataSize: event.dataSize,
            isBackward: event.isBackward,
            isRing: false
          });
        } else if (event.eventType === 'end_transfer') {
          const transferKey = `${event.sourceNode}-${event.targetNode}`;
          if (activeTransfers.has(transferKey)) {
            const transfer = activeTransfers.get(transferKey);
            transfer.endTime = event.timestamp;

            // 如果传输已经结束，而当前时间大于结束时间，删除这个传输
            if (event.timestamp <= this.currentTime) {
              activeTransfers.delete(transferKey);
            }
          }
        } else if (event.eventType === 'ring_communication') {
          // 处理Ring事件
          if (event.sourceNode === undefined && event.targetNode !== undefined) {
            // 如果只有目标节点，我们需要找一个合适的源节点
            // 这里简单地从拓扑中找一个连接到目标节点的节点
            const sourceLink = this.topologyData.links.find(link => {
              const targetId = typeof link.target === 'object' ? link.target.id : link.target;
              return targetId === event.targetNode;
            });

            if (sourceLink) {
              const sourceId = typeof sourceLink.source === 'object' ? sourceLink.source.id : sourceLink.source;
              const transferKey = `${sourceId}-${event.targetNode}`;

              activeTransfers.set(transferKey, {
                startTime: event.timestamp,
                endTime: event.timestamp + 0.01, // 假设Ring通信持续0.01秒
                sourceId: sourceId,
                targetId: event.targetNode,
                chunkId: event.chunkId,
                iteration: event.iteration,
                batch: event.batch,
                group: event.group,
                isBackward: false,
                isRing: true
              });
            }
          } else if (event.sourceNode !== undefined && event.targetNode !== undefined) {
            const transferKey = `${event.sourceNode}-${event.targetNode}`;

            activeTransfers.set(transferKey, {
              startTime: event.timestamp,
              endTime: event.timestamp + 0.01, // 假设Ring通信持续0.01秒
              sourceId: event.sourceNode,
              targetId: event.targetNode,
              chunkId: event.chunkId,
              iteration: event.iteration,
              batch: event.batch,
              group: event.group,
              isBackward: false,
              isRing: true
            });
          }
        } else if (event.eventType === 'start_ring_allreduce') {
          // 处理Ring-AllReduce开始事件
          if (event.group !== undefined) {
            // 找出该组的所有节点
            const groupNodes = this.simulationData.stagesConfig
              ?.filter(stage => stage.group === event.group)
              ?.map(stage => stage.node) || [];

            // 将这些节点标记为Ring节点
            groupNodes.forEach(nodeId => {
              if (this.nodeStateMap[nodeId]) {
                this.nodeStateMap[nodeId].isRingNode = true;
              }
            });
          }
        }
      }

      // 更新节点状态
      activeComputations.forEach((computation, nodeId) => {
        if (this.nodeStateMap[nodeId]) {
          this.nodeStateMap[nodeId].busy = true;
          this.nodeStateMap[nodeId].currentBatch = computation.batch;
          this.nodeStateMap[nodeId].currentGroup = computation.group;
          this.nodeStateMap[nodeId].isBackward = computation.isBackward;
        }
      });

      // 更新链路状态和创建数据包
      activeTransfers.forEach((transfer, transferKey) => {
        if (this.linkStateMap[transferKey]) {
          this.linkStateMap[transferKey].active = true;
          this.linkStateMap[transferKey].isBackward = transfer.isBackward;
          this.linkStateMap[transferKey].isRing = transfer.isRing;

          // 计算传输进度
          let progress = 0;
          if (transfer.endTime) {
            // 传输有明确的结束时间
            const totalDuration = transfer.endTime - transfer.startTime;
            const elapsed = this.currentTime - transfer.startTime;
            progress = Math.min(1, Math.max(0, elapsed / totalDuration));
          } else {
            // 传输没有结束时间，使用平均速率估计
            const elapsed = this.currentTime - transfer.startTime;
            progress = Math.min(1, Math.max(0, elapsed / 0.1)); // 假设传输平均需要0.1秒
          }

          // 创建数据包表示
          if (progress < 1) {
            const packet = {
              sourceId: transfer.sourceId,
              targetId: transfer.targetId,
              progress,
              batch: transfer.batch,
              group: transfer.group,
              isBackward: transfer.isBackward,
              isRing: transfer.isRing,
              element: null
            };

            // 找到源节点和目标节点
            const sourceNode = this.topologyData.nodes.find(n => n.id === transfer.sourceId);
            const targetNode = this.topologyData.nodes.find(n => n.id === transfer.targetId);

            if (sourceNode && targetNode &&
              sourceNode.x !== undefined && targetNode.x !== undefined &&
              this.svg) {
              // 计算包的位置
              const x = sourceNode.x + (targetNode.x - sourceNode.x) * progress;
              const y = sourceNode.y + (targetNode.y - sourceNode.y) * progress;
              // 创建包的可视化元素
              let packetColor = this.forwardColor; // 默认前向传播颜色

              if (transfer.isBackward) {
                packetColor = this.backwardColor; // 反向传播颜色
              } else if (transfer.isRing) {
                packetColor = this.ringColor; // Ring通信颜色
              } else if (transfer.batch !== undefined) {
                packetColor = this.batchColors[`批次 ${transfer.batch}`] || this.forwardColor;
              }

              packet.element = this.svg.append('circle')
                .attr('class', 'packet')
                .attr('r', 5)
                .attr('cx', x)
                .attr('cy', y)
                .attr('fill', packetColor);

              this.packetElements.push(packet);
              this.linkStateMap[transferKey].packets.push(packet);
            }
          }

          // 检测链路拥堵（当有多个数据包时）
          if (this.linkStateMap[transferKey].packets.length > 1) {
            this.linkStateMap[transferKey].congested = true;
          }
        }
      });

      // 更新链路的视觉效果
      if (this.linkElements) {
        this.linkElements
          .attr('class', d => {
            // 确保source和target是对象而不是ID
            const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
            const targetId = typeof d.target === 'object' ? d.target.id : d.target;
            const linkId = `${sourceId}-${targetId}`;

            let classes = 'link';
            if (this.linkStateMap[linkId] && this.linkStateMap[linkId].congested) {
              classes += ' congested-link';
            }
            return classes;
          })
          .attr('stroke', d => {
            // 确保source和target是对象而不是ID
            const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
            const targetId = typeof d.target === 'object' ? d.target.id : d.target;
            const linkId = `${sourceId}-${targetId}`;

            // 根据链路状态设置不同的颜色
            if (this.linkStateMap[linkId]) {
              if (this.linkStateMap[linkId].isRing && this.linkStateMap[linkId].active) {
                return this.ringColor;
              } else if (this.linkStateMap[linkId].isBackward && this.linkStateMap[linkId].active) {
                return this.backwardColor;
              } else if (this.linkStateMap[linkId].active) {
                return this.forwardColor;
              }
            }
            return '#aaa';
          })
          .attr('stroke-opacity', d => {
            // 确保source和target是对象而不是ID
            const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
            const targetId = typeof d.target === 'object' ? d.target.id : d.target;
            const linkId = `${sourceId}-${targetId}`;

            return this.linkStateMap[linkId] && this.linkStateMap[linkId].active ? 0.8 : 0.2;
          })
          .attr('stroke-dasharray', d => {
            // 确保source和target是对象而不是ID
            const sourceId = typeof d.source === 'object' ? d.source.id : d.source;
            const targetId = typeof d.target === 'object' ? d.target.id : d.target;
            const linkId = `${sourceId}-${targetId}`;

            // 使用虚线表示Ring通信
            return this.linkStateMap[linkId] && this.linkStateMap[linkId].isRing ? '5,5' : null;
          });
      }

      // 更新节点的视觉效果
      if (this.nodeElements) {
        this.nodeElements
          .attr('fill', d => {
            if (this.nodeStateMap[d.id] && this.nodeStateMap[d.id].busy) {
              // 如果是反向传播，使用反向传播的颜色
              if (this.nodeStateMap[d.id].isBackward) {
                return this.backwardColor;
              }

              const batch = this.nodeStateMap[d.id].currentBatch;
              const group = this.nodeStateMap[d.id].currentGroup;

              if (batch !== null && this.batchColors[`批次 ${batch}`]) {
                return this.batchColors[`批次 ${batch}`];
              } else if (group !== null && this.groupColors[`组 ${group}`]) {
                return this.groupColors[`组 ${group}`];
              }
            } else if (this.nodeStateMap[d.id] && this.nodeStateMap[d.id].isRingNode) {
              // 如果是参与Ring-AllReduce的节点，使用Ring颜色
              return this.ringColor;
            }

            return this.getNodeColor(d);
          })
          .attr('stroke', d => {
            // 为参与Ring-AllReduce的节点添加边框
            if (this.nodeStateMap[d.id] && this.nodeStateMap[d.id].isRingNode) {
              return '#000';
            }
            return null;
          })
          .attr('stroke-width', d => {
            // 为参与Ring-AllReduce的节点添加边框
            if (this.nodeStateMap[d.id] && this.nodeStateMap[d.id].isRingNode) {
              return 2;
            }
            return 0;
          });
      }

      // 更新统计信息
      this.updateStatistics();
    },

    updateStatistics() {
      // 计算活跃节点数
      this.activeNodeCount = Object.values(this.nodeStateMap).filter(state => state.busy).length;

      // 计算计算中的节点数
      this.computeNodeCount = Object.values(this.nodeStateMap).filter(state => state.busy).length;

      // 计算节点利用率
      this.nodeUtilization = this.totalNodeCount > 0 ? this.activeNodeCount / this.totalNodeCount : 0;

      // 计算活跃链路数
      this.activeLinkCount = Object.values(this.linkStateMap).filter(state => state.active).length;

      // 计算拥塞链路数
      this.congestedLinkCount = Object.values(this.linkStateMap).filter(state => state.congested).length;

      // 计算链路利用率
      this.linkUtilization = this.totalLinkCount > 0 ? this.activeLinkCount / this.totalLinkCount : 0;
    },

    // 事件类型样式
    getEventClass(event) {
      if (event.eventType === 'start_compute' || event.eventType === 'end_compute') {
        return 'event-compute';
      } else if (event.eventType === 'start_backward_compute' || event.eventType === 'end_backward_compute') {
        return 'event-backward-compute';
      } else if (event.eventType === 'start_transfer' || event.eventType === 'end_transfer') {
        return event.isBackward ? 'event-backward-transfer' : 'event-transfer';
      } else if (event.eventType === 'complete_batch' || event.eventType === 'batch_complete') {
        return 'event-complete';
      } else if (event.eventType === 'start_ring_allreduce' || event.eventType === 'ring_communication') {
        return 'event-ring-allreduce';
      } else if (event.eventType === 'stats') {
        return 'event-stats';
      } else if (event.eventType === 'parameter_sync' || event.eventType === 'parameter_sync_complete') {
        return 'event-parameter';
      }
      return '';
    },

    // 事件描述
    getEventDescription(event) {
      if (!event) return '';

      let prefix = '';
      if (event.group !== undefined) {
        prefix = `组 ${event.group} `;
      }

      if (event.batch !== undefined) {
        prefix += `批次 ${event.batch} `;
      }

      if (event.microbatch !== undefined) {
        prefix += `微批次 ${event.microbatch} `;
      }

      switch (event.eventType) {
        case 'start_compute':
          return `${prefix}开始前向计算 (阶段 ${event.stage} 节点 ${event.sourceNode})`;

        case 'end_compute':
          return `${prefix}完成前向计算 (阶段 ${event.stage} 节点 ${event.sourceNode})`;

        case 'start_backward_compute':
          return `${prefix}开始反向计算 (阶段 ${event.stage} 节点 ${event.sourceNode})`;

        case 'end_backward_compute':
          return `${prefix}完成反向计算 (阶段 ${event.stage} 节点 ${event.sourceNode})`;

        case 'start_transfer':
          const direction = event.isBackward ? '反向' : '前向';
          return `${prefix}${direction}传输启动: ${event.sourceNode}→${event.targetNode} (目标 ${event.destNode || event.targetNode}) ${event.dataSize}MB`;

        case 'end_transfer':
          const dir = event.isBackward ? '反向' : '前向';
          return `${prefix}${dir}传输完成: ${event.sourceNode}→${event.targetNode} (${event.dataSize}MB)`;

        case 'complete_batch':
          return `${prefix}微批次 ${event.microbatch} 完成所有计算，总耗时: ${event.totalTime}s`;

        case 'batch_complete':
          return `${prefix}批次 ${event.batch} 完成，耗时: ${event.time}s, 吞吐量: ${event.throughput} 样本/秒`;

        case 'start_ring_allreduce':
          return `${prefix}开始Ring-AllReduce梯度聚合`;

        case 'ring_communication':
          return `${prefix}节点 ${event.targetNode} 接收块 ${event.chunkId} (迭代 ${event.iteration})`;

        case 'parameter_sync':
          return `${prefix}参数同步: ${event.sourceNode}→${event.targetNode} (${event.dataSize}MB)`;

        case 'parameter_sync_complete':
          return `${prefix}参数同步完成: ${event.sourceNode}→${event.targetNode} (${event.dataSize}MB)`;

        case 'stats':
          if (event.statType && event.statValue) {
            return `${event.statType}: ${event.statValue}`;
          }
          return event.description || '统计信息';

        default:
          return event.description || '未知事件';
      }
    }
  }
}
</script>

<style src="./style.css"></style>