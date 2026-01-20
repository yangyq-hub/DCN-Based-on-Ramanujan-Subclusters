const express = require('express');
const fs = require('fs');
const path = require('path');
const cors = require('cors');
const { spawn } = require('child_process');
const bodyParser = require('body-parser');
const yaml = require('js-yaml');
const { execSync } = require('child_process');
const app = express();
const PORT = 3000;

app.use(cors());
app.use(express.static('public'));
app.use(bodyParser.json()); // 解析JSON请求体

// 读取仿真结果数据
app.get('/api/results', (req, res) => {
  try {
    // 获取文件名参数，如果没有则使用默认值
    console.log(req.query.file)
    const filename = path.join("results",req.query.file);
    const simulationData = fs.readFileSync(filename, 'utf8');
    const lines = simulationData.split('\n');
    
    // 解析阶段配置信息
    const stagesConfig = [];
    const forwardEvents = [];
    const backwardEvents = []; // 反向传播事件
    const ringEvents = [];
    const statsEvents = []; // 统计事件（丢包、完成等）
    
    let parsingStages = true;
    let parsingEvents = false;
    let parsingStats = false;
    
    lines.forEach(line => {
      if (line.trim() === '') return;
      
      // 检测部分切换
      if (line.includes('开始仿真...')) {
        parsingStages = false;
        parsingEvents = true;
        return;
      }
      
      if (line.includes('===== 仿真统计 =====')) {
        parsingEvents = false;
        parsingStats = true;
        return;
      }
      
      if (parsingStages) {
        // 解析阶段配置 - 格式: 组 0 阶段 0 (节点: 44) 计算时间: 2.1s
        const stageMatch = line.match(/组\s(\d+)\s阶段\s(\d+)\s\(节点:\s(\d+)\)\s计算时间:\s([\d.]+)s/);
        if (stageMatch) {
          stagesConfig.push({
            group: parseInt(stageMatch[1]),
            id: parseInt(stageMatch[2]),
            node: parseInt(stageMatch[3]),
            computeTime: parseFloat(stageMatch[4])
          });
        }
      } else if (parsingEvents) {
        // 解析事件
        const eventMatch = line.match(/\[([\d.]+)s\]\s(.*)/);
        if (eventMatch) {
          const timestamp = parseFloat(eventMatch[1]);
          const description = eventMatch[2];
          
          let eventType = 'other';
          let group = null;
          let batch = null;
          let sourceNode = null;
          let targetNode = null;
          let destNode = null;
          let dataSize = null;
          let isBackward = false;
          
          // 检查是否是前向计算开始
          if (description.includes('开始前向计算')) {
            eventType = 'start_compute';
            const nodeMatch = description.match(/组\s(\d+)\s微批次\s(\d+)\s在节点\s(\d+)\s开始前向计算\s\(阶段\s(\d+)\)/);
            if (nodeMatch) {
              group = parseInt(nodeMatch[1]);
              batch = parseInt(nodeMatch[2]);
              sourceNode = parseInt(nodeMatch[3]);
            }
          } 
          // 检查是否是前向计算完成
          else if (description.includes('完成前向计算')) {
            eventType = 'end_compute';
            const nodeMatch = description.match(/组\s(\d+)\s微批次\s(\d+)\s在节点\s(\d+)\s完成前向计算\s\(阶段\s(\d+)\)/);
            if (nodeMatch) {
              group = parseInt(nodeMatch[1]);
              batch = parseInt(nodeMatch[2]);
              sourceNode = parseInt(nodeMatch[3]);
            }
          } 
          // 检查是否是反向计算开始
          else if (description.includes('开始反向计算')) {
            eventType = 'start_backward_compute';
            isBackward = true;
            const nodeMatch = description.match(/组\s(\d+)\s微批次\s(\d+)\s在节点\s(\d+)\s开始反向计算\s\(阶段\s(\d+)\)/);
            if (nodeMatch) {
              group = parseInt(nodeMatch[1]);
              batch = parseInt(nodeMatch[2]);
              sourceNode = parseInt(nodeMatch[3]);
            }
          } 
          // 检查是否是反向计算完成
          else if (description.includes('完成反向计算')) {
            eventType = 'end_backward_compute';
            isBackward = true;
            const nodeMatch = description.match(/组\s(\d+)\s微批次\s(\d+)\s在节点\s(\d+)\s完成反向计算\s\(阶段\s(\d+)\)/);
            if (nodeMatch) {
              group = parseInt(nodeMatch[1]);
              batch = parseInt(nodeMatch[2]);
              sourceNode = parseInt(nodeMatch[3]);
            }
          } 
          // 检查是否是前向数据到达
          else if (description.includes('前向数据到达')) {
            eventType = 'data_arrival';
            const nodeMatch = description.match(/组\s(\d+)\s微批次\s(\d+)\s前向数据到达\s阶段\s(\d+)\s节点\s(\d+)/);
            if (nodeMatch) {
              group = parseInt(nodeMatch[1]);
              batch = parseInt(nodeMatch[2]);
              targetNode = parseInt(nodeMatch[4]);
            }
          } 
          // 检查是否是传输启动
          else if (description.includes('传输启动')) {
            eventType = 'start_transfer';
            isBackward = description.includes('backward');
            const transferMatch = description.match(/(forward|backward)\s传输启动:\s(\d+)→(\d+)\s\(目标\s(\d+)\)\s([\d.]+)MB/);
            if (transferMatch) {
              sourceNode = parseInt(transferMatch[2]);
              targetNode = parseInt(transferMatch[3]);
              destNode = parseInt(transferMatch[4]);
              dataSize = parseFloat(transferMatch[5]);
            }
          } 
          // 检查是否是传输完成
          else if (description.includes('传输完成')) {
            eventType = 'end_transfer';
            isBackward = description.includes('backward');
            const transferMatch = description.match(/(forward|backward)\s传输完成:\s(\d+)→(\d+)\s\(([\d.]+)MB\)/);
            if (transferMatch) {
              sourceNode = parseInt(transferMatch[2]);
              targetNode = parseInt(transferMatch[3]);
              dataSize = parseFloat(transferMatch[4]);
            }
          } 
          // 检查是否是传输丢包
          else if (description.includes('传输丢包')) {
            eventType = 'packet_loss';
            isBackward = description.includes('backward');
            const transferMatch = description.match(/(forward|backward)\s传输丢包:\s(\d+)→(\d+)\s\(目标\s(\d+)\)\s([\d.]+)MB/);
            if (transferMatch) {
              sourceNode = parseInt(transferMatch[2]);
              targetNode = parseInt(transferMatch[3]);
              destNode = parseInt(transferMatch[4]);
              dataSize = parseFloat(transferMatch[5]);
            }
          } 
          // 检查是否是微批次完成
          else if (description.includes('完成所有计算')) {
            eventType = 'complete_batch';
            const completeMatch = description.match(/组\s(\d+)\s微批次\s(\d+)\s完成所有计算，总耗时:\s([\d.]+)s/);
            if (completeMatch) {
              group = parseInt(completeMatch[1]);
              batch = parseInt(completeMatch[2]);
            }
          } 
          // 检查是否是Ring-AllReduce开始
          else if (description.includes('开始Ring-AllReduce')) {
            eventType = 'start_ring_allreduce';
            const ringMatch = description.match(/组\s(\d+)\s开始Ring-AllReduce梯度聚合/);
            if (ringMatch) {
              group = parseInt(ringMatch[1]);
            }
          } 
          // 检查是否是Ring通信
          else if (description.includes('Ring-')) {
            eventType = 'ring_communication';
            const ringMatch = description.match(/(Ring-\w+):\s节点\s(\d+)\s发送分块\s(\d+)\s到节点\s(\d+)\s\(迭代\s(\d+)\)/);
            if (ringMatch) {
              const ringType = ringMatch[1]; // Ring-Gather 或 Ring-Reduce
              sourceNode = parseInt(ringMatch[2]);
              const chunkId = parseInt(ringMatch[3]);
              targetNode = parseInt(ringMatch[4]);
              const iteration = parseInt(ringMatch[5]);
              
              const ringEvent = {
                timestamp,
                eventType,
                ringType,
                sourceNode,
                targetNode,
                chunkId,
                iteration,
                description
              };
              
              ringEvents.push(ringEvent);
              return; // 已处理Ring事件，跳过后续处理
            }
          }
          
          const event = {
            timestamp,
            eventType,
            description,
            group,
            batch,
            sourceNode,
            targetNode,
            destNode,
            dataSize,
            isBackward
          };
          
          // 根据是否是反向传播事件放入不同的数组
          if (isBackward) {
            backwardEvents.push(event);
          } else if (eventType === 'packet_loss' || eventType === 'complete_batch' || eventType === 'start_ring_allreduce') {
            statsEvents.push(event);
          } else {
            forwardEvents.push(event);
          }
        }
      } else if (parsingStats) {
        // 解析统计信息
        // 可以根据需要添加统计信息的解析
        const statsMatch = line.match(/(链路利用率|批次完成时间|丢包事件|重传事件|总仿真时间):\s(.*)/);
        if (statsMatch) {
          const statType = statsMatch[1];
          const statValue = statsMatch[2];
          
          const statsEvent = {
            eventType: 'stats',
            statType,
            statValue,
            description: line
          };
          
          statsEvents.push(statsEvent);
        }
      }
    });
    
    res.json({ 
      stagesConfig, 
      events: {
        forward: forwardEvents,
        backward: backwardEvents,
        ring: ringEvents,
        stats: statsEvents
      }
    });
  } catch (error) {
    console.error('Error reading simulation data:', error);
    res.status(500).send('Error fetching simulation results');
  }
});


// 读取拓扑结构数据
app.get('/api/topology', (req, res) => {
  try {
    // 获取拓扑文件名参数
    const filename = req.query.file || 'fattree.txt';
    const topologyData = fs.readFileSync(path.join(__dirname,path.join("topo", filename)), 'utf8');
    const lines = topologyData.trim().split('\n');
    const nodes = [];
    const links = [];

    // 创建邻接矩阵
    const matrix = [];
    for (let i = 0; i < lines.length; i++) {
      const row = lines[i].trim().split(/\s+/).map(Number);
      matrix.push(row);
    }

    // 创建节点
    const nodeCount = matrix.length;
    for (let i = 0; i < nodeCount; i++) {
      nodes.push({
        id: i,
        // 可以根据需要添加其他节点属性
        type: 'node',
      });
    }
    
    // 从邻接矩阵创建连接
    for (let i = 0; i < nodeCount; i++) {
      for (let j = 0; j < nodeCount; j++) {
        if (matrix[i][j] > 0) {
          links.push({
            source: i,
            target: j,
            bandwidth: matrix[i][j] // 使用矩阵中的值作为带宽
          });
        }
      }
    }

    res.json({ nodes, links });
  } catch (error) {
    console.error('Error reading topology data:', error);
    res.status(500).send('Error fetching topology data');
  }
});

// 添加: 获取日志内容的API端点
app.get('/api/log', (req, res) => {
  try {
    // 获取日志文件名参数
    const filename = req.query.file;
    
    if (!filename) {
      return res.status(400).send('文件名参数缺失');
    }
    
    // 构建日志文件的完整路径
    const logFilePath = path.join(__dirname, 'results', filename);
    
    // 检查文件是否存在
    if (!fs.existsSync(logFilePath)) {
      return res.status(404).send(`文件 ${filename} 不存在`);
    }
    
    // 读取日志文件内容
    const logContent = fs.readFileSync(logFilePath, 'utf8');
    
    // 直接返回日志内容作为文本
    res.type('text/plain').send(logContent);
  } catch (error) {
    console.error('获取日志内容时出错:', error);
    res.status(500).send(`获取日志内容时出错: ${error.message}`);
  }
});

// 新增: 运行Python仿真器的API端点
app.post('/api/run_simulation', (req, res) => {
  try {
    // 获取配置参数
    const config = req.body;
    
    // 生成唯一的输出文件名
    const timestamp = new Date().toISOString().replace(/[:.]/g, '').substring(0, 15);
    const outputFile = path.join(__dirname, 'results', `simulation_${timestamp}.txt`);
    const configFile = path.join(__dirname, 'config', `config_${timestamp}.yaml`);

    // 确保目录存在
    fs.mkdirSync(path.join(__dirname, 'results'), { recursive: true });
    fs.mkdirSync(path.join(__dirname, 'config'), { recursive: true });
    
    // 首先安装 networkx
    console.log("开始安装 networkx...");
    const pythonScheduler1 = spawn(
      path.join(__dirname, 'myenv/bin/pip'),
      ['install', 'networkx']
    );
    
    pythonScheduler1.stderr.on('data', (data) => {
      console.error(`pip 安装错误: ${data}`);
    });
    
    // 等待 pip 安装完成后再运行调度器
    pythonScheduler1.on('close', (code) => {
      if (code !== 0) {
        return res.status(500).json({
          success: false,
          error: `networkx 安装失败，错误代码: ${code}`
        });
      }
      
      console.log("networkx 安装成功，开始运行调度器...");
      let schedulerOutput = '';
      
      // 运行调度器
      const pythonScheduler = spawn(
        path.join(__dirname, 'myenv/bin/python'),
        [
          path.join(__dirname, 'run_scheduler.py'),
          config.topology_file,
          config.scheduling_mode,
          config.compute_times.length.toString(),
          config.data_parallel_size.toString(),
        ]
      );
      
      
      pythonScheduler.stdout.on('data', (data) => {
        schedulerOutput += data.toString();
        console.log(`调度器输出: ${data}`);
      });
      
      pythonScheduler.stderr.on('data', (data) => {
        console.error(`调度器错误: ${data}`);
      });
      
      // 等待调度器完成
      pythonScheduler.on('close', (code) => {
        if (code !== 0) {
          return res.status(500).json({
            success: false,
            error: `调度器失败，错误代码: ${code}`
          });
        }
        
        try {
          // 确保输出不为空
          const trimmedOutput = schedulerOutput.trim();
          console.log("调度器完整输出:", trimmedOutput);
          
          if (!trimmedOutput) {
            return res.status(500).json({
              success: false,
              error: "调度器没有产生输出"
            });
          }
          
          // 解析调度器输出
          const groups = JSON.parse(trimmedOutput);
          
          // 更新配置中的分组信息
          config.groups = groups;
          
          // 将配置写入临时YAML文件
          fs.writeFileSync(configFile, yaml.dump(config));
          
          console.log(`运行仿真，配置文件: ${configFile}, 输出文件: ${outputFile}`);
          
          // 运行仿真器
          const pythonProcess = spawn(
            path.join(__dirname, 'myenv/bin/python'), 
            [
              path.join(__dirname, 'simulator.py'),
              configFile,
              outputFile
            ]
          );
          
          let stdoutData = '';
          let stderrData = '';
          
          // 收集标准输出
          pythonProcess.stdout.on('data', (data) => {
            stdoutData += data.toString();
            console.log(`仿真器输出: ${data}`);
          });
          
          // 收集标准错误
          pythonProcess.stderr.on('data', (data) => {
            stderrData += data.toString();
            console.error(`仿真器错误: ${data}`);
          });
          
          // 进程结束时的处理
          pythonProcess.on('close', (code) => {
            console.log(`仿真器进程退出，代码: ${code}`);
            
            if (code !== 0) {
              // 仿真失败
              return res.status(500).json({
                success: false,
                error: `仿真失败，错误代码: ${code}`,
                stderr: stderrData
              });
            }
            
            // 仿真成功，返回结果文件名
            console.log(`仿真完成，结果文件: ${outputFile}`);
            res.json({
              success: true,
              resultFile: path.basename(outputFile),
              topologyFile: config.topology_file,
              message: '仿真完成'
            });
          });
        } catch (error) {
          console.error('解析调度器输出时出错:', error);
          return res.status(500).json({
            success: false,
            error: `解析调度器输出失败: ${error.message}`,
            rawOutput: schedulerOutput
          });
        }
      });
    });
  } catch (error) {
    console.error('运行仿真时出错:', error);
    res.status(500).json({
      success: false,
      error: error.message
    });
  }
});

// 新增: 获取可用拓扑文件列表
app.get('/api/available_topologies', (req, res) => {
  try {
    const topoDir = path.join(__dirname, 'topo'); // 指定topo目录路径
    
    const files = fs.readdirSync(topoDir).filter(file => 
      file.endsWith('.txt')
    );
    
    res.json({
      topologies: files
    });
  } catch (error) {
    console.error('获取拓扑文件列表时出错:', error);
    res.status(500).json({
      error: error.message
    });
  }
});

// 新增: 获取可用仿真结果文件列表
app.get('/api/available_results', (req, res) => {
  try {
    const resultsDir = path.join(__dirname, 'results');
    
    // 确保目录存在
    if (!fs.existsSync(resultsDir)) {
      fs.mkdirSync(resultsDir, { recursive: true });
    }
    
    const files = fs.readdirSync(resultsDir).filter(file => 
      file.startsWith('simulation_') && 
      file.endsWith('.txt')
    );
    
    // 按修改时间排序，最新的在前
    const sortedFiles = files.map(file => ({
      name: file,
      time: fs.statSync(path.join(resultsDir, file)).mtime.getTime()
    }))
    .sort((a, b) => b.time - a.time)
    .map(file => file.name);
    
    res.json({
      results: sortedFiles
    });
  } catch (error) {
    console.error('获取仿真结果文件列表时出错:', error);
    res.status(500).json({
      error: error.message
    });
  }
});

app.listen(PORT, () => {
  console.log(`服务器运行在 http://localhost:${PORT}`);
});
