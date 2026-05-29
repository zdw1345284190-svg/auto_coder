"""
项目理解模块
读取文档和现有代码，生成项目理解报告（流式+实时Token+全量日志）
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
            timeout=Config.TASK_TIMEOUT
        )

    @staticmethod
    def count_tokens(text: str) -> int:
        """全局统一Token计算规则"""
        return len(text) // 4

    @staticmethod
    def clean_json_content(content: str) -> str:
        """🔥 核心修复：清理模型返回的Markdown代码块标记，提取纯JSON"""
        if not content:
            return ""
        # 移除 ```json ``` 标记
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        # 再次清理空白字符
        return content.strip()

    def read_all_files(self, path: Path, extensions: list = None) -> dict:
        """读取目录下所有文件"""
        files = {}
        if not path.exists():
            return files
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    files[str(path)] = f.read()
            except:
                pass
            return files
        for root, _, filenames in os.walk(path):
            for filename in filenames:
                file_path = Path(root) / filename
                if extensions and file_path.suffix not in extensions:
                    continue
                if filename.startswith('.') or '.git' in file_path.parts or '__pycache__' in file_path.parts:
                    continue
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    files[str(file_path)] = content
                except Exception as e:
                    self.logger.warning(f"无法读取文件 {file_path}: {e}")
        return files

    def generate_understanding(self) -> dict:
        """生成项目理解报告 - 流式+实时Token日志"""
        self.logger.info("=" * 80)
        self.logger.info("📚 开始执行【项目理解】LLM 交互")
        self.logger.info("=" * 80)

        # 读取文档与代码
        self.logger.info("正在读取项目文档与现有代码...")
        docs_content = {}
        if self.docs_path:
            docs_content = self.read_all_files(self.docs_path)
        code_content = self.read_all_files(self.project_path, extensions=[
            '.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.html', '.css', '.md'
        ])

        # 构建提示词
        prompt = f"""
# 项目理解任务
请分析以下项目文档和现有代码，生成结构化JSON报告。

## 项目文档
{self._format_files(docs_content)}

## 现有代码
{self._format_files(code_content)}

## 输出要求
严格返回标准JSON，**不要加任何Markdown代码块（```json ```）**，包含以下字段：
1. project_overview: 项目整体概述
2. core_features: 核心功能列表
3. tech_stack: 技术栈分析
4. architecture: 项目架构
5. existing_modules: 现有模块分析
6. missing_features: 缺失的功能
7. potential_issues: 潜在问题
8. development_priorities: 开发优先级
"""

        # 统计提示词Token
        prompt_tokens = self.count_tokens(prompt)
        self.logger.info(f"📝 项目理解提示词 Token：{prompt_tokens}")
        self.logger.debug(f"提示词预览：{prompt[:600]}...")

        # 流式交互变量
        full_response = []
        current_tokens = 0
        ESTIMATED_RESPONSE_TOKENS = 40000
        stop_event = threading.Event()

        # 实时Token进度监控线程
        def progress_monitor():
            while not stop_event.is_set():
                time.sleep(1)
                if current_tokens > 0:
                    self.logger.debug(
                        f"📊 项目理解实时进度：已生成 {current_tokens} Token / 预估总 {ESTIMATED_RESPONSE_TOKENS} Token"
                    )

        monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
        monitor_thread.start()

        try:
            self.logger.info("🔍 流式调用 LLM 分析项目中...")
            self.logger.info("--------------------------------------------------")

            # 流式接收返回
            for chunk in self.llm.stream(prompt):
                if chunk.content:
                    full_response.append(chunk.content)
                    current_tokens = self.count_tokens("".join(full_response))
                    self.logger.debug(f"✍️ 实时片段：{chunk.content.strip()[:120]}...")

            # 拼接完整结果
            final_content = "".join(full_response)
            # 🔥 关键修复：清理JSON内容
            cleaned_content = self.clean_json_content(final_content)
            generated_tokens = self.count_tokens(cleaned_content)
            total_tokens = prompt_tokens + generated_tokens

            self.logger.info("--------------------------------------------------")
            self.logger.info("✅ 项目理解 LLM 交互完成")
            self.logger.info(f"📊 用量统计 | 提示词：{prompt_tokens} | 生成：{generated_tokens} | 总计：{total_tokens}")

            # 解析JSON（使用清理后的内容）
            understanding = json.loads(cleaned_content)
            self.logger.info("✅ JSON 报告解析成功")
            return understanding

        except json.JSONDecodeError as e:
            self.logger.error(f"❌ JSON 解析失败：{str(e)}", exc_info=True)
            self.logger.debug(f"原始返回内容：{final_content[:1000]}")
            self.logger.debug(f"清理后内容：{cleaned_content[:1000]}")
            # 解析失败返回默认结构，不中断流程
            return {
                "project_overview": "解析失败，使用默认任务",
                "core_features": [],
                "tech_stack": {},
                "architecture": "未知",
                "existing_modules": [],
                "missing_features": [],
                "potential_issues": [],
                "development_priorities": []
            }
        except Exception as e:
            self.logger.error(f"❌ 项目理解执行异常：{str(e)}", exc_info=True)
            raise
        finally:
            stop_event.set()
            monitor_thread.join()
            self.logger.info("🏁 项目理解流程结束\n")

    def _format_files(self, files: dict) -> str:
        """格式化文件内容"""
        if not files:
            return "无"
        content = []
        for path, text in files.items():
            content.append(f"### 文件: {path}\n\n{text[:10000]}...")
        return "\n\n".join(content)