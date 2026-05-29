"""
交付文档自动生成器
项目完成后自动在 --docs 目录生成：使用说明、部署指南、项目结构、任务总结
"""
from pathlib import Path
from .logger import setup_logger

class DocGenerator:
    def __init__(self, project_path: str, docs_path: str):
        self.project_path = Path(project_path)
        self.docs_path = Path(docs_path)
        self.logger = setup_logger("doc_generator")
        self.docs_path.mkdir(parents=True, exist_ok=True)

    def generate_all_docs(self, project_understanding: dict, tasks: list):
        self.logger.info("📚 开始生成项目交付文档...")
        self.generate_user_guide(project_understanding)
        self.generate_deployment_guide(project_understanding)
        self.generate_project_structure()
        self.generate_task_summary(tasks)
        self.logger.info(f"✅ 所有交付文档已生成：{self.docs_path}")

    def generate_user_guide(self, understanding):
        content = f"""# {self.project_path.name} 项目使用说明

## 📖 1. 项目简介
{understanding.get('project_overview', '无')}

## 🛠️ 2. 运行环境
- Node.js 16+
- npm / yarn

## 🚀 3. 本地运行（必须这样启动，不能直接点开dist/index.html）
1. 进入项目目录
cd {self.project_path.name}

2. 安装依赖
npm install

3. 启动开发服务
npm run dev

4. 打开浏览器访问终端显示的地址（通常是 http://localhost:5173）

## 📦 4. 生产构建
npm run build
构建完成后产物在 dist/ 目录

## ⚠️ 5. 为什么直接打开 dist/index.html 打不开？
因为这是前端单页应用（SPA），必须通过服务器运行，不能直接打开本地文件。

正确运行 dist 的方法：
npx serve dist
然后访问 http://localhost:3000

## ✅ 6. 常见问题
1. 依赖安装失败
→ 使用 npm install --legacy-peer-deps

2. 启动报错
→ 检查 Node.js 版本 >= 16

---
AutoCoder 自动生成
生成时间：{self._now()}
"""
        self._write("使用说明.md", content)

    def generate_deployment_guide(self, understanding):
        content = f"""# {self.project_path.name} 部署指南

## 本地部署
1. 构建：npm run build
2. 把 dist 目录上传到服务器
3. 使用 Nginx / Apache / Caddy 托管 dist 目录

## Nginx 配置示例
server {{
    listen 80;
    server_name localhost;
    root /path/to/dist;
    index index.html;
    location / {{
        try_files $uri $uri/ /index.html;
    }}
}}

---
AutoCoder 自动生成
生成时间：{self._now()}
"""
        self._write("部署指南.md", content)

    def generate_project_structure(self):
        structure = self._scan(self.project_path)
        content = f"""# {self.project_path.name} 项目结构

{structure}

---
AutoCoder 自动生成
生成时间：{self._now()}
"""
        self._write("项目结构说明.md", content)

    def generate_task_summary(self, tasks):
        total = len(tasks)
        ok = sum(1 for t in tasks if t.get("status") == "success")
        fail = sum(1 for t in tasks if t.get("status") == "failed")

        content = f"""# {self.project_path.name} 开发任务总结

总任务：{total}
完成：{ok}
失败：{fail}

任务列表：
"""
        for t in tasks:
            s = "✅ 完成" if t.get("status") == "success" else "❌ 失败/未完成"
            content += f"- {s} {t.get('name','未知任务')}\n"

        content += f"\n---\nAutoCoder 自动生成\n{self._now()}"
        self._write("开发任务总结.md", content)

    def _scan(self, path: Path, prefix=""):
        lines = []
        if not path.exists():
            return ""
        items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
        for i, item in enumerate(items):
            if item.name in [".git", "node_modules", "__pycache__", ".venv", ".vscode", "logs"]:
                continue
            connector = "├──" if i < len(items)-1 else "└──"
            if item.is_dir():
                lines.append(f"{prefix}{connector} {item.name}/")
                lines.append(self._scan(item, prefix + ("│   " if i < len(items)-1 else "    ")))
            else:
                lines.append(f"{prefix}{connector} {item.name}")
        return "\n".join(lines)

    def _write(self, filename, content):
        p = self.docs_path / filename
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        self.logger.info(f"✅ 生成：{filename}")

    def _now(self):
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")