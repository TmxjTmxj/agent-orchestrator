"""
龙虾 — Simple Orchestrator

从 small_orchestrator 拆解提炼的轻量级 agent 编排框架。
实现 plan → delegate → execute → collect 四步流程。
支持子 agent 注册、任务分发、并行执行、结果收集。

参考:
  - small_orchestrator/agents/orchestrator.md (编排器设计)
  - small_orchestrator/agents/plan-runner.md (计划执行)
  - small_orchestrator/skills/agent-delegation/SKILL.md (委派机制)
"""
from __future__ import annotations
import os
import json, logging, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

logger = logging.getLogger("lobster.agent_orchestrator")

WORKSPACE = Path(os.environ.get("ORCH_WORKSPACE", Path.home() / ".orchestrator_plans"))
WORKSPACE.mkdir(parents=True, exist_ok=True)


# ── 任务与状态 ──────────────────────────────────────────────

class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class AgentRole(Enum):
    """映射自 small_orchestrator 的 11 种子 agent 角色"""
    ORCHESTRATOR = "orchestrator"
    PLAN_RUNNER = "plan-runner"
    CODE_EXPLORER = "code-explorer"
    CODE_EXECUTOR = "code-executor"
    SPEC_CRITIC = "spec-critic"
    API_RESEARCHER = "api-docs-researcher"
    TEST_VERIFIER = "test-verifier"
    CODE_REVIEWER = "code-reviewer"
    DOCS_REVIEWER = "docs-reviewer"
    SECURITY_REVIEWER = "security-reviewer"
    HOST_SECURITY_INVESTIGATOR = "host-security-investigator"


@dataclass
class Task:
    """一个可被 agent 执行的原子任务"""
    id: str = field(default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}")
    role: AgentRole = AgentRole.CODE_EXECUTOR
    description: str = ""
    scope: str = ""  # 如 "read-only" 或具体路径
    payload: Dict[str, Any] = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    dependencies: List[str] = field(default_factory=list)  # 前驱 task id 列表
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    priority: int = 0  # 越大越优先

    def to_dict(self) -> dict:
        return {
            "id": self.id, "role": self.role.value, "description": self.description[:60],
            "status": self.status.value, "error": self.error,
            "dependencies": self.dependencies,
        }


# ── 子 Agent 抽象 ──────────────────────────────────────────

class BaseAgent:
    """子 agent 基类。子类需实现 execute()。"""

    def __init__(self, role: AgentRole, name: str = ""):
        self.role = role
        self.name = name or role.value
        self.task_count = 0
        self.successes = 0
        self.failures = 0

    def execute(self, task: Task) -> Any:
        """执行一个任务。子类必须重写。"""
        raise NotImplementedError(f"{self.name} must implement execute()")

    def can_handle(self, task: Task) -> bool:
        """判断此 agent 是否能处理该任务"""
        return task.role == self.role

    @property
    def stats(self) -> dict:
        return {"name": self.name, "role": self.role.value,
                "tasks": self.task_count, "successes": self.successes, "failures": self.failures}


# ── 内置 Agent 实现 ─────────────────────────────────────────

class PlanRunnerAgent(BaseAgent):
    """计划执行 agent — 基于模板生成执行计划"""

    def execute(self, task: Task) -> Dict[str, Any]:
        goal = task.payload.get("goal", task.description)
        constraints = task.payload.get("constraints", "none")

        # 生成计划文件
        plan = {
            "goal": goal,
            "steps": [
                {"step": 1, "action": f"Investigate context for: {goal}", "by": "code-explorer"},
                {"step": 2, "action": f"Implement: {goal}", "by": "code-executor"},
                {"step": 3, "action": "Verify implementation", "by": "test-verifier"},
            ],
            "constraints": constraints,
            "risks": ["Unexpected side effects in related modules"],
            "acceptance": ["All tests pass", "No regressions"],
        }
        plan_path = WORKSPACE / f"plan_{task.id}.json"
        plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")

        return {"plan_path": str(plan_path), "steps": len(plan["steps"]), "plan": plan}


class CodeExplorerAgent(BaseAgent):
    """代码探索 agent — 只读，查找文件/符号"""

    def execute(self, task: Task) -> Dict[str, Any]:
        paths = task.payload.get("paths", [])
        query = task.payload.get("query", task.description)
        findings = []
        for p in paths:
            path_obj = Path(p).expanduser()
            if path_obj.exists():
                findings.append({"path": str(path_obj), "exists": True, "size": path_obj.stat().st_size})
            else:
                findings.append({"path": str(path_obj), "exists": False})
        return {"query": query, "findings": findings, "count": len(findings)}


class CodeExecutorAgent(BaseAgent):
    """代码执行 agent — 写文件/执行命令"""

    def execute(self, task: Task) -> Dict[str, Any]:
        action = task.payload.get("action", "write")
        if action == "write":
            filepath = task.payload.get("filepath", "")
            content = task.payload.get("content", "")
            p = Path(filepath).expanduser()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return {"action": "write", "filepath": str(p), "bytes": len(content)}
        elif action == "shell":
            import subprocess
            cmd = task.payload.get("command", "")
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            return {
                "action": "shell", "command": cmd,
                "returncode": result.returncode,
                "stdout": result.stdout[-500:],  # 截断避免爆内存
                "stderr": result.stderr[-200:],
            }
        return {"error": f"Unknown action: {action}"}


class SpecCriticAgent(BaseAgent):
    """规范批评 agent — 审查计划/需求的一致性"""

    def execute(self, task: Task) -> Dict[str, Any]:
        plan = task.payload.get("plan", {})
        issues = []
        if not plan.get("goal"):
            issues.append("Missing goal")
        if not plan.get("steps"):
            issues.append("No execution steps defined")
        if not plan.get("acceptance"):
            issues.append("No acceptance criteria")
        return {
            "approved": len(issues) == 0,
            "issues": issues,
            "suggestions": ["Add explicit file paths to each step"] if not issues else [],
        }


class TestVerifierAgent(BaseAgent):
    """测试验证 agent — 简单运行测试"""

    def execute(self, task: Task) -> Dict[str, Any]:
        test_path = task.payload.get("test_path", "")
        module = task.payload.get("module", "")
        results = []
        if test_path:
            import subprocess
            try:
                r = subprocess.run(["python3", "-m", "pytest", test_path, "-x", "-q"],
                                   capture_output=True, text=True, timeout=60)
                results.append({"test": test_path, "passed": r.returncode == 0, "output": r.stdout[-300:]})
            except Exception as e:
                results.append({"test": test_path, "passed": False, "error": str(e)})
        if module:
            try:
                import importlib, sys
                importlib.import_module(module)
                results.append({"test": f"import {module}", "passed": True})
            except Exception as e:
                results.append({"test": f"import {module}", "passed": False, "error": str(e)})
        return {"results": results, "all_passed": all(r["passed"] for r in results)}


class CodeReviewerAgent(BaseAgent):
    """代码审查 agent — 审查已完成的代码"""

    def execute(self, task: Task) -> Dict[str, Any]:
        paths = task.payload.get("paths", [])
        findings = []
        for p in paths:
            path_obj = Path(p).expanduser()
            if path_obj.exists():
                content = path_obj.read_text(encoding="utf-8")
                lines = content.split("\n")
                n = len(lines)
                # 简单静态检查
                issues = []
                if n > 500:
                    issues.append(f"File too long ({n} lines)")
                if "TODO" in content:
                    issues.append("Contains TODO markers")
                if "print(" in content:
                    issues.append("Contains debug print statements")
                findings.append({"path": p, "lines": n, "issues": issues})
        return {
            "findings": findings,
            "blocking": [f for f in findings for i in f["issues"] if "TODO" in i],
            "advisory": [f for f in findings for i in f["issues"] if "print" in i],
        }


# ── Agent 注册表 ──────────────────────────────────────────

AGENT_CLASSES: Dict[AgentRole, Type[BaseAgent]] = {
    AgentRole.PLAN_RUNNER: PlanRunnerAgent,
    AgentRole.CODE_EXPLORER: CodeExplorerAgent,
    AgentRole.CODE_EXECUTOR: CodeExecutorAgent,
    AgentRole.SPEC_CRITIC: SpecCriticAgent,
    AgentRole.TEST_VERIFIER: TestVerifierAgent,
    AgentRole.CODE_REVIEWER: CodeReviewerAgent,
}


def register_agent(role: AgentRole, agent_class: Type[BaseAgent]):
    """注册自定义 agent 类"""
    AGENT_CLASSES[role] = agent_class


# ── SimpleOrchestrator ────────────────────────────────

class SimpleOrchestrator:
    """
    轻量级 agent 编排器。

    用法:
        orch = SimpleOrchestrator()
        orch.register(PlanRunnerAgent())

        task = Task(role=AgentRole.PLAN_RUNNER, description="实现一个计算器")
        results = orch.execute_plan(task)

    """

    def __init__(self, max_workers: int = 4):
        self.agents: Dict[AgentRole, BaseAgent] = {}
        self._pool = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: List[Task] = []
        self._completed: List[Task] = []

    def register(self, agent: BaseAgent):
        """注册一个子 agent"""
        if agent.role == AgentRole.ORCHESTRATOR:
            logger.warning("Cannot register orchestrator as sub-agent")
            return
        self.agents[agent.role] = agent
        logger.info(f"Registered agent: {agent.name} ({agent.role.value})")

    def unregister(self, role: AgentRole):
        """移除注册的 agent"""
        self.agents.pop(role, None)

    def get_agent(self, role: AgentRole) -> Optional[BaseAgent]:
        """根据角色获取 agent 实例"""
        # 如果已注册，直接用
        if role in self.agents:
            return self.agents[role]
        # 否则尝试创建
        cls = AGENT_CLASSES.get(role)
        if cls:
            agent = cls(role)
            self.agents[role] = agent
            return agent
        logger.warning(f"No agent class registered for role: {role}")
        return None

    # ── Plan 阶段 ────────────────────────────────────────

    def plan(self, goal: str, constraints: Optional[Dict[str, Any]] = None) -> Task:
        """
        Phase A: 计划 — 让 plan-runner 生成执行计划
        """
        plan_task = Task(
            role=AgentRole.PLAN_RUNNER,
            description=f"Plan: {goal}",
            payload={"goal": goal, "constraints": constraints or {}},
        )
        self._tasks.append(plan_task)
        result = self._run_single(plan_task)
        return plan_task

    # ── Delegate 阶段 ────────────────────────────────────

    def delegate(self, tasks: List[Task]) -> List[Task]:
        """
        Phase B: 委派 — 将一批任务分发给合适的 agent 并行执行
        """
        futures: Dict[str, Future] = {}

        for task in tasks:
            if task.status != TaskStatus.PENDING:
                continue

            # 将任务纳入内部追踪
            if task not in self._tasks:
                self._tasks.append(task)

            # 检查依赖
            deps_done = all(
                t.status == TaskStatus.COMPLETED
                for t in self._completed + self._tasks
                if t.id in task.dependencies
            )
            if not deps_done:
                task.status = TaskStatus.BLOCKED
                continue

            agent = self.get_agent(task.role)
            if agent is None:
                task.status = TaskStatus.FAILED
                task.error = f"No agent for role {task.role}"
                continue

            task.status = TaskStatus.IN_PROGRESS
            future = self._pool.submit(self._execute_safe, agent, task)
            futures[task.id] = future

        for tid, future in futures.items():
            try:
                future.result()
            except Exception as e:
                t = next((t for t in tasks if t.id == tid), None)
                if t:
                    t.status = TaskStatus.FAILED
                    t.error = str(e)

        return tasks

    # ── Execute 阶段 ─────────────────────────────────────

    def execute(self, task: Task) -> Any:
        """
        Phase C: 执行单个任务（同步）
        """
        return self._run_single(task)

    # ── Collect 阶段 ─────────────────────────────────────

    def collect(self) -> List[Task]:
        """
        Phase D: 收集已完成的任务结果
        """
        done = [t for t in self._tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)]
        for t in done:
            if t not in self._completed:
                self._completed.append(t)
                self._tasks.remove(t)
        return self._completed

    # ── 四步一体化 ───────────────────────────────────────

    def execute_plan(self, task: Task) -> Dict[str, Any]:
        """
        全流程: plan → delegate → execute → collect
        支持单个 Task 或自动拆解为多步
        """
        step_results = []

        # Step 1: Plan
        logger.info(f"[ORCH] Planning: {task.description}")
        plan_result = self._run_single(Task(
            role=AgentRole.PLAN_RUNNER,
            description=f"Plan: {task.description}",
            payload={"goal": task.description, **task.payload},
        ))
        step_results.append({"phase": "plan", "result": plan_result.result})

        # Step 2: Delegate
        logger.info(f"[ORCH] Delegating: {task.description}")
        delegate_result = self._run_single(Task(
            role=AgentRole.CODE_EXECUTOR,
            description=task.description,
            payload=task.payload,
        ))
        step_results.append({"phase": "delegate", "result": delegate_result.result})

        # Step 3: Verify
        logger.info(f"[ORCH] Verifying: {task.description}")
        verify_result = self._run_single(Task(
            role=AgentRole.TEST_VERIFIER,
            description=f"Verify: {task.description}",
            payload={"module": task.payload.get("verify_module", "")},
        ))
        step_results.append({"phase": "verify", "result": verify_result.result})

        # Step 4: Review
        logger.info(f"[ORCH] Reviewing: {task.description}")
        paths = task.payload.get("review_paths", [])
        if paths:
            review_result = self._run_single(Task(
                role=AgentRole.CODE_REVIEWER,
                description=f"Review: {task.description}",
                payload={"paths": paths},
            ))
            step_results.append({"phase": "review", "result": review_result.result})

        return {"task_id": task.id, "steps": step_results}

    # ── 内部方法 ─────────────────────────────────────────

    def _run_single(self, task: Task) -> Task:
        """同步执行单个任务"""
        self._tasks.append(task)
        agent = self.get_agent(task.role)
        if agent is None:
            task.status = TaskStatus.FAILED
            task.error = f"No agent for role {task.role.value}"
            return task
        task.status = TaskStatus.IN_PROGRESS
        result = self._execute_safe(agent, task)
        return task

    def _execute_safe(self, agent: BaseAgent, task: Task) -> Any:
        """带错误处理的执行包装"""
        try:
            result = agent.execute(task)
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            agent.task_count += 1
            agent.successes += 1
            logger.info(f"[OK] {agent.name} completed task {task.id}")
            return result
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = time.time()
            agent.task_count += 1
            agent.failures += 1
            logger.error(f"[FAIL] {agent.name} failed task {task.id}: {e}")
            return None

    # ── 状态与报告 ───────────────────────────────────────

    def status(self) -> dict:
        return {
            "agents": {r.value: a.stats for r, a in self.agents.items()},
            "pending_tasks": len([t for t in self._tasks if t.status == TaskStatus.PENDING]),
            "in_progress": len([t for t in self._tasks if t.status == TaskStatus.IN_PROGRESS]),
            "completed": len(self._completed),
            "failed": len([t for t in self._completed if t.status == TaskStatus.FAILED]),
        }

    def report(self) -> str:
        """人类可读的状态报告"""
        s = self.status()
        lines = [
            "=== SimpleOrchestrator Status ===",
            f"  Agents: {len(self.agents)} registered",
            f"  Tasks: {s['pending_tasks']} pending, {s['in_progress']} running",
            f"  Completed: {s['completed']} (failed: {s['failed']})",
        ]
        for r, st in s["agents"].items():
            lines.append(f"    {r}: {st['tasks']} tasks ({st['successes']} ok / {st['failures']} fail)")
        return "\n".join(lines)


# ── CLI 测试入口 ─────────────────────────────────────────

def run_demo():
    """运行一个完整的四步流程演示"""
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    orch = SimpleOrchestrator(max_workers=2)

    # 注册所有 agent
    for role, cls in AGENT_CLASSES.items():
        try:
            orch.register(cls(role))
        except TypeError:
            pass

    logger.info("All agents registered")

    # ——— 测试案例 1: 并行委派 ———
    logger.info("\n=== Test 1: Parallel delegation ===")
    tasks = [
        Task(role=AgentRole.CODE_EXPLORER, description="Explore lobster directory",
             payload={"paths": [str(Path.cwd() / "examples" / "sample_file.py"),
                                str(Path.home() / ".lobster" / "needs.py")]}),
        Task(role=AgentRole.PLAN_RUNNER, description="Write a test plan",
             payload={"goal": "Add a math utility module", "constraints": {"lang": "python"}}),
    ]
    orch.delegate(tasks)
    results = orch.collect()
    for t in results:
        status_icon = "✅" if t.status == TaskStatus.COMPLETED else "❌"
        logger.info(f"  {status_icon} {t.role.value}: {t.description[:40]} | status={t.status.value}")

    # ——— 测试案例 2: 规范审查 ———
    logger.info("\n=== Test 2: Spec critic review ===")
    crit = SpecCriticAgent(AgentRole.SPEC_CRITIC)
    review = crit.execute(Task(
        payload={"plan": {"goal": "Do something", "steps": [],
                          "acceptance": []}}
    ))
    logger.info(f"  Approved: {review['approved']}, Issues: {review['issues']}")

    # ——— 测试案例 3: 代码审查 ———
    logger.info("\n=== Test 3: Code review ===")
    reviewer = CodeReviewerAgent(AgentRole.CODE_REVIEWER)
    review_result = reviewer.execute(Task(
        payload={"paths": [str(Path.cwd() / "examples" / "sample_file.py")]}
    ))
    for f in review_result["findings"]:
        logger.info(f"  {f['path']}: {f['lines']} lines, {len(f['issues'])} issues")

    # ——— 测试案例 4: 全流程 execute_plan ———
    logger.info("\n=== Test 4: Full pipeline ===")
    full_task = Task(
        role=AgentRole.CODE_EXECUTOR,
        description="Create a greeting script",
        payload={
            "action": "write",
            "filepath": str(Path.cwd() / "_test_greeting.py"),
            "content": "def greet(name):\n    return f'Hello, {name}!'\n\nprint(greet('Orchestrator'))\n",
            "verify_module": "_test_greeting",
            "review_paths": [str(Path.cwd() / "_test_greeting.py")],
        }
    )
    pipeline_result = orch.execute_plan(full_task)
    logger.info(f"  Pipeline steps: {len(pipeline_result['steps'])}")

    # ——— 清理测试文件 ———
    test_file = Path.home() / ".lobster" / "_test_greeting.py"
    if test_file.exists():
        test_file.unlink()
        logger.info("  Cleaned up test file")

    print("\n" + orch.report())
    print("\n✅ Demo completed successfully!")


if __name__ == "__main__":
    run_demo()
