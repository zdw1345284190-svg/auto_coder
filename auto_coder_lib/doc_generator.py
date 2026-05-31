"""
交付文档自动生成器
项目完成后自动在 --docs 目录生成：使用说明、部署指南、项目结构、版本报告
"""
from pathlib import Path
from .logger import setup_logger


class DocGenerator:
    def __init__(self, project_path: str, docs_path: str):
        self.project_path = Path(project_path)
        self.docs_path = Path(docs_path)
        self.logger = setup_logger("doc_generator")
        self.docs_path.mkdir(parents=True, exist_ok=True)

    def generate_all_docs(self, project_understanding: dict, tasks: list, docs_content: str = ""):
        self.logger.info("📚 开始生成项目交付文档...")
        self.generate_user_guide(project_understanding)
        self.generate_deployment_guide(project_understanding)
        self.generate_project_structure()
        self.generate_version_report(project_understanding, tasks, docs_content)
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

    def generate_version_report(self, understanding: dict, tasks: list, docs_content: str):
        leaf_tasks = self._get_leaf_tasks(tasks)
        total = len(leaf_tasks)
        success_tasks = [t for t in leaf_tasks if t.get("status") == "success"]
        failed_tasks = [t for t in leaf_tasks if t.get("status") == "failed"]
        pending_tasks = [t for t in leaf_tasks if t.get("status") in ("pending", "running")]

        content = f"# {self.project_path.name} 版本报告\n"
        content += f"生成时间：{self._now()}\n"
        content += f"项目目录：{self.project_path}\n\n"
        content += "---\n\n"

        content += self._section_user_requirements(docs_content)
        content += self._section_dev_summary(understanding, success_tasks, failed_tasks)
        content += self._section_test_results(leaf_tasks)
        content += self._section_tech_highlights(understanding, leaf_tasks)
        content += self._section_task_list(leaf_tasks, failed_tasks, pending_tasks)
        content += self._section_modified_files(leaf_tasks)
        content += self._section_deployment(understanding)

        self._write("开发任务总结.md", content)

    def _get_leaf_tasks(self, tasks: list) -> list:
        result = []
        for t in tasks:
            if t.get("is_leaf"):
                result.append(t)
            elif "children" in t:
                result.extend(self._get_leaf_tasks(t["children"]))
        return result

    def _section_user_requirements(self, docs_content: str) -> str:
        if not docs_content or not docs_content.strip():
            return "## 一、用户需求\n\n无原始需求文档。\n\n---\n\n"

        lines = ["## 一、用户需求\n\n"]
        for raw_line in docs_content.strip().splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue
            if stripped.startswith(("-", "*", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "10.")):
                lines.append(f"- {stripped.lstrip('-*. 0123456789')}")
            else:
                lines.append(f"- {stripped}")
        lines.append("\n---\n\n")
        return "".join(lines)

    def _section_dev_summary(self, understanding: dict, success: list, failed: list) -> str:
        lines = [f"## 二、开发结果\n\n"]
        lines.append(f"- 总任务数：{len(success) + len(failed)}\n")
        lines.append(f"- 成功完成：{len(success)}\n")
        if failed:
            lines.append(f"- 失败/未完成：{len(failed)}\n")
            for t in failed:
                lines.append(f"  - ❌ {t.get('name', '未知')}\n")
        lines.append(f"- 待执行：{sum(1 for t in success if t.get('status') in ('pending', 'running'))}\n\n")

        core = understanding.get("core_features", [])
        if core:
            lines.append("### 核心功能\n\n")
            for f in core:
                lines.append(f"- {f}\n")
            lines.append("\n")

        existing = understanding.get("existing_modules", [])
        if existing:
            lines.append("### 已有模块\n\n")
            for m in existing:
                lines.append(f"- {m}\n")
            lines.append("\n")

        tech = understanding.get("tech_stack", {})
        if tech:
            lines.append("### 技术栈\n\n")
            for k, v in tech.items():
                lines.append(f"- **{k}**：{v}\n")
            lines.append("\n")

        lines.append("---\n\n")
        return "".join(lines)

    def _section_test_results(self, leaf_tasks: list) -> str:
        lines = ["## 三、测试报告\n\n"]
        passed = [t for t in leaf_tasks if t.get("status") == "success"]
        total = len(leaf_tasks)

        if not total:
            lines.append("无任务数据。\n\n---\n\n")
            return "".join(lines)

        lines.append(f"- 总用例：{total}\n")
        lines.append(f"- 通过：{len(passed)}\n")
        lines.append(f"- 失败：{total - len(passed)}\n")
        lines.append(f"- 通过率：{len(passed) / total * 100:.1f}%\n\n")

        for t in passed:
            test_res = t.get("test_result", {})
            report = test_res.get("report", "") if test_res else ""
            if report:
                lines.append(f"### 任务：{t.get('name', '未知')}\n\n")
                preview = report[:1500]
                if len(report) > 1500:
                    preview += f"\n\n*(内容过长，截取前1500字符，完整报告见日志目录)*\n"
                lines.append(f"```\n{preview}\n```\n\n")

        if any(t.get("status") == "failed" for t in leaf_tasks):
            lines.append("### 失败任务详情\n\n")
            for t in leaf_tasks:
                if t.get("status") == "failed":
                    lines.append(f"- ❌ {t.get('name', '未知')}\n")
                    test_res = t.get("test_result", {})
                    if test_res:
                        report = test_res.get("report", "")
                        if report:
                            lines.append(f"  - 报错摘要：{report[:300]}\n")
            lines.append("\n")

        lines.append("---\n\n")
        return "".join(lines)

    def _section_tech_highlights(self, understanding: dict, leaf_tasks: list) -> str:
        lines = ["## 四、技术亮点\n\n"]

        tech = understanding.get("tech_stack", {})
        if tech:
            lines.append("### 技术栈\n\n")
            for k, v in tech.items():
                lines.append(f"- **{k}**：{v}\n")
            lines.append("\n")

        arch = understanding.get("architecture", "")
        if arch:
            lines.append(f"- **架构**：{arch}\n\n")

        overview = understanding.get("project_overview", "")
        if overview:
            lines.append(f"- **项目概述**：{overview}\n\n")

        success_tasks = [t for t in leaf_tasks if t.get("status") == "success"]
        if success_tasks:
            lines.append("### 完成功能\n\n")
            for t in success_tasks:
                name = t.get("name", "")
                lines.append(f"- ✅ {name}\n")
            lines.append("\n")

        lines.append("---\n\n")
        return "".join(lines)

    def _section_task_list(self, leaf_tasks, failed, pending) -> str:
        lines = ["## 五、任务执行明细\n\n"]
        lines.append("| 状态 | 任务名称 | 描述 |\n")
        lines.append("|------|----------|------|\n")

        all_sorted = sorted(leaf_tasks, key=lambda t: (
            0 if t.get("status") == "success" else
            1 if t.get("status") == "failed" else
            2 if t.get("status") in ("pending", "running") else 3
        ))

        for t in all_sorted:
            status = t.get("status", "unknown")
            if status == "success":
                icon = "✅"
            elif status == "failed":
                icon = "❌"
            elif status in ("pending", "running"):
                icon = "⏳"
            else:
                icon = "⚪"

            name = t.get("name", "未知")
            desc = (t.get("description", "") or "")[:80]
            lines.append(f"| {icon} {status} | {name} | {desc} |\n")

        lines.append("\n---\n\n")
        return "".join(lines)

    def _section_modified_files(self, leaf_tasks: list) -> str:
        all_files = set()
        for t in leaf_tasks:
            dev_res = t.get("dev_result", {})
            if dev_res:
                files = dev_res.get("files_modified", [])
                for f in files:
                    try:
                        rel = Path(f).relative_to(self.project_path)
                        all_files.add(str(rel).replace("\\", "/"))
                    except ValueError:
                        all_files.add(f)

        if not all_files:
            return ""

        lines = ["## 六、修改文件清单\n\n"]
        for f in sorted(all_files):
            lines.append(f"- `{f}`\n")
        lines.append("\n---\n\n")
        return "".join(lines)

    def _section_deployment(self, understanding: dict) -> str:
        lines = ["## 七、部署说明\n\n"]
        tech = understanding.get("tech_stack", {})
        if tech.get("frontend"):
            lines.append("### 前端部署\n\n")
            lines.append("1. 构建：`npm run build`\n")
            lines.append("2. 将 `dist/` 目录部署到 Web 服务器\n")
            lines.append("3. 或使用开发服务器：`npm run dev`\n\n")

        if tech.get("backend"):
            lines.append("### 后端部署\n\n")
            lines.append(f"- 技术：{tech['backend']}\n")
            lines.append("- 启动命令请参考项目文档\n\n")

        lines.append("---\n\n")
        lines.append(f"AutoCoder 自动生成\n")
        lines.append(f"生成时间：{self._now()}\n")
        return "".join(lines)

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
