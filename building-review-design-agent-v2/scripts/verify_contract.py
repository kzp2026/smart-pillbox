from __future__ import annotations

import argparse
import ast
import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


SKILL_NAME = "building-review-design-agent-v2"
SYNC_MARKER = "skill-sync:building-review-design-agent-v2"

REQUIRED_PATHS = (
    "AGENTS.md",
    "app.py",
    "app_legacy_current.py",
    "pages/01_现有流程备份.py",
    "pages/02_产品管理.py",
    "pages/03_旧版结果预览.py",
    "v2/app.py",
    "v2/auth.py",
    "v2/config.py",
    "v2/application/view_cache.py",
    "v2/assets/studio-background.webp",
    "v2/assets/ai-brand-mark.webp",
    "v2/assets/assistant-mascot.webp",
    "v2/ui/errors.py",
    "v2/pipeline/catalog.py",
    "v2/migrations/001_agent_v2_schema.sql",
    "tests/v2/test_original_freeze.py",
    "tests/v2/test_pipeline_catalog.py",
    "tests/v2/test_auth.py",
    "tests/v2/test_error_messages.py",
    "tests/v2/test_view_cache.py",
    "tests/v2/test_schema_sql.py",
    "docs/V2_MIGRATION.md",
    "docs/V2_DEPLOY_STREAMLIT_CLOUD.md",
    "design-qa.md",
    f"{SKILL_NAME}/SKILL.md",
    f"{SKILL_NAME}/agents/openai.yaml",
    f"{SKILL_NAME}/references/project-contract.md",
    f"{SKILL_NAME}/references/workflow.md",
    f"{SKILL_NAME}/references/verification.md",
)


def check_required_paths(root: Path, required: Iterable[str] = REQUIRED_PATHS) -> list[str]:
    return [f"缺少必需路径：{relative}" for relative in required if not (root / relative).exists()]


def _literal_assignment(source: str, name: str) -> object:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"找不到顶层常量：{name}")


def count_top_level_tuple_items(source: str, name: str) -> int:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            if not isinstance(node.value, (ast.Tuple, ast.List)):
                raise ValueError(f"{name} 必须是顶层 tuple/list。")
            return len(node.value.elts)
    raise ValueError(f"找不到顶层常量：{name}")


def find_forbidden_markers(text: str) -> list[str]:
    errors: list[str] = []
    if "TODO" in text:
        errors.append("Skill 中仍有 TODO 占位符。")
    if "\ufffd" in text:
        errors.append("Skill 中存在乱码替换字符。")
    return errors


def _git_blob_sha1(path: Path) -> str:
    content = path.read_bytes().replace(b"\r\n", b"\n")
    blob = b"blob " + str(len(content)).encode("ascii") + b"\0" + content
    return hashlib.sha1(blob).hexdigest()


def _check_original_hashes(root: Path) -> list[str]:
    freeze_source = (root / "tests/v2/test_original_freeze.py").read_text(encoding="utf-8")
    expected = _literal_assignment(freeze_source, "EXPECTED_SHA1")
    if not isinstance(expected, dict):
        return ["EXPECTED_SHA1 必须是字典。"]
    errors: list[str] = []
    for relative, expected_hash in expected.items():
        path = root / str(relative)
        if not path.exists():
            errors.append(f"原站冻结文件缺失：{relative}")
            continue
        actual_hash = _git_blob_sha1(path)
        if actual_hash != expected_hash:
            errors.append(f"原站冻结哈希变化：{relative}")
    return errors


def verify_static(root: Path) -> list[str]:
    errors = check_required_paths(root)
    if errors:
        return errors

    skill_text = (root / SKILL_NAME / "SKILL.md").read_text(encoding="utf-8")
    yaml_text = (root / SKILL_NAME / "agents/openai.yaml").read_text(encoding="utf-8")
    errors.extend(find_forbidden_markers(skill_text + "\n" + yaml_text))

    agents_text = (root / "AGENTS.md").read_text(encoding="utf-8")
    if SYNC_MARKER not in agents_text:
        errors.append("AGENTS.md 缺少 Skill 同步标记。")

    catalog_source = (root / "v2/pipeline/catalog.py").read_text(encoding="utf-8")
    if count_top_level_tuple_items(catalog_source, "LEGACY_STAGES") != 10:
        errors.append("旧流程阶段数量不再是 10；请核对功能完整性并同步 Skill。")
    if count_top_level_tuple_items(catalog_source, "V2_STAGES") != 7:
        errors.append("V2 阶段组数量不再是 7；请核对导航并同步 Skill。")

    app_source = (root / "v2/app.py").read_text(encoding="utf-8")
    if count_top_level_tuple_items(app_source, "STAGE_NAV_ITEMS") != 7:
        errors.append("V2 页面阶段导航数量不再是 7。")
    for marker in (
        "ExpiringViewCache(ttl_seconds=30)",
        "workspace_snapshot",
        "配置百炼效果图 Key",
        "V2_IMAGE_API_KEY",
    ):
        if marker not in app_source:
            errors.append(f"V2 导航性能或百炼 Key 入口契约缺少：{marker}")

    repository_source = (root / "v2/adapters/postgres.py").read_text(encoding="utf-8")
    if "def workspace_snapshot(" not in repository_source:
        errors.append("V2 仓库缺少单查询工作台快照。")

    theme_source = (root / "v2/ui/theme.py").read_text(encoding="utf-8")
    for marker in (
        '[data-testid="stFileUploaderDropzone"] button',
        '[data-testid="stCode"] button',
        "color-scheme: dark",
        'ASSET_DIR / "studio-background.webp"',
    ):
        if marker not in theme_source:
            errors.append(f"V2 深色原生控件契约缺少：{marker}")

    config_source = (root / "v2/config.py").read_text(encoding="utf-8")
    for key in ("V2_USERNAME", "V2_PASSWORD_HASH", "V2_DATABASE_URL", "V2_OWNER_ID"):
        if key not in config_source:
            errors.append(f"V2 配置契约缺少：{key}")

    schema_source = (root / "v2/migrations/001_agent_v2_schema.sql").read_text(encoding="utf-8").lower()
    for marker in (
        "create schema if not exists agent_v2",
        "revoke all on schema agent_v2 from anon, authenticated",
        "enable row level security",
    ):
        if marker not in schema_source:
            errors.append(f"私有 schema 契约缺少：{marker}")
    if schema_source.count("enable row level security") < 11:
        errors.append("agent_v2 启用 RLS 的表少于 11 张。")
    if "auth.uid()" in schema_source:
        errors.append("检测到 Supabase Auth 多租户策略；本项目使用固定服务器 owner。")

    errors.extend(_check_original_hashes(root))
    return errors


def build_test_environment(root: Path, base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    local_dependencies = root / ".test_deps"
    if local_dependencies.is_dir():
        existing = env.get("PYTHONPATH", "")
        entries = [str(local_dependencies)]
        if existing:
            entries.append(existing)
        env["PYTHONPATH"] = os.pathsep.join(entries)
    return env


def build_unittest_command(scope: str) -> list[str]:
    if scope == "v2":
        return [sys.executable, "-m", "unittest", "discover", "-s", "tests/v2", "-p", "test_*.py"]
    if scope == "all":
        return [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-t",
            ".",
            "-p",
            "test_*.py",
        ]
    raise ValueError(f"未知测试范围：{scope}")


def run_test_suite(root: Path, scope: str) -> int:
    command = build_unittest_command(scope)
    print("运行：" + " ".join(command))
    return subprocess.run(command, cwd=root, env=build_test_environment(root), check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 Review Design Agent V2 与维护 Skill 的静态契约。")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="仓库根目录，默认从 Skill 目录推导。",
    )
    parser.add_argument("--run-tests", action="store_true", help="静态检查后运行全部 tests/v2。")
    parser.add_argument("--run-all-tests", action="store_true", help="静态检查后运行仓库全量测试。")
    args = parser.parse_args()

    root = args.repo_root.resolve()
    errors = verify_static(root)
    if errors:
        print("V2 契约校验失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    print("V2 静态契约校验通过。")
    scope = "all" if args.run_all_tests else "v2" if args.run_tests else ""
    if scope and run_test_suite(root, scope) != 0:
        print("测试失败。")
        return 1
    if scope:
        print("全量测试通过。" if scope == "all" else "V2 测试通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
