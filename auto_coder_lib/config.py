"""
配置管理模块
"""
import os
from dotenv import load_dotenv
from pathlib import Path

class Config:
    # Claude Code CLI配置
    CLAUDE_CODE_CLI_PATH = "claude-code"
    
    # LLM配置 (llama.cpp)
    LLM_BASE_URL = "http://localhost:8080/v1"
    LLM_API_KEY = "dummy"
    LLM_MODEL_NAME = "qwen3.6"
    
    # 搜索配置 (SearXNG)
    SEARXNG_BASE_URL = "http://localhost:8888"
    
    # 任务配置
    MAX_CONTEXT_LENGTH = 2000000  # 200万token
    MAX_RETRIES = 3
    TASK_TIMEOUT = 3600  # 1小时
    MAX_FIX_ITER = 5  # 单任务最大自动修复迭代次数
    
    # 日志配置
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # 开发配置
    DEVELOPER_TEMPERATURE = 0.2
    TESTER_TEMPERATURE = 0.1
    
    @classmethod
    def load_from_env(cls):
        """从环境变量加载配置"""
        for key in dir(cls):
            if key.isupper() and not key.startswith('_'):
                env_value = os.getenv(key)
                if env_value is not None:
                    # 类型转换
                    current_value = getattr(cls, key)
                    if isinstance(current_value, int):
                        setattr(cls, key, int(env_value))
                    elif isinstance(current_value, float):
                        setattr(cls, key, float(env_value))
                    else:
                        setattr(cls, key, env_value)

def load_config(env_file=".env"):
    """加载配置文件"""
    env_path = Path(env_file)
    if env_path.exists():
        load_dotenv(env_path)
    Config.load_from_env()