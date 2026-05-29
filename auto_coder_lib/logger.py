"""
日志系统（全倒序 + 项目+时间双隔离 · 无语法错误）
✅ 按项目分目录：logs/项目名/
✅ 按执行时间分目录：logs/项目名/20250529_103045/
✅ 完全隔离：不同项目/同项目不同执行永不混淆
✅ 主日志 latest.log → 倒序（新日志在顶部）
✅ 所有子日志 → 全部倒序
✅ 实时冗余汇总到主日志
✅ 线程安全 | 全兼容 | 无丢失
"""
import logging
import threading
import time
from pathlib import Path
from datetime import datetime

# 全局锁（保证所有文件倒序写入线程安全）
GLOBAL_LOG_LOCK = threading.Lock()

# ====================== 全局日志上下文（动态隔离） ======================
class LogContext:
    """日志上下文：动态管理项目+时间目录"""
    project_name: str = "default_project"  # 项目名
    timestamp: str = ""                    # 执行时间戳
    base_dir: Path = Path("logs")          # 日志根目录
    current_dir: Path = None               # 当前执行日志目录（自动生成）

    @classmethod
    def init(cls, project_path: str):
        """初始化：自动提取项目名 + 生成时间戳"""
        # 1. 从项目路径提取项目名（最后一级文件夹名）
        cls.project_name = Path(project_path).name
        # 2. 生成时间戳（精确到秒，每次执行唯一）
        cls.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 3. 生成最终日志目录：logs/项目名/时间戳/
        cls.current_dir = cls.base_dir / cls.project_name / cls.timestamp
        # 4. 自动创建目录
        cls.current_dir.mkdir(parents=True, exist_ok=True)

# 初始化默认上下文（启动时自动初始化）
LogContext.init("./project/default")

# 基础配置
LOG_FORMAT = "%(asctime)s - %(name)-20s - %(levelname)-8s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ------------------------------
# 通用倒序文件处理器（核心）
# 所有日志文件都用这个：新内容永远写在头部
# ------------------------------
class PrependFileHandler(logging.FileHandler):
    def emit(self, record):
        try:
            # 格式化日志
            msg = self.format(record)
            # 加锁保证线程安全
            with GLOBAL_LOG_LOCK:
                # 读取原有内容
                old_content = ""
                if Path(self.baseFilename).exists():
                    with open(self.baseFilename, "r", encoding="utf-8") as f:
                        old_content = f.read()
                # 新日志 + 旧日志（倒序核心）
                new_content = f"{msg}\n{old_content}"
                # 写入文件
                with open(self.baseFilename, "w", encoding="utf-8") as f:
                    f.write(new_content)
        except Exception:
            self.handleError(record)

# ------------------------------
# 初始化日志文件（带标题）
# ------------------------------
def init_log_file(file_path: Path, title: str):
    if not file_path.exists():
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write(f"{title}（倒序显示 · 最新日志在顶部）\n")
            f.write(f"项目：{LogContext.project_name} | 执行时间：{LogContext.timestamp}\n")
            f.write("=" * 80 + "\n\n")

# ------------------------------
# 日志创建工具（全模块通用）
# ------------------------------
def setup_logger(name: str) -> logging.Logger:
    """
    创建全倒序日志器（自动项目+时间隔离）
    1. 控制台输出（正常顺序）
    2. 独立子日志文件（倒序）
    3. 自动冗余汇总到主日志（倒序）
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    
    # ====================== 动态文件路径（自动隔离） ======================
    main_log_path = LogContext.current_dir / "latest.log"
    sub_log_path = LogContext.current_dir / f"{name}.log"

    # 初始化子日志标题
    init_log_file(sub_log_path, f"{name} 模块日志")

    # 1. 控制台输出（正常顺序，方便查看）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. 独立子日志文件（🔥 倒序写入）
    sub_handler = PrependFileHandler(sub_log_path, encoding="utf-8")
    sub_handler.setLevel(logging.DEBUG)
    sub_handler.setFormatter(formatter)
    logger.addHandler(sub_handler)

    # 3. 汇总到主日志（🔥 倒序写入）
    main_handler = PrependFileHandler(main_log_path, encoding="utf-8")
    main_handler.setLevel(logging.DEBUG)
    main_handler.setFormatter(formatter)
    logger.addHandler(main_handler)

    return logger

def get_task_logger(task_id: str) -> logging.Logger:
    """任务专属日志（自动项目+时间隔离）"""
    return setup_logger(f"task_{task_id[:8]}")