"""
用户交互模块
支持执行过程中的用户介入
"""
import sys
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

class UserInteraction:
    def __init__(self):
        self.console = Console()
        
    def show_info(self, message: str):
        """显示信息"""
        self.console.print(f"[blue]ℹ️ {message}[/blue]")
        
    def show_success(self, message: str):
        """显示成功信息"""
        self.console.print(f"[green]✅ {message}[/green]")
        
    def show_warning(self, message: str):
        """显示警告信息"""
        self.console.print(f"[yellow]⚠️ {message}[/yellow]")
        
    def show_error(self, message: str):
        """显示错误信息"""
        self.console.print(f"[red]❌ {message}[/red]")
        
    def ask_question(self, question: str) -> str:
        """向用户提问"""
        self.console.print(Panel(question, title="需要您的确认", border_style="yellow"))
        return Prompt.ask("请输入您的回答")
        
    def confirm_action(self, action: str) -> bool:
        """确认操作"""
        return Confirm.ask(f"是否{action}?", default=True)
        
    def show_task_progress(self, tasks: list):
        """显示任务进度"""
        table = Table(title="任务进度")
        table.add_column("任务ID", style="cyan")
        table.add_column("任务名称", style="magenta")
        table.add_column("状态", style="green")
        table.add_column("进度", style="blue")
        
        for task in tasks:
            status = task.get("status", "pending")
            status_color = {
                "pending": "gray",
                "running": "yellow",
                "success": "green",
                "failed": "red",
                "user_intervention": "blue"
            }.get(status, "white")
            
            progress = f"{task.get('progress', 0)}%"
            
            table.add_row(
                task["id"],
                task["name"],
                f"[{status_color}]{status}[/{status_color}]",
                progress
            )
            
        self.console.print(table)
        
    def wait_for_user_intervention(self, task_id: str, task_name: str, error_message: str) -> str:
        """等待用户介入"""
        self.console.print(Panel(
            f"任务 {task_id}: {task_name}\n\n错误信息: {error_message}\n\n"
            "请选择操作:\n"
            "1. 重试任务\n"
            "2. 跳过任务\n"
            "3. 手动修改后继续\n"
            "4. 终止执行",
            title="需要用户介入",
            border_style="red"
        ))
        
        while True:
            choice = Prompt.ask("请输入选项 (1-4)", choices=["1", "2", "3", "4"])
            if choice == "1":
                return "retry"
            elif choice == "2":
                return "skip"
            elif choice == "3":
                return "continue"
            elif choice == "4":
                return "abort"