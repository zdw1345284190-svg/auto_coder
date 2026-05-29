"""
LangGraph工作流定义
增强版：支持测试失败自动迭代修复 + 测试报告闭环传递
"""
import json
from pathlib import Path
from langgraph.graph import StateGraph, END
from typing import TypedDict, List, Dict, Any, Optional

from .config import Config
from .logger import setup_logger
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
    
    project_understanding = ProjectUnderstanding(docs_path, project_path)
    task_splitter = TaskSplitter()
    developer = DeveloperAgent(project_path)
    tester = TesterAgent(project_path)
    
    def understand_project(state: State) -> State:
        logger.info("步骤: 理解项目")
        ui.show_info("正在理解项目需求...")
        
        understanding = project_understanding.generate_understanding()
        
        with open(Path("logs") / "project_understanding.json", "w", encoding="utf-8") as f:
            json.dump(understanding, f, ensure_ascii=False, indent=2)
            
        ui.show_success("项目理解完成")
        return {**state, "project_understanding": understanding, "status": "understanding_complete"}
        
    def split_tasks(state: State) -> State:
        logger.info("步骤: 拆分任务")
        ui.show_info("正在拆分开发任务...")
        
        tasks = task_splitter.split_tasks(state["project_understanding"])
        
        with open(Path("logs") / "tasks.json", "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
            
        ui.show_success(f"任务拆分完成")
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
        current_index = state["current_task_index"]
        fix_iter = state.get("fix_iter_count", 0)
        last_report = state.get("last_test_report", "")
        is_fix_mode = state.get("last_test_failed", False)

        current_task = _get_next_leaf_task(tasks, current_index)
        
        if not current_task:
            logger.info("✅ 所有任务已全部执行完成")
            return {**state, "status": "all_tasks_complete"}
            
        logger.info(f"👉 处理任务: {current_task['name']} (ID: {current_task['id']})")
        if is_fix_mode:
            logger.info(f"🔧 当前为【迭代修复模式】，第 {fix_iter + 1} 轮修复")
            ui.show_info(f"测试失败，开始第 {fix_iter + 1} 轮代码修复: {current_task['name']}")
        else:
            ui.show_info(f"正常执行任务: {current_task['name']}")

        current_task["status"] = "running"
        
        dev_result = developer.develop(
            task=current_task,
            context=state["project_understanding"],
            test_report=last_report,
            is_fix=is_fix_mode
        )
        
        if not dev_result["success"]:
            current_task["status"] = "failed"
            return {
                **state,
                "status": "task_failed",
                "current_task": current_task,
                "error": dev_result["error"]
            }
            
        test_result = tester.test(current_task, dev_result)
        current_task["dev_result"] = dev_result
        current_task["test_result"] = test_result

        if test_result["success"]:
            current_task["status"] = "success"
            current_task["progress"] = 100
            ui.show_success(f"✅ 任务完成: {current_task['name']}")
            return {
                **state,
                "current_task_index": current_index + 1,
                "fix_iter_count": 0,
                "last_test_report": "",
                "last_test_failed": False,
                "status": "task_complete"
            }
        
        max_fix = getattr(Config, "MAX_FIX_ITER", 5)
        new_fix_iter = fix_iter + 1
        logger.warning(f"❌ 测试失败！当前修复迭代次数: {new_fix_iter}/{max_fix}")
        ui.show_warning(f"测试不通过，准备自动修复 (迭代 {new_fix_iter}/{max_fix})")

        if new_fix_iter < max_fix:
            current_task["status"] = "pending"
            return {
                **state,
                "fix_iter_count": new_fix_iter,
                "last_test_report": test_result.get("report", ""),
                "last_test_failed": True,
                "status": "need_fix"
            }
        else:
            logger.error(f"⚠️ 已达到最大修复迭代次数 {max_fix}，停止自动修复")
            current_task["status"] = "failed"
            return {
                **state,
                "current_task": current_task,
                "error": f"测试多次失败，已达最大修复迭代次数 {max_fix}",
                "status": "task_failed"
            }

    def handle_failure(state: State) -> State:
        current_task = state["current_task"]
        retry_count = state.get("retry_count", 0)
        
        logger.warning(f"任务最终失败: {current_task['name']}，全局重试次数: {retry_count}")
        ui.show_error(f"任务执行失败: {current_task['name']}")
        
        if retry_count < Config.MAX_RETRIES:
            ui.show_info(f"将在5秒后全局重试 (第 {retry_count + 1} 次)")
            import time
            time.sleep(5)
            
            current_task["status"] = "pending"
            return {
                **state,
                "retry_count": retry_count + 1,
                "fix_iter_count": 0,
                "last_test_report": "",
                "last_test_failed": False,
                "status": "retry"
            }
        else:
            action = ui.wait_for_user_intervention(
                current_task["id"],
                current_task["name"],
                state.get("error", "未知错误")
            )
            
            if action == "retry":
                current_task["status"] = "pending"
                return {
                    **state,
                    "retry_count": 0,
                    "fix_iter_count": 0,
                    "last_test_report": "",
                    "last_test_failed": False,
                    "status": "retry"
                }
            elif action == "skip":
                current_task["status"] = "skipped"
                return {
                    **state,
                    "current_task_index": state["current_task_index"] + 1,
                    "fix_iter_count": 0,
                    "last_test_report": "",
                    "last_test_failed": False,
                    "status": "skip"
                }
            elif action == "continue":
                current_task["status"] = "success"
                return {
                    **state,
                    "current_task_index": state["current_task_index"] + 1,
                    "fix_iter_count": 0,
                    "last_test_report": "",
                    "last_test_failed": False,
                    "status": "continue"
                }
            elif action == "abort":
                raise KeyboardInterrupt("用户终止执行")

    def generate_docs(state: State) -> State:
        logger.info("📚 开始生成项目使用说明文档...")
        ui.show_info("正在生成使用说明、部署指南...")
        gen = DocGenerator(state["project_path"], state["docs_path"])
        gen.generate_all_docs(state["project_understanding"], state["tasks"])
        ui.show_success("✅ 所有使用文档已生成到你的docx目录")
        return {**state, "status": "docs_generated"}
        
    def _get_next_leaf_task(tasks: list, start_index: int) -> Optional[dict]:
        for task in tasks:
            if task.get("is_leaf", False) and task["status"] == "pending":
                return task
            if "children" in task:
                leaf_task = _get_next_leaf_task(task["children"], 0)
                if leaf_task:
                    return leaf_task
        return None
        
    def _save_progress(state: State):
        progress = {
            "tasks": state["tasks"],
            "current_task_index": state["current_task_index"],
            "project_understanding": state["project_understanding"],
            "fix_iter_count": state.get("fix_iter_count", 0),
            "last_test_report": state.get("last_test_report", ""),
            "last_test_failed": state.get("last_test_failed", False)
        }
        
        with open(Path("logs") / "progress.json", "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
            
    workflow = StateGraph(State)
    
    workflow.add_node("understand_project", understand_project)
    workflow.add_node("split_tasks", split_tasks)
    workflow.add_node("execute_task", execute_task)
    workflow.add_node("handle_failure", handle_failure)
    workflow.add_node("generate_docs", generate_docs)
    
    workflow.set_entry_point("understand_project")
    workflow.add_edge("understand_project", "split_tasks")
    workflow.add_edge("split_tasks", "execute_task")
    
    workflow.add_conditional_edges(
        "execute_task",
        lambda state: state["status"],
        {
            "task_complete": "execute_task",
            "need_fix": "execute_task",
            "task_failed": "handle_failure",
            "all_tasks_complete": "generate_docs"
        }
    )

    workflow.add_conditional_edges(
        "handle_failure",
        lambda state: state["status"],
        {
            "retry": "execute_task",
            "skip": "execute_task",
            "continue": "execute_task"
        }
    )

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
        initial_state = {
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
        
        if resume:
            progress_file = Path("logs") / "progress.json"
            if progress_file.exists():
                self.logger.info("从上次中断处恢复执行...")
                with open(progress_file, "r", encoding="utf-8") as f:
                    progress = json.load(f)
                initial_state.update(progress)
                self.ui.show_info(f"已恢复执行，当前任务索引: {initial_state['current_task_index']}")
            else:
                self.logger.warning("未找到进度文件，从头开始执行")
                
        self.app.invoke(initial_state)