from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "scripts"))


def load_design_visuals_module():
    spec = importlib.util.spec_from_file_location(
        "design_visuals", ROOT_DIR / "scripts" / "08_generate_design_visuals.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class DesignVisualConsistencyTests(unittest.TestCase):
    def test_prompts_share_same_product_consistency_lock(self) -> None:
        module = load_design_visuals_module()
        req_df = pd.DataFrame(
            [
                {"需求主题": "安全稳定", "需求描述": "老人如厕起身需要稳定支撑", "来源关键词": "防滑、稳固、老人"},
                {"需求主题": "安装方便", "需求描述": "希望墙面安装牢固", "来源关键词": "安装、方便"},
            ]
        )
        struct_df = pd.DataFrame(
            [
                {"结构名称": "U型双横杆扶手", "结构描述": "提供双手支撑和起身借力"},
                {"结构名称": "墙面金属固定座", "结构描述": "通过螺丝固定在瓷砖墙面"},
            ]
        )

        consistency_lock = module.build_product_consistency_lock("马桶扶手", req_df, struct_df)
        prompts_text = module.build_image_prompts("马桶扶手", req_df, struct_df)
        prompt_lines = module.extract_prompt_lines(prompts_text)
        locked_prompts = module.attach_consistency_lock_to_prompts(prompt_lines, consistency_lock)

        self.assertEqual(len(prompt_lines), 6)
        self.assertEqual(len(locked_prompts), 6)
        self.assertIn("统一产品设计锁定", consistency_lock)
        self.assertIn("白色 U 型双横杆扶手", consistency_lock)
        self.assertIn("不得生成水龙头", consistency_lock)
        for prompt in locked_prompts:
            self.assertIn("统一产品设计锁定", prompt)
            self.assertIn("same exact product design", prompt)
            self.assertIn("马桶扶手", prompt)


if __name__ == "__main__":
    unittest.main()
