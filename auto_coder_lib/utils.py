"""
通用工具函数
"""
import os
import sys
import subprocess
from pathlib import Path
from .logger import setup_logger

logger = setup_logger("utils")

def create_virtual_environment():
    """创建虚拟环境"""
    logger.info("创建虚拟环境...")
    
    venv_path = Path(".venv")
    
    if venv_path.exists():
        logger.info("虚拟环境已存在")
        return
        
    try:
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_path)])
        logger.info("虚拟环境创建成功")
    except subprocess.CalledProcessError as e:
        logger.error(f"创建虚拟环境失败: {e}")
        raise
        
def install_dependencies():
    """安装依赖"""
    logger.info("安装依赖...")
    
    pip_path = Path(".venv") / "Scripts" / "pip.exe" if os.name == "nt" else Path(".venv") / "bin" / "pip"
    
    if not pip_path.exists():
        logger.error("pip未找到，请先创建虚拟环境")
        raise FileNotFoundError("pip not found")
        
    try:
        subprocess.check_call([str(pip_path), "install", "-r", "requirements.txt"])
        logger.info("依赖安装成功")
    except subprocess.CalledProcessError as e:
        logger.error(f"安装依赖失败: {e}")
        raise
        
def count_tokens(text: str) -> int:
    """估算文本的token数量"""
    # 简单估算：中文每个字约1token，英文每个单词约1token
    # 实际项目中可以使用tiktoken等库
    return len(text) // 4