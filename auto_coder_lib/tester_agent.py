"""
测试代理（修复版：强制绑定项目工作目录）
"""
from pathlib import Path
from langchain_claude_code import ChatClaudeCode
from .config import Config
from .logger import setup_logger

class TesterAgent:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)
        self.project_path.mkdir(parents=True, exist_ok=True)
        
        # 关键修复：初始化时绑定项目工作目录
        self.llm = ChatClaudeCode(
            cli_path=Config.CLAUDE_CODE_CLI_PATH,
            temperature=Config.TESTER_TEMPERATURE,
            timeout=Config.TASK_TIMEOUT,
            work_dir=str(self.project_path)  # 强制绑定项目目录
        )
        self.logger = setup_logger("tester")

    def test(self, task: dict, dev_result: dict) -> dict:
        task_name = task['name']
        self.logger.info(f"🧪 开始测试任务：{task_name}，工作目录：{self.project_path}")

        # 关键修复：提示词中强调工作目录，避免模型执行全局命令
        prompt = f"""
# 自动化测试任务
## 任务信息
任务ID：{task['id']}
任务名称：{task_name}
任务描述：{task['description']}

## 【强制要求】工作目录与依赖管理
1. **当前工作目录固定为：{self.project_path}**
2. 所有测试命令、依赖安装必须在此目录下进行
3. 不要修改根目录下的任何文件（如 auto_coder 根目录的 package.json）
4. 测试用例和测试报告保存在当前目录下的 `tests/` 文件夹中

## 开发结果
{dev_result.get('report', '无')}

## 测试要求
1. 编写自动化测试用例
2. 运行测试并生成详细报告
3. 明确标记测试是否通过
4. 若失败，给出具体错误信息和修复建议
        """

        try:
            response = self.llm.invoke(prompt)
            report = response.content

            # 简单判断测试结果
            success = "测试通过" in report or "all tests passed" in report.lower()

            self.logger.info(f"✅ 测试完成：{'通过' if success else '失败'}")
            return {
                "success": success,
                "report": report
            }

        except Exception as e:
            self.logger.error(f"❌ 测试执行失败：{str(e)}", exc_info=True)
            return {
                "success": False,
                "report": f"测试执行异常：{str(e)}"
            }