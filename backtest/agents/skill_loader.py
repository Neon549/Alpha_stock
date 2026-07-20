# agents/skill_loader.py

import os


def load_skill(skill_name: str = "stock_analysis") -> str:
    """
    加载 SKILL.md 内容
    从项目根目录的 skills/ 文件夹读取
    """
    # 找到项目根目录（skills/ 的上一级）
    current_dir = os.path.dirname(__file__)  # agents/
    project_root = os.path.dirname(current_dir)  # 项目根目录

    skill_path = os.path.join(project_root, "skills", skill_name, "SKILL.md")

    if not os.path.exists(skill_path):
        print(f"⚠️ SKILL.md 不存在：{skill_path}")
        return ""

    with open(skill_path, "r", encoding="utf-8") as f:
        return f.read()


def load_skill_with_ref(skill_name: str, ref_name: str) -> str:
    """
    加载主 SKILL.md + 指定的 ref 文件
    用于按需加载，节省token
    """
    main_skill = load_skill(skill_name)

    current_dir = os.path.dirname(__file__)
    project_root = os.path.dirname(current_dir)

    ref_path = os.path.join(
        project_root, "skills", skill_name, "refs", f"{ref_name}.md"
    )

    if os.path.exists(ref_path):
        with open(ref_path, "r", encoding="utf-8") as f:
            ref_content = f.read()
        return main_skill + f"\n\n## 补充规范：{ref_name}\n" + ref_content

    return main_skill
