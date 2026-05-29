"""
递归任务拆分器
将项目拆分为可在200万上下文内处理的小任务（流式+实时Token+全量日志）
"""
import uuid
import threading
import time
from langchain_claude_code import ChatClaudeCode
from .config import Config
from .logger import setup_logger

class TaskSplitter:
    def __init__(self):
        self.logger = setup_logger("task_splitter")
        self.llm = ChatClaudeCode(
            cli_path=Config.CLAUDE_CODE_CLI_PATH,
            temperature=0.1,
            timeout=Config.TASK_TIMEOUT
        )

    @staticmethod
    def count_tokens(text: str) -> int:
        """全局统一Token计算规则"""
        return len(text) // 4

    def split_tasks(self, project_understanding: dict) -> list:
        """递归拆分任务"""
        self.logger.info("=" * 80)
        self.logger.info("📋 开始递归拆分项目任务")
        self.logger.info("=" * 80)

        root_task = {
            "id": str(uuid.uuid4()),
            "name": "项目整体开发",
            "description": "完成整个项目的开发、测试和验收",
            "type": "root",
            "children": [],
            "status": "pending",
            "progress": 0
        }

        # 递归拆分（最大深度5层）
        self._split_recursive(root_task, project_understanding, depth=0)
        total_tasks = self._count_tasks(root_task)

        self.logger.info("=" * 80)
        self.logger.info(f"任务拆分完成！总计生成【{total_tasks}】个可执行叶子任务")
        self.logger.info("=" * 80)
        return [root_task]

    def _split_recursive(self, task: dict, context: dict, depth: int):
        """增强版递归拆分，强制拆分直到任务足够小"""
        MAX_SPLIT_DEPTH = 5
        if depth >= MAX_SPLIT_DEPTH:
            self.logger.debug(f"✅ 达到最大拆分深度({MAX_SPLIT_DEPTH})，标记为叶子任务: {task['name']}")
            task["is_leaf"] = True
            return

        task_size = self._estimate_task_size(task, context)
        threshold = Config.MAX_CONTEXT_LENGTH * 0.1
        self.logger.debug(f"任务: {task['name']} | 估算大小: {task_size} | 阈值: {threshold} | 深度: {depth}")

        if task_size > threshold:
            self.logger.info(f"🔍 任务过大，触发自动拆分: {task['name']}")
            sub_tasks = self._split_with_llm(task, context)

            if not sub_tasks:
                self.logger.warning(f"⚠️ LLM拆分失败，使用兜底拆分方案")
                sub_tasks = [
                    {
                        "name": f"{task['name']} - 核心功能实现",
                        "description": f"实现{task['name']}的核心业务逻辑、数据结构、主流程"
                    },
                    {
                        "name": f"{task['name']} - 辅助功能与工具",
                        "description": f"实现{task['name']}的工具函数、配置、辅助模块"
                    },
                    {
                        "name": f"{task['name']} - 测试与验收",
                        "description": f"编写{task['name']}的测试用例、验证功能、生成验收报告"
                    }
                ]

            for sub_task in sub_tasks:
                sub_task["id"] = str(uuid.uuid4())
                sub_task["parent_id"] = task["id"]
                sub_task["children"] = []
                sub_task["status"] = "pending"
                sub_task["progress"] = 0
                task["children"].append(sub_task)
                self.logger.info(f"📌 生成子任务: {sub_task['name']}")
                self._split_recursive(sub_task, context, depth + 1)
        else:
            self.logger.debug(f"✅ 任务大小符合要求，标记为叶子任务: {task['name']}")
            task["is_leaf"] = True

    def _estimate_task_size(self, task: dict, context: dict) -> int:
        """精准任务上下文大小估算"""
        desc_tokens = len(task["description"]) // 4
        context_tokens = len(str(context)) // 4
        safe_buffer = 5000
        return desc_tokens + context_tokens + safe_buffer

    def _split_with_llm(self, task: dict, context: dict) -> list:
        """LLM拆分子任务（流式+实时Token日志）"""
        self.logger.info("--------------------------------------------------")
        self.logger.info(f"🤖 调用 LLM 拆分子任务：{task['name']}")

        prompt = f"""
# 任务拆分要求
请将以下大任务拆分为 **独立、可执行、可测试** 的小任务，
每个任务必须能在 {int(Config.MAX_CONTEXT_LENGTH/10000)}万 token 上下文内完成。

## 父任务信息
任务名称：{task['name']}
任务描述：{task['description']}

## 项目上下文
{context.get('project_overview', '无项目概述')}
技术栈：{context.get('tech_stack', '未知')}

## 输出格式（纯JSON数组，无多余内容）
[
    {{
        "name": "任务名称",
        "description": "详细任务描述"
    }}
]
        """

        prompt_tokens = self.count_tokens(prompt)
        self.logger.info(f"📝 拆分提示词 Token：{prompt_tokens}")
        self.logger.debug(f"提示词预览：{prompt[:500]}...")

        full_response = []
        current_tokens = 0
        ESTIMATED_RESPONSE_TOKENS = 20000
        stop_event = threading.Event()

        # 实时进度线程
        def progress_monitor():
            while not stop_event.is_set():
                time.sleep(1)
                if current_tokens > 0:
                    self.logger.debug(
                        f"📊 任务拆分进度：已生成 {current_tokens} Token / 预估总 {ESTIMATED_RESPONSE_TOKENS} Token"
                    )

        monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
        monitor_thread.start()

        try:
            self.logger.info("🔄 流式接收拆分结果...")
            for chunk in self.llm.stream(prompt):
                if chunk.content:
                    full_response.append(chunk.content)
                    current_tokens = self.count_tokens("".join(full_response))
                    self.logger.debug(f"✍️ 实时片段：{chunk.content.strip()[:120]}...")

            final_content = "".join(full_response)
            generated_tokens = self.count_tokens(final_content)
            total_tokens = prompt_tokens + generated_tokens

            self.logger.info(f"📊 用量统计 | 提示词：{prompt_tokens} | 生成：{generated_tokens} | 总计：{total_tokens}")
            self.logger.info("✅ 子任务拆分完成")

            import json
            return json.loads(final_content)

        except Exception as e:
            self.logger.error(f"❌ LLM 拆分任务失败：{str(e)}", exc_info=True)
            return []
        finally:
            stop_event.set()
            monitor_thread.join()
            self.logger.info("--------------------------------------------------\n")

    def _count_tasks(self, task: dict) -> int:
        """统计所有叶子任务数量"""
        if task.get("is_leaf", False):
            return 1
        count = 0
        for child in task["children"]:
            count += self._count_tasks(child)
        return count