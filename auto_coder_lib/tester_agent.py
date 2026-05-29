"""
独立测试代理
负责编写和运行测试（流式输出+实时Token计数+全量日志）
"""
import os
import threading
import time
from pathlib import Path
from langchain_claude_code import ChatClaudeCode
from .config import Config
from .logger import get_task_logger

class TesterAgent:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.llm = ChatClaudeCode(
            cli_path=Config.CLAUDE_CODE_CLI_PATH,
            temperature=Config.TESTER_TEMPERATURE,
            timeout=Config.TASK_TIMEOUT,
            work_dir=str(self.project_path)
        )

    @staticmethod
    def count_tokens(text: str) -> int:
        """全局统一Token计算规则"""
        return len(text) // 4

    def test(self, task: dict, dev_result: dict) -> dict:
        """执行测试任务 - 流式输出 + 实时Token进度"""
        logger = get_task_logger(task["id"])
        task_name = task['name']
        task_id = task['id']

        logger.info("=" * 80)
        logger.info(f"🧪 启动测试任务 | 实时Token日志已开启")
        logger.info(f"任务ID：{task_id}")
        logger.info(f"任务名称：{task_name}")
        logger.info("=" * 80)

        if not dev_result["success"]:
            logger.error("❌ 开发任务失败，跳过测试")
            return {"success": False, "error": "开发任务未完成"}

        # 构建测试提示词
        prompt = f"""
# 测试任务执行
## 任务信息
ID：{task_id} | 名称：{task_name}
描述：{task['description']}

## 开发结果
修改文件：{dev_result['files_modified']}
开发报告：{dev_result['report'][:2000]}...

## 测试要求
1. 编写单元测试/集成测试
2. 运行测试并验证功能
3. 输出严格的测试报告
4. 明确标记测试通过/失败
        """

        prompt_tokens = self.count_tokens(prompt)
        logger.info(f"📝 测试提示词总Token：{prompt_tokens}")

        full_response = []
        current_tokens = 0
        ESTIMATED_RESPONSE_TOKENS = 30000
        stop_event = threading.Event()

        # 实时进度线程
        def progress_monitor():
            while not stop_event.is_set():
                time.sleep(1)
                if current_tokens > 0:
                    logger.debug(
                        f"📊 测试实时进度：已生成 {current_tokens} Token / 预估总 {ESTIMATED_RESPONSE_TOKENS} Token"
                    )

        monitor_thread = threading.Thread(target=progress_monitor, daemon=True)
        monitor_thread.start()

        try:
            logger.info("🔍 开始流式调用 ClaudeCode，执行测试中...")
            logger.info("--------------------------------------------------")

            for chunk in self.llm.stream(prompt):
                if chunk.content:
                    full_response.append(chunk.content)
                    current_tokens = self.count_tokens("".join(full_response))
                    logger.debug(f"✍️ 测试实时生成：{chunk.content.strip()[:100]}...")

            final_response = "".join(full_response)
            generated_tokens = self.count_tokens(final_response)
            total_tokens = prompt_tokens + generated_tokens
            test_passed = "测试通过" in final_response or "所有测试用例通过" in final_response

            logger.info("--------------------------------------------------")
            logger.info(f"✅ 测试任务完成 | 结果：{'通过' if test_passed else '失败'}")
            logger.info(f"📊 用量统计 | 提示词：{prompt_tokens} | 生成：{generated_tokens} | 总计：{total_tokens}")
            logger.debug(f"测试报告预览：{final_response[:800]}...")

            return {
                "success": test_passed,
                "report": final_response,
                "test_passed": test_passed,
                "token_usage": {
                    "prompt_tokens": prompt_tokens,
                    "generated_tokens": generated_tokens,
                    "total_tokens": total_tokens
                }
            }

        except Exception as e:
            logger.error(f"❌ 测试执行失败：{str(e)}", exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            stop_event.set()
            monitor_thread.join()
            logger.info(f"🏁 测试任务流程结束：{task_name}\n")