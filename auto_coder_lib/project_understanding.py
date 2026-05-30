"""
项目理解模块
优化：不再Python手动读取拼接文件，交由Claude原生遍历，彻底解决上下文超限
内置JSON容错，解析失败自动返回默认结构
新增：生成结构化Markdown总结报告
"""
import threading
import time
import json
from pathlib import Path
from datetime import datetime
from langchain_claude_code import ChatClaudeCode
from .config import Config
from .logger import setup_logger, LogContext

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
        """统一Token计算规则"""
        return len(text) // 4

    @staticmethod
    def clean_json_content(content: str) -> str:
        """清洗Markdown代码块标记"""
        if not content:
            return ""
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        return content.strip()

    def _generate_understanding_report(self, data: dict):
        """生成项目理解Markdown总结报告"""
        report_path = LogContext.current_dir / "project_understanding_summary.md"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        content = f"""# 项目理解总结报告
生成时间：{now}
项目目录：{self.project_path}
需求文档目录：{self.docs_path}

---
## 1. 项目概述
{data.get('project_overview', '无')}

## 2. 核心功能
{chr(10).join([f"- {item}" for item in data.get('core_features', [])]) or '无'}

## 3. 技术栈
{chr(10).join([f"- {k}: {v}" for k, v in data.get('tech_stack', {}).items()]) or '无'}

## 4. 项目架构
{data.get('architecture', '无')}

## 5. 现有模块
{chr(10).join([f"- {item}" for item in data.get('existing_modules', [])]) or '无'}

## 6. 缺失功能
{chr(10).join([f"- {item}" for item in data.get('missing_features', [])]) or '无'}

## 7. 潜在问题
{chr(10).join([f"- {item}" for item in data.get('potential_issues', [])]) or '无'}

## 8. 开发优先级
{chr(10).join([f"- {item}" for item in data.get('development_priorities', [])]) or '无'}
"""
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)
        self.logger.info(f"📄 项目理解总结报告已生成：{report_path}")

    def generate_understanding(self) -> dict:
        self.logger.info("=" * 80)
        self.logger.info("📚 开始项目分析（Claude原生遍历文件）")
        self.logger.info("=" * 80)

        # 极简提示词，仅传递路径，由Claude自行读取文件
        prompt = f"""
请分析当前项目，严格只返回标准JSON，不要额外文字、注释、markdown格式。

需求文档目录：{self.docs_path}
项目代码目录：{self.project_path}

JSON字段要求：
project_overview, core_features, tech_stack, architecture, existing_modules, missing_features, potential_issues, development_priorities
"""

        prompt_tokens = self.count_tokens(prompt)
        self.logger.info(f"📝 提示词Token：{prompt_tokens}")

        full_response = []
        current_tokens = 0
        stop_event = threading.Event()

        # 实时进度监控
        def progress_monitor():
            while not stop_event.is_set():
                time.sleep(1)
                if current_tokens > 0:
                    self.logger.debug(f"📊 实时生成Token：{current_tokens}")

        monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
        monitor_thread.start()

        try:
            self.logger.info("🔍 Claude 正在自动分析项目...")
            for chunk in self.llm.stream(prompt):
                if chunk.content:
                    full_response.append(chunk.content)
                    current_tokens = self.count_tokens("".join(full_response))

            final_content = "".join(full_response)
            cleaned_content = self.clean_json_content(final_content)
            generated_tokens = self.count_tokens(cleaned_content)
            self.logger.info(f"✅ 分析完成 | 总Token：{prompt_tokens + generated_tokens}")

            # JSON解析容错
            result = json.loads(cleaned_content)
            
            # 生成Markdown总结报告
            self._generate_understanding_report(result)
            
            return result

        except json.JSONDecodeError as e:
            self.logger.error(f"❌ JSON解析失败：{str(e)}，使用默认项目结构", exc_info=True)
            default = self._get_default_struct()
            self._generate_understanding_report(default)
            return default
        except Exception as e:
            self.logger.error(f"❌ 项目分析异常：{str(e)}", exc_info=True)
            default = self._get_default_struct()
            self._generate_understanding_report(default)
            return default
        finally:
            stop_event.set()
            monitor_thread.join()
            self.logger.info("🏁 项目理解流程结束\n")

    def _get_default_struct(self) -> dict:
        """解析/执行失败兜底结构，保证流程不中断"""
        return {
            "project_overview": "项目自动分析（解析失败兜底）",
            "core_features": [],
            "tech_stack": {},
            "architecture": "单体应用",
            "existing_modules": [],
            "missing_features": [],
            "potential_issues": [],
            "development_priorities": []
        }