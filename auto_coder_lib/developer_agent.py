"""
开发代理（修复版：强制绑定项目工作目录）
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
        # 确保项目目录存在
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        # 关键修复：初始化时就绑定项目工作目录
        self.llm = ChatClaudeCode(
            cli_path=Config.CLAUDE_CODE_CLI_PATH,
            temperature=Config.DEVELOPER_TEMPERATURE,
            timeout=Config.TASK_TIMEOUT,
            work_dir=str(self.project_path)  # 强制绑定项目目录
        )

    @staticmethod
    def count_tokens(text: str) -> int:
        return len(text) // 4

    def develop(self, task: dict, context: dict, test_report: str = "", is_fix: bool = False) -> dict:
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
        logger.info(f"项目工作目录：{self.project_path}")
        logger.info("=" * 80)

        # 关键修复：在提示词中再次强调工作目录，避免模型执行全局命令
        if not is_fix:
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

## 【强制要求】工作目录与依赖管理
1. **当前工作目录固定为：{self.project_path}**
2. 所有文件操作、命令执行必须在此目录下进行
3. 安装依赖时，必须使用 `npm install` / `pip install` 且不指定全局参数，依赖会自动安装到当前目录
4. 生成的所有文件必须保存在当前目录下，不要使用绝对路径

## 开发要求
1. 编写可运行、规范、带注释的代码
2. 自动创建/修改项目文件
3. 完成后输出开发总结报告
            """
        else:
            prompt = f"""
# 代码修复迭代任务
## 任务信息
任务ID：{task_id}
任务名称：{task_name}
原始需求：{task['description']}

## 项目上下文
项目概述：{context.get('project_overview', '无')}
技术栈：{context.get('tech_stack', '无')}

## 【强制要求】工作目录与依赖管理
1. **当前工作目录固定为：{self.project_path}**
2. 所有文件操作、命令执行必须在此目录下进行
3. 安装依赖时，必须使用 `npm install` / `pip install` 且不指定全局参数，依赖会自动安装到当前目录
4. 修改文件时，只修改当前目录下的文件，不要修改外部文件

## 【重要】上一轮测试失败报告（必须根据此内容修复）
{test_report}

## 修复要求
1. 基于现有代码修改，不要全部重写
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
        modified_files = []
        try:
            # 只扫描项目目录下的文件，不扫描根目录
            for root, _, filenames in os.walk(self.project_path):
                if any(p in root for p in ['.git', '__pycache__', '.venv', 'logs', 'node_modules']):
                    continue
                for filename in filenames:
                    if filename.startswith('.'):
                        continue
                    modified_files.append(str(Path(root) / filename))
        except Exception as e:
            get_task_logger("dev").warning(f"获取文件列表失败：{e}")
        return modified_files