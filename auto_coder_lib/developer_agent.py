"""
开发代理：全新开发 / 迭代修复双模式
特性：实时Token进度、完整报告不截断、自动保存MD报告、绑定工作目录
优化：增强动作日志，记录每个关键操作
"""
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from langchain_claude_code import ChatClaudeCode
from .config import Config
from .logger import get_task_logger, LogContext

class DeveloperAgent:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.project_path.mkdir(parents=True, exist_ok=True)

        self.llm = ChatClaudeCode(
            cli_path=Config.CLAUDE_CODE_CLI_PATH,
            temperature=Config.DEVELOPER_TEMPERATURE,
            timeout=Config.TASK_TIMEOUT,
            work_dir=str(self.project_path)
        )

    @staticmethod
    def count_tokens(text: str) -> int:
        return len(text) // 4

    def develop(self, task: dict, context: dict, test_report: str = "", is_fix: bool = False) -> dict:
        logger = get_task_logger(task["id"])
        task_id = task["id"]
        task_name = task["name"]

        logger.info("=" * 80)
        if is_fix:
            logger.info(f"🔧 代码修复任务 | 任务ID：{task_id}")
            logger.info(f"🔧 修复目标：解决测试失败问题")
        else:
            logger.info(f"🚀 全新开发任务 | 任务ID：{task_id}")
            logger.info(f"🚀 开发目标：{task_name}")
        logger.info(f"工作目录：{self.project_path}")
        logger.info("=" * 80)

        # 构造提示词，强制限定工作目录
        if not is_fix:
            prompt = f"""
# 全新开发任务
任务ID：{task_id}
任务名称：{task_name}
任务描述：{task['description']}

项目概述：{context.get('project_overview', '无')}
技术栈：{context.get('tech_stack', '无')}
项目架构：{context.get('architecture', '无')}

强制规则：
1. 工作目录固定为 {self.project_path}，所有文件、命令仅在此目录执行
2. 依赖使用 npm install / pip install 本地安装，禁止全局安装
3. 完成后输出完整开发总结报告
"""
        else:
            prompt = f"""
# 代码迭代修复任务
任务ID：{task_id}
任务名称：{task_name}
原始需求：{task['description']}

项目概述：{context.get('project_overview', '无')}
技术栈：{context.get('tech_stack', '无')}

上一轮测试报错报告：
{test_report}

强制规则：
1. 工作目录固定为 {self.project_path}
2. 基于现有代码修复，不要全量重写
3. 根据报错逐条修复，完成后输出详细修复说明
"""

        prompt_tokens = self.count_tokens(prompt)
        logger.info(f"📝 提示词构建完成，Token：{prompt_tokens}")
        logger.info("🔧 开始流式执行开发任务，实时生成代码...")

        full_response = []
        current_tokens = 0
        ESTIMATED_RESPONSE_TOKENS = 50000
        stop_event = threading.Event()

        def progress_monitor():
            while not stop_event.is_set():
                time.sleep(1)
                if current_tokens > 0:
                    progress_pct = min(100, int(current_tokens / ESTIMATED_RESPONSE_TOKENS * 100))
                    logger.debug(f"📊 实时进度：{current_tokens} Token / 预估 {ESTIMATED_RESPONSE_TOKENS} Token ({progress_pct}%)")

        monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
        monitor_thread.start()

        try:
            logger.info("--------------------------------------------------")
            for chunk in self.llm.stream(prompt):
                if chunk.content:
                    full_response.append(chunk.content)
                    current_tokens = self.count_tokens("".join(full_response))
                    logger.debug(f"✍️ 实时片段：{chunk.content.strip()}")

            final_report = "".join(full_response)
            gen_tokens = self.count_tokens(final_report)
            total_tokens = prompt_tokens + gen_tokens

            logger.info("--------------------------------------------------")
            logger.info(f"✅ {'修复完成' if is_fix else '开发完成'}")
            logger.info(f"📊 用量：提示词{prompt_tokens} | 生成{gen_tokens} | 总计{total_tokens}")

            # 扫描修改文件，记录动作
            modified_files = self._scan_modified_files()
            logger.info(f"📁 本次修改文件共 {len(modified_files)} 个：")
            for f in modified_files[:10]:  # 只显示前10个，避免日志过长
                logger.info(f"  - {f}")
            if len(modified_files) > 10:
                logger.info(f"  ... 还有 {len(modified_files)-10} 个文件")

            # 保存完整报告到日志目录，记录动作
            save_path = self._save_report(task_id, task_name, final_report, is_fix)
            logger.info(f"📄 开发报告已保存：{save_path}")

            return {
                "success": True,
                "report": final_report,
                "files_modified": modified_files,
                "token_usage": {
                    "prompt_tokens": prompt_tokens,
                    "generated_tokens": gen_tokens,
                    "total_tokens": total_tokens
                }
            }

        except Exception as e:
            logger.error(f"❌ 执行失败：{str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            stop_event.set()
            monitor_thread.join()
            logger.info(f"🏁 流程结束：{task_name}\n")

    def _scan_modified_files(self) -> list:
        """扫描项目目录下文件，排除缓存/依赖"""
        file_list = []
        exclude_dirs = {".git", "__pycache__", ".venv", "logs", "node_modules"}
        for root, _, files in os.walk(self.project_path):
            if any(d in root for d in exclude_dirs):
                continue
            for name in files:
                if not name.startswith("."):
                    file_list.append(str(Path(root) / name))
        return file_list

    def _save_report(self, task_id: str, task_name: str, content: str, is_fix: bool):
        """保存MD格式报告"""
        typ = "修复报告" if is_fix else "开发报告"
        filename = f"dev_report_{task_id[:8]}_{typ}.md"
        save_path = LogContext.current_dir / filename
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        md_content = f"""# {typ} - {task_name}
任务ID：{task_id}
生成时间：{now}

---
{content}
"""
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(md_content)
        return save_path