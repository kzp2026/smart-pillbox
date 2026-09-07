import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from experiment.evaluation.materials import prepare_review_materials


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="从已完成的实验阶段导出正式人工审核材料；无需等待 graph 或 generation 完成")
    parser.add_argument("--run", type=Path, required=True, help="包含 run_manifest.json 的实验运行目录")
    parser.add_argument("--output", type=Path, required=True, help="材料输出目录")
    args = parser.parse_args()
    result = prepare_review_materials(args.run, args.output)
    print(f"材料目录：{args.output.resolve()}")
    print("材料缺失清单：")
    for item in result["missing_items"]: print(f"- {item}")
    print("导入命令：")
    for name, command in result["import_commands"].items(): print(f"- {name}: {command}")


if __name__ == "__main__": main()
