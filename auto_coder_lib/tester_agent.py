"""
测试代理：自动化测试 + 完整报错报告 + 实时进度
修复：补充 threading / time 依赖，解决NameError
优化：增强动作日志，记录每个关键操作
"""
import threading
import time
from datetime import datetime
from pathlib import Path
from langchain_claude_code import ChatClaudeCode
from .config import Config
from .logger import setup_logger, LogContext

class TesterAgent:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.project_path.mkdir(parents=True, exist_ok=True)

        self.llm = ChatClaudeCode(
            cli_path=Config.CLAUDE_CODE_CLI_PATH,
            temperature=Config.TESTER_TEMPERATURE,
            timeout=Config.TASK_TIMEOUT,
            work_dir=str(self.project_path)
        )
        self.logger = setup_logger("tester")

    @staticmethod
    def count_tokens(text: str) -> int:
        return len(text) // 4

    def test(self, task: dict, dev_result: dict) -> dict:
        task_id = task["id"]
        task_name = task["name"]
        self.logger.info("=" * 80)
        self.logger.info(f"🧪 测试任务开始 | 任务ID：{task_id}")
        self.logger.info(f"🧪 测试目标：{task_name}")
        self.logger.info(f"工作目录：{self.project_path}")
        self.logger.info("=" * 80)

        prompt = f"""
# 自动化测试任务
任务ID：{task_id}
任务名称：{task_name}
需求描述：{task['description']}

工作目录固定为：{self.project_path}

开发结果：
{dev_result.get('report', '无开发内容')}

要求：
1. 执行完整测试，输出所有用例结果
2. 失败用例必须写明报错信息、堆栈、问题定位、修复建议
3. 输出完整测试报告，不可省略内容
"""

        prompt_tokens = self.count_tokens(prompt)
        self.logger.info(f"📝 测试提示词构建完成，Token：{prompt_tokens}")
        self.logger.info("🧪 开始执行自动化测试，准备用例...")

        full_response = []
        current_tokens = 0
        ESTIMATED_RESPONSE_TOKENS = 50000
        stop_event = threading.Event()

        # 实时进度线程
        def progress_monitor():
            while not stop_event.is_set():
                time.sleep(1)
                if current_tokens > 0:
                    progress_pct = min(100, int(current_tokens / ESTIMATED_RESPONSE_TOKENS * 100))
                    self.logger.debug(f"📊 测试进度：{current_tokens} Token / 预估 {ESTIMATED_RESPONSE_TOKENS} Token ({progress_pct}%)")

        monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
        monitor_thread.start()

        try:
            self.logger.info("🔍 正在执行测试命令并生成报告...")
            self.logger.info("--------------------------------------------------")
            for chunk in self.llm.stream(prompt):
                if chunk.content:
                    full_response.append(chunk.content)
                    current_tokens = self.count_tokens("".join(full_response))
                    self.logger.debug(f"✍️ 测试片段：{chunk.content.strip()}")

            test_report = "".join(full_response)
            gen_tokens = self.count_tokens(test_report)
            total_tokens = prompt_tokens + gen_tokens

            self.logger.info("--------------------------------------------------")
            self.logger.info("✅ 测试交互完成")
            self.logger.info(f"📊 用量：提示词{prompt_tokens} | 生成{gen_tokens} | 总计{total_tokens}")

            # 判断测试结果，记录动作
            success = "测试全部通过" in test_report or "all tests passed" in test_report.lower()
            self.logger.debug(f"📝 完整测试报告：\n{test_report}")

            # 保存测试报告文件，记录动作
            save_path = self._save_test_report(task_id, task_name, test_report, success)
            self.logger.info(f"📄 测试报告已保存：{save_path}")

            if success:
                self.logger.info("✅ 测试结果：全部通过，无失败用例")
            else:
                self.logger.error("❌ 测试结果：存在失败用例，详细信息见报告")

            return {"success": success, "report": test_report}

        except Exception as e:
            err_msg = f"测试执行异常：{str(e)}"
            self.logger.error(err_msg, exc_info=True)
            return {"success": False, "report": err_msg}
        finally:
            stop_event.set()
            monitor_thread.join()
            self.logger.info(f"🏁 测试流程结束：{task_name}\n")

    def _save_test_report(self, task_id: str, task_name: str, report: str, success: bool):
        status = "通过" if success else "失败"
        filename = f"test_report_{task_id[:8]}_{status}.md"
        save_path = LogContext.current_dir / filename
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        md = f"""# 测试报告 - {task_name}
任务ID：{task_id}
测试状态：{status}
生成时间：{now}

---
{report}
"""
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(md)
        return save_path