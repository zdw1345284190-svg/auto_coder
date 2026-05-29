"""
开发代理
增强版：支持测试失败自动迭代修复 + 接收测试报告针对性改代码
流式输出+实时Token+全量日志 完全保留
"""
import os
import threading
import time
from pathlib import Path
from langchain_claude_code import ChatClaudeCode
from .config import Config
from .logger import get_task_logger

class DeveloperAgent:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.llm = ChatClaudeCode(
            cli_path=Config.CLAUDE_CODE_CLI_PATH,
            temperature=Config.DEVELOPER_TEMPERATURE,
            timeout=Config.TASK_TIMEOUT,
            work_dir=str(self.project_path)
        )

    @staticmethod
    def count_tokens(text: str) -> int:
        """全局统一Token计算规则"""
        return len(text) // 4

    def develop(self, task: dict, context: dict, test_report: str = "", is_fix: bool = False) -> dict:
        """
        执行开发任务
        :param task: 任务信息
        :param context: 项目全局上下文
        :param test_report: 上一轮测试报告（失败原因）
        :param is_fix: 是否为【修复模式】
        """
        logger = get_task_logger(task["id"])
        task_name = task['name']
        task_id = task['id']

        logger.info("=" * 80)
        if is_fix:
            logger.info(f"🔧 启动【代码修复任务】| 基于测试报告迭代")
        else:
            logger.info(f"🚀 启动【全新开发任务】")
        logger.info(f"任务ID：{task_id}")
        logger.info(f"任务名称：{task_name}")
        logger.info("=" * 80)

        # ========== 区分提示词：正常开发 / 修复开发 ==========
        if not is_fix:
            # 首次开发提示词
            prompt = f"""
# 全新开发任务执行
## 任务基本信息
任务ID：{task_id}
任务名称：{task_name}
任务描述：{task['description']}

## 项目上下文
项目概述：{context.get('project_overview', '无')}
技术栈：{context.get('tech_stack', '无')}
项目架构：{context.get('architecture', '无')}

## 开发要求
1. 工作目录：{self.project_path}
2. 编写可运行、规范、带注释的代码
3. 自动创建/修改项目文件
4. 完成后输出开发总结报告
            """
        else:
            # 修复模式提示词（核心：基于测试报告改BUG）
            prompt = f"""
# 代码修复迭代任务
## 任务信息
任务ID：{task_id}
任务名称：{task_name}
原始需求：{task['description']}

## 项目上下文
项目概述：{context.get('project_overview', '无')}
技术栈：{context.get('tech_stack', '无')}

## 【重要】上一轮测试失败报告（必须根据此内容修复）
{test_report}

## 修复要求
1. 工作目录：{self.project_path}，**基于现有代码修改，不要全部重写**
2. 逐条分析测试报告中的错误、BUG、不满足需求的点
3. 精准定位问题代码并修复，保证功能符合需求
4. 修复后保证代码规范、可运行、注释完整
5. 输出本次修复说明：修改了哪些文件、修复了哪些问题
            """

        prompt_tokens = self.count_tokens(prompt)
        logger.info(f"📝 提示词总Token：{prompt_tokens}")
        logger.debug(f"提示词内容预览：{prompt[:500]}...")

        full_response = []
        current_tokens = 0
        ESTIMATED_RESPONSE_TOKENS = 50000
        stop_event = threading.Event()

        # 实时进度监控线程
        def progress_monitor():
            while not stop_event.is_set():
                time.sleep(1)
                if current_tokens > 0:
                    logger.debug(
                        f"📊 实时进度：已生成 {current_tokens} Token / 预估总 {ESTIMATED_RESPONSE_TOKENS} Token"
                    )

        monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
        monitor_thread.start()

        try:
            if is_fix:
                logger.info("🔧 流式调用 ClaudeCode，正在修复代码BUG...")
            else:
                logger.info("🔧 流式调用 ClaudeCode，实时生成代码中...")
            logger.info("--------------------------------------------------")

            for chunk in self.llm.stream(prompt):
                if chunk.content:
                    full_response.append(chunk.content)
                    current_tokens = self.count_tokens("".join(full_response))
                    logger.debug(f"✍️ 实时生成片段：{chunk.content.strip()[:100]}...")

            final_response = "".join(full_response)
            total_generated_tokens = self.count_tokens(final_response)
            total_tokens = prompt_tokens + total_generated_tokens

            logger.info("--------------------------------------------------")
            logger.info(f"✅ {'代码修复完成' if is_fix else '开发任务完成'}！")
            logger.info(f"📊 用量统计 | 提示词：{prompt_tokens} | 生成：{total_generated_tokens} | 总计：{total_tokens}")

            modified_files = self._get_modified_files()
            logger.info(f"📁 本次任务修改文件数：{len(modified_files)}")
            for f in modified_files[:10]:
                logger.debug(f"已修改文件：{f}")

            return {
                "success": True,
                "report": final_response,
                "files_modified": modified_files,
                "token_usage": {
                    "prompt_tokens": prompt_tokens,
                    "generated_tokens": total_generated_tokens,
                    "total_tokens": total_tokens
                }
            }

        except Exception as e:
            logger.error(f"❌ {'代码修复' if is_fix else '开发任务'}执行失败！错误：{str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            stop_event.set()
            monitor_thread.join()
            logger.info(f"🏁 流程结束：{task_name}\n")

    def _get_modified_files(self) -> list:
        """获取所有修改的文件"""
        modified_files = []
        try:
            for root, _, filenames in os.walk(self.project_path):
                if any(p in root for p in ['.git', '__pycache__', '.venv', 'logs']):
                    continue
                for filename in filenames:
                    if filename.startswith('.'):
                        continue
                    modified_files.append(str(Path(root) / filename))
        except Exception as e:
            get_task_logger("dev").warning(f"获取文件列表失败：{e}")
        return modified_files