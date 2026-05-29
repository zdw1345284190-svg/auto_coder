"""
测试代理（修复版：实时进度 + 完整报告 + 缺失导入）
✅ 修复 threading 未定义报错
✅ 新增实时Token进度监控
✅ 完整测试报告保存 + 日志记录
"""
import threading  # 🔥 必加：修复报错核心
import time       # 🔥 必加：进度监控需要
from pathlib import Path
from langchain_claude_code import ChatClaudeCode
from .config import Config
from .logger import setup_logger, LogContext

class TesterAgent:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        # 强制绑定项目工作目录，避免根目录污染
        self.llm = ChatClaudeCode(
            cli_path=Config.CLAUDE_CODE_CLI_PATH,
            temperature=Config.TESTER_TEMPERATURE,
            timeout=Config.TASK_TIMEOUT,
            work_dir=str(self.project_path)
        )
        self.logger = setup_logger("tester")

    @staticmethod
    def count_tokens(text: str) -> int:
        """全局统一Token计算规则"""
        return len(text) // 4

    def test(self, task: dict, dev_result: dict) -> dict:
        task_id = task['id']
        task_name = task['name']
        self.logger.info(f"🧪 开始测试任务：{task_name}，工作目录：{self.project_path}")

        # 提示词：强制生成详细测试报告，包含错误详情
        prompt = f"""
# 自动化测试任务（强制生成完整报告）
## 任务信息
任务ID：{task_id}
任务名称：{task_name}
原始需求：{task['description']}

## 项目工作目录
当前工作目录固定为：{self.project_path}
所有测试命令、依赖安装必须在此目录下进行。

## 开发结果
{dev_result.get('report', '无开发报告')}

## 【强制要求】测试报告必须包含以下内容：
1. 测试用例执行情况（通过/失败的用例列表）
2. 所有失败用例的错误信息、报错堆栈
3. 问题定位：是代码错误、依赖问题还是环境问题
4. 修复建议：具体的修改方向和代码示例

## 输出格式
无论测试是否通过，都必须返回完整的测试报告，不要省略任何细节。
"""

        prompt_tokens = self.count_tokens(prompt)
        self.logger.info(f"📝 提示词总Token：{prompt_tokens}")

        full_response = []
        current_tokens = 0
        ESTIMATED_RESPONSE_TOKENS = 50000
        stop_event = threading.Event()

        # 实时进度监控线程
        def progress_monitor():
            while not stop_event.is_set():
                time.sleep(1)
                if current_tokens > 0:
                    self.logger.debug(
                        f"📊 测试实时进度：已生成 {current_tokens} Token / 预估总 {ESTIMATED_RESPONSE_TOKENS} Token"
                    )

        monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
        monitor_thread.start()

        try:
            self.logger.info("🔍 正在执行测试并生成报告...")
            self.logger.info("--------------------------------------------------")

            # 流式捕获测试生成内容，输出实时片段
            for chunk in self.llm.stream(prompt):
                if chunk.content:
                    full_response.append(chunk.content)
                    current_tokens = self.count_tokens("".join(full_response))
                    self.logger.debug(f"✍️ 测试实时生成片段：{chunk.content.strip()}")

            test_report = "".join(full_response)
            generated_tokens = self.count_tokens(test_report)
            total_tokens = prompt_tokens + generated_tokens

            self.logger.info("--------------------------------------------------")
            self.logger.info("✅ 测试交互完成")
            self.logger.info(f"📊 用量统计 | 提示词：{prompt_tokens} | 生成：{generated_tokens} | 总计：{total_tokens}")

            success = "测试全部通过" in test_report or "all tests passed" in test_report.lower()

            # 1. 日志记录完整测试报告
            self.logger.debug(f"📝 【测试报告完整内容】\n{test_report}")

            # 2. 自动保存测试报告文件到日志目录
            self._save_test_report(task_id, task_name, test_report, success)

            # 3. 记录结果到日志
            if success:
                self.logger.info(f"✅ 测试结果：通过")
            else:
                self.logger.error(f"❌ 测试结果：失败（详细报告已保存）")

            return {
                "success": success,
                "report": test_report
            }

        except Exception as e:
            error_msg = f"测试执行异常：{str(e)}"
            self.logger.error(f"❌ 测试执行失败：{error_msg}", exc_info=True)
            return {
                "success": False,
                "report": f"测试执行异常：{error_msg}"
            }
        finally:
            stop_event.set()
            monitor_thread.join()
            self.logger.info(f"🏁 测试流程结束：{task_name}\n")

    def _save_test_report(self, task_id: str, task_name: str, report: str, success: bool):
        """把测试报告保存为文件，和日志同目录"""
        status = "通过" if success else "失败"
        filename = f"test_report_{task_id[:8]}_{status}.md"
        report_path = LogContext.current_dir / filename

        content = f"""# 测试报告 - {task_name}
任务ID：{task_id}
测试状态：{status}
生成时间：{self._get_current_time()}

---

{report}
"""

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        self.logger.info(f"📄 测试报告已保存：{report_path}")

    def _get_current_time(self) -> str:
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")