"""
LangGraph 工作流
完整流程：项目理解 → 任务拆分 → 执行任务(开发+测试+迭代修复) → 生成交付文档 → 结束
优化：JSON文件保存路径修正到项目日志目录
"""
import json
from pathlib import Path
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any, Optional

from .config import Config
from .logger import setup_logger, LogContext
from .project_understanding import ProjectUnderstanding
from .task_splitter import TaskSplitter
from .developer_agent import DeveloperAgent
from .tester_agent import TesterAgent
from .user_interaction import UserInteraction
from .doc_generator import DocGenerator

class State(TypedDict):
    docs_path: str
    project_path: str
    project_understanding: Dict[str, Any]
    tasks: List[Dict[str, Any]]
    current_task_index: int
    retry_count: int
    fix_iter_count: int
    last_test_report: str
    last_test_failed: bool
    results: Dict[str, Any]
    status: str

def create_workflow(docs_path: str, project_path: str, ui: UserInteraction) -> "Workflow":
    logger = setup_logger("workflow")
    proj_understand = ProjectUnderstanding(docs_path, project_path)
    task_split = TaskSplitter()
    dev_agent = DeveloperAgent(project_path)
    test_agent = TesterAgent(project_path)

    def understand_project(state: State) -> State:
        logger.info("步骤：项目理解")
        ui.show_info("正在分析项目需求与代码结构...")
        res = proj_understand.generate_understanding()

        # 修正：使用LogContext.current_dir替代硬编码的logs/
        with open(LogContext.current_dir / "project_understanding.json", "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        logger.info(f"📄 项目理解JSON已保存：{LogContext.current_dir / 'project_understanding.json'}")

        ui.show_success("项目理解完成")
        return {**state, "project_understanding": res, "status": "understanding_complete"}

    def split_tasks(state: State) -> State:
        logger.info("步骤：任务拆分")
        ui.show_info("正在拆分开发任务...")
        tasks = task_split.split_tasks(state["project_understanding"])

        # 修正：使用LogContext.current_dir替代硬编码的logs/
        with open(LogContext.current_dir / "tasks.json", "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        logger.info(f"📄 任务列表JSON已保存：{LogContext.current_dir / 'tasks.json'}")

        ui.show_success("任务拆分完成")
        ui.show_task_progress(tasks)
        return {
            **state,
            "tasks": tasks,
            "current_task_index": 0,
            "fix_iter_count": 0,
            "last_test_report": "",
            "last_test_failed": False,
            "status": "tasks_split"
        }

    def execute_task(state: State) -> State:
        tasks = state["tasks"]
        curr_idx = state["current_task_index"]
        fix_iter = state.get("fix_iter_count", 0)
        test_report = state.get("last_test_report", "")
        is_fix = state.get("last_test_failed", False)

        def get_leaf_task(task_list: list) -> Optional[dict]:
            for t in task_list:
                if t.get("is_leaf") and t["status"] == "pending":
                    return t
                if "children" in t:
                    child = get_leaf_task(t["children"])
                    if child:
                        return child
            return None

        curr_task = get_leaf_task(tasks)
        if not curr_task:
            logger.info("✅ 所有业务任务执行完毕")
            return {**state, "status": "all_tasks_complete"}

        logger.info(f"👉 执行任务：{curr_task['name']}")
        if is_fix:
            logger.info(f"🔧 迭代修复模式，第 {fix_iter+1} 轮")
            ui.show_warning(f"测试失败，开始第{fix_iter+1}轮修复")
        else:
            ui.show_info(f"执行任务：{curr_task['name']}")

        curr_task["status"] = "running"
        dev_res = dev_agent.develop(
            task=curr_task,
            context=state["project_understanding"],
            test_report=test_report,
            is_fix=is_fix
        )

        if not dev_res["success"]:
            curr_task["status"] = "failed"
            return {
                **state,
                "status": "task_failed",
                "current_task": curr_task,
                "error": dev_res["error"]
            }

        test_res = test_agent.test(curr_task, dev_res)
        curr_task["dev_result"] = dev_res
        curr_task["test_result"] = test_res

        if test_res["success"]:
            curr_task["status"] = "success"
            curr_task["progress"] = 100
            ui.show_success(f"✅ 任务完成：{curr_task['name']}")
            return {
                **state,
                "current_task_index": curr_idx + 1,
                "fix_iter_count": 0,
                "last_test_report": "",
                "last_test_failed": False,
                "status": "task_complete"
            }

        # 测试失败，进入迭代修复
        max_fix = Config.MAX_FIX_ITER
        new_fix = fix_iter + 1
        logger.warning(f"❌ 测试失败，修复迭代 {new_fix}/{max_fix}")

        if new_fix < max_fix:
            curr_task["status"] = "pending"
            return {
                **state,
                "fix_iter_count": new_fix,
                "last_test_report": test_res["report"],
                "last_test_failed": True,
                "status": "need_fix"
            }
        else:
            logger.error(f"⚠️ 达到最大修复次数 {max_fix}，停止自动修复")
            curr_task["status"] = "failed"
            return {
                **state,
                "current_task": curr_task,
                "error": f"测试多次失败，已达最大修复次数 {max_fix}",
                "status": "task_failed"
            }

    def handle_failure(state: State) -> State:
        curr_task = state["current_task"]
        retry_cnt = state.get("retry_count", 0)
        logger.warning(f"任务最终失败：{curr_task['name']}，全局重试次数：{retry_cnt}")
        ui.show_error(f"任务执行失败：{curr_task['name']}")

        if retry_cnt < Config.MAX_RETRIES:
            ui.show_info("5秒后自动重试...")
            import time
            time.sleep(5)
            curr_task["status"] = "pending"
            return {
                **state,
                "retry_count": retry_cnt + 1,
                "fix_iter_count": 0,
                "last_test_report": "",
                "last_test_failed": False,
                "status": "retry"
            }

        # 达到最大重试，等待人工干预
        action = ui.wait_for_user_intervention(
            curr_task["id"], curr_task["name"], state.get("error", "未知错误")
        )
        if action == "retry":
            curr_task["status"] = "pending"
            return {**state, "retry_count": 0, "status": "retry"}
        elif action == "skip":
            curr_task["status"] = "skipped"
            return {**state, "current_task_index": state["current_task_index"]+1, "status": "skip"}
        elif action == "continue":
            curr_task["status"] = "success"
            return {**state, "current_task_index": state["current_task_index"]+1, "status": "continue"}
        elif action == "abort":
            raise KeyboardInterrupt("用户终止程序")

    def generate_docs(state: State) -> State:
        """业务任务全部完成后，自动生成交付文档"""
        logger.info("📚 开始生成项目交付文档")
        ui.show_info("正在生成使用说明、部署文档...")
        doc_gen = DocGenerator(state["project_path"], state["docs_path"])
        doc_gen.generate_all_docs(state["project_understanding"], state["tasks"])
        ui.show_success("交付文档全部生成完成")
        return {**state, "status": "docs_generated"}

    # 构建工作流
    workflow = StateGraph(State)
    workflow.add_node("understand_project", understand_project)
    workflow.add_node("split_tasks", split_tasks)
    workflow.add_node("execute_task", execute_task)
    workflow.add_node("handle_failure", handle_failure)
    workflow.add_node("generate_docs", generate_docs)

    workflow.set_entry_point("understand_project")
    workflow.add_edge("understand_project", "split_tasks")
    workflow.add_edge("split_tasks", "execute_task")

    # 任务执行分支跳转
    workflow.add_conditional_edges(
        "execute_task",
        lambda s: s["status"],
        {
            "task_complete": "execute_task",
            "need_fix": "execute_task",
            "task_failed": "handle_failure",
            "all_tasks_complete": "generate_docs"
        }
    )

    # 故障处理分支跳转
    workflow.add_conditional_edges(
        "handle_failure",
        lambda s: s["status"],
        {
            "retry": "execute_task",
            "skip": "execute_task",
            "continue": "execute_task"
        }
    )

    # 文档生成完成，流程结束
    workflow.add_edge("generate_docs", END)
    app = workflow.compile()

    return Workflow(app, docs_path, project_path, ui)

class Workflow:
    def __init__(self, app, docs_path: str, project_path: str, ui: UserInteraction):
        self.app = app
        self.docs_path = docs_path
        self.project_path = project_path
        self.ui = ui
        self.logger = setup_logger("workflow")

    def run(self, resume: bool = False):
        init_state = {
            "docs_path": self.docs_path,
            "project_path": self.project_path,
            "project_understanding": None,
            "tasks": [],
            "current_task_index": 0,
            "retry_count": 0,
            "fix_iter_count": 0,
            "last_test_report": "",
            "last_test_failed": False,
            "results": {},
            "status": "initializing"
        }

        # 断点续跑
        progress_file = LogContext.current_dir / "progress.json"
        if resume and progress_file.exists():
            self.logger.info("🔄 断点续跑：加载历史进度")
            with open(progress_file, "r", encoding="utf-8") as f:
                progress_data = json.load(f)
            init_state.update(progress_data)
            self.ui.show_info(f"已恢复至任务索引：{init_state['current_task_index']}")

        # 保存进度回调
        def save_progress(state):
            data = {
                "tasks": state["tasks"],
                "current_task_index": state["current_task_index"],
                "project_understanding": state["project_understanding"],
                "fix_iter_count": state.get("fix_iter_count", 0),
                "last_test_report": state.get("last_test_report", ""),
                "last_test_failed": state.get("last_test_failed", False)
            }
            with open(progress_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        # 执行工作流
        self.app.invoke(init_state)
        save_progress(init_state)