#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

# 导入核心模块
from auto_coder_lib.logger import setup_logger
from auto_coder_lib.config import Config
from auto_coder_lib.user_interaction import UserInteraction
from auto_coder_lib.workflow import create_workflow

# 加载环境配置
Config.load_from_env()

# 🔥 修复：传入日志名称 "auto_coder"
logger = setup_logger("auto_coder")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="AutoCoder - 自动化AI开发工具")
    parser.add_argument("--docs", required=True, help="项目需求文档路径")
    parser.add_argument("--project", required=True, help="项目代码路径")
    parser.add_argument("--resume", action="store_true", help="从中断处恢复执行")
    
    args = parser.parse_args()

    docs_path = Path(args.docs)
    project_path = Path(args.project)

    # 校验路径
    if not docs_path.exists():
        logger.error(f"文档路径不存在: {docs_path}")
        return
    if not project_path.exists():
        project_path.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("AutoCoder 启动")
    logger.info(f"需求文档: {docs_path}")
    logger.info(f"项目路径: {project_path}")
    logger.info("=" * 60)

    # 初始化UI
    ui = UserInteraction()
    
    try:
        # 创建并运行工作流
        workflow = create_workflow(str(docs_path), str(project_path), ui)
        workflow.run(resume=args.resume)
        
        logger.info("✅ 所有任务执行完成！")
        ui.show_success("项目开发完成！")
        
    except KeyboardInterrupt:
        logger.warning("⚠️ 用户手动终止程序")
        ui.show_info("程序已终止")
    except Exception as e:
        logger.error(f"❌ 执行失败: {str(e)}", exc_info=True)
        ui.show_error(f"执行失败: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()