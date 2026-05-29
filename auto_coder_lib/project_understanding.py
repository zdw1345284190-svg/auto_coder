"""
项目理解模块【终极正确版】
✅ 不再用Python读取所有文件！
✅ 让ClaudeCode自己访问项目、自己读文件、自己分析！
✅ 提示词极小，永不超长，100%不崩溃
"""
import os
import threading
import time
import json
from pathlib import Path
from langchain_claude_code import ChatClaudeCode
from .config import Config
from .logger import setup_logger

class ProjectUnderstanding:
    def __init__(self, docs_path: str, project_path: str):
        self.docs_path = Path(docs_path) if docs_path else None
        self.project_path = Path(project_path)
        self.logger = setup_logger("project_understanding")
        self.llm = ChatClaudeCode(
            cli_path=Config.CLAUDE_CODE_CLI_PATH,
            temperature=0.1,
            timeout=Config.TASK_TIMEOUT,
            work_dir=str(self.project_path)
        )

    @staticmethod
    def count_tokens(text: str) -> int:
        return len(text) // 4

    @staticmethod
    def clean_json_content(content: str) -> str:
        if not content:
            return ""
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()

    def generate_understanding(self) -> dict:
        """【正确方式】让ClaudeCode自己分析项目，无需Python读文件"""
        self.logger.info("=" * 80)
        self.logger.info("📚 【正确模式】让 ClaudeCode 自己分析项目")
        self.logger.info("=" * 80)

        # 🔥 核心：极简提示词，只告诉路径，让模型自己读！
        prompt = f"""
你是项目分析助手。

项目信息：
- 需求文档目录：{self.docs_path}
- 项目代码目录：{self.project_path}

请你自己遍历目录、读取文件、分析项目。
严格只返回标准JSON，不要任何多余文字、解释、markdown。

返回字段：
project_overview, core_features, tech_stack, architecture, existing_modules, missing_features, potential_issues, development_priorities
"""

        prompt_tokens = self.count_tokens(prompt)
        self.logger.info(f"📝 提示词 Token：{prompt_tokens} (极小，永不超长)")

        full_response = []
        current_tokens = 0
        stop_event = threading.Event()

        def progress_monitor():
            while not stop_event.is_set():
                time.sleep(1)
                if current_tokens > 0:
                    self.logger.debug(f"📊 实时生成：{current_tokens} Token")

        monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
        monitor_thread.start()

        try:
            self.logger.info("🔍 ClaudeCode 正在自己分析项目...")
            for chunk in self.llm.stream(prompt):
                if chunk.content:
                    full_response.append(chunk.content)
                    current_tokens = self.count_tokens("".join(full_response))

            final_content = "".join(full_response)
            cleaned_content = self.clean_json_content(final_content)
            
            generated_tokens = self.count_tokens(cleaned_content)
            self.logger.info(f"✅ 分析完成 | 总Token：{prompt_tokens + generated_tokens}")

            # 解析失败自动返回默认值
            try:
                return json.loads(cleaned_content)
            except:
                self.logger.error("❌ 解析失败，使用默认项目结构")
                return self._default()

        except Exception as e:
            self.logger.error(f"❌ 执行失败：{str(e)}")
            return self._default()
        finally:
            stop_event.set()
            monitor_thread.join()
            self.logger.info("🏁 项目理解完成\n")

    def _default(self):
        return {
            "project_overview": "自动分析项目",
            "core_features": [],
            "tech_stack": {},
            "architecture": "未知",
            "existing_modules": [],
            "missing_features": [],
            "potential_issues": [],
            "development_priorities": []
        }