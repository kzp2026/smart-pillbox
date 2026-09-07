"""Download only a public, pinned model. Never read an account token or change the lock."""
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ.setdefault('HF_HOME',str(ROOT/'.research-cache/huggingface'))
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['HF_HUB_DISABLE_XET']='1'


def main():
    from huggingface_hub import snapshot_download
    from experiment.pipeline.topics import verify_embedding
    cfg=json.loads((ROOT/'experiment/config.example.json').read_text(encoding='utf-8'))['topic']['embedding']
    for attempt in range(5):
        try:
            snapshot_download(cfg['model_id'],revision=cfg['revision'],local_dir=ROOT/cfg['path'],token=False,allow_patterns=['*.json','*.safetensors','sentencepiece.bpe.model','1_Pooling/*'],ignore_patterns=['onnx/*','openvino/*'],max_workers=1)
            break
        except Exception:
            if attempt==4:raise
            print('公开模型连接中断，续传尝试',attempt+2)
    print('模型哈希验证通过：',len(verify_embedding(cfg)),'个文件')


if __name__=='__main__':main()
