<div align="center">

# 🎯 Agent Orchestrator

**轻量级多 Agent 编排框架 —— plan → delegate → execute → collect**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-4%2F4%20PASS-green)]()

</div>

> 一个简单、可扩展的多 Agent 编排框架：中央编排器（Orchestrator）协调**计划、执行、审查、安全**各阶段，子 Agent 各司其职，全程 token 敏感（只传聚焦任务，不传全量上下文）。
>
> 从 OpenCode Orchestrator 配置中提炼的轻量实现，配套 11 个专业 Agent 角色定义。

---

## 🏗️ 架构

```
┌─────────────────────────────────────────────┐
│              SimpleOrchestrator              │
│  plan → delegate → execute → collect        │
├─────────────────────────────────────────────┤
│                                              │
│  ┌──────────────┐   ┌──────────────────┐    │
│  │ PlanRunner   │   │ CodeExplorer     │    │
│  │ (制定计划)    │   │ (只读探索代码)    │    │
│  └──────────────┘   └──────────────────┘    │
│  ┌──────────────┐   ┌──────────────────┐    │
│  │ CodeExecutor │   │ SpecCritic       │    │
│  │ (执行实现)    │   │ (规范审查)       │    │
│  └──────────────┘   └──────────────────┘    │
│  ┌──────────────┐   ┌──────────────────┐    │
│  │ TestVerifier │   │ CodeReviewer     │    │
│  │ (测试验证)    │   │ (代码审查)       │    │
│  └──────────────┘   └──────────────────┘    │
│                                              │
│  并行执行 (ThreadPoolExecutor, 默认 4 workers) │
└─────────────────────────────────────────────┘
```

## ✨ 特性

### 核心框架（`agent_orchestrator.py`，576 行）
- **四步流程**：`plan()` 制定计划 → `delegate()` 并行委派 → `execute()` 执行 → `collect()` 收集结果
- **6 种 Agent 角色**：PlanRunner（计划）/ CodeExplorer（只读探索）/ CodeExecutor（实现）/ SpecCritic（规范审查）/ TestVerifier（测试）/ CodeReviewer（审查）
- **并行执行**：ThreadPoolExecutor 支持多任务并行，互不阻塞
- **安全执行**：`_execute_safe` 捕获异常、超时控制、失败隔离（单个 agent 失败不影响整体）
- **状态追踪**：每个 Task 有完整生命周期（pending → running → completed/failed），可查询统计

### Agent 角色定义（`agents/`，11 个）
完整的多 Agent 团队角色卡（OpenCode 格式）：
- **orchestrator**：总编排器（不直接写代码，只协调）
- **plan-runner / spec-critic**：计划与规范审查
- **code-explorer / code-executor**：探索与实现分离（读/写职责严格隔离）
- **code-reviewer / docs-reviewer / test-verifier**：三重验证
- **security-reviewer / host-security-investigator**：安全审查
- **api-docs-researcher**：外部 API 文档调研

### 技能系统（`skills/`）
- **agent-delegation**：任务委派机制
- **task-management**：任务管理 CLI + 迁移脚本（TypeScript）
- **pythonic-quality**：Python 代码质量规范
- **skill-creator**：技能自动创建/验证/打包
- **security-investigation**：VPS 安全扫描

## 🚀 快速开始

```bash
# 1. 运行完整演示（4 项测试）
python3 agent_orchestrator.py

# 2. 在自己的代码中使用
from agent_orchestrator import SimpleOrchestrator, AgentRole, Task

orch = SimpleOrchestrator(max_workers=4)
task = orch.plan("实现一个用户登录模块")
orch.delegate([task])
result = orch.execute_plan(task)
print(orch.report())
```

## ✅ 实测验证（4/4 测试通过）

```
✅ Test 1: 并行委派（plan-runner + code-explorer 同时执行）
✅ Test 2: 规范审查（SpecCritic 正确识别缺失的执行步骤）
✅ Test 3: 代码审查（CodeReviewer 检查代码问题）
✅ Test 4: 全流程管道（plan → delegate → execute → collect）
```

## 📁 目录结构

```
agent-orchestrator/
├── agent_orchestrator.py    # 核心编排框架 (576行)
├── AGENTS.md                # 全局 Agent 规则（角色分离/验证纪律）
├── agents/                  # 11 个 Agent 角色定义
│   ├── orchestrator.md
│   ├── plan-runner.md
│   ├── code-explorer.md
│   ├── code-executor.md
│   ├── code-reviewer.md
│   └── ...
├── skills/                  # 5 个可复用技能
│   ├── agent-delegation/
│   ├── task-management/
│   ├── pythonic-quality/
│   ├── skill-creator/
│   └── security-investigation/
├── examples/                # 示例文件
├── opencode.jsonc           # OpenCode 配置
└── package.json
```

## ⚙️ 设计理念

- **小而清晰**：不是通用 Agent 平台，是可理解、可修改的编排起点
- **Token 敏感**：子 Agent 只接收聚焦任务，不传全量上下文
- **职责分离**：探索（读）与实现（写）严格隔离，审查独立进行
- **审批门控**：非平凡任务先计划、用户批准后才实现
- **可扩展**：注册新 Agent 只需继承 `BaseAgent` 并 `register_agent()`

## 📄 License

[MIT](LICENSE)
