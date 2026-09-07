"""Complete application source (including untracked files), excluding credentials and datasets."""
import argparse
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiment.pipeline.io import sha256, write_json

EXCLUDED={'.git','.codex','.agents','.venv','.venv-research','.test_deps','.research-cache',
          '__pycache__','.pytest_cache','.playwright','.playwright-cli','node_modules','data','output','runs','verification',
          '.streamlit','qa'}
EXTENSIONS={'.py','.md','.json','.txt','.toml','.sql','.css','.html','.yml','.yaml','.svg','.webp','.png','.jpg','.jpeg','.ini','.cfg','.ps1','.sh','.bat','.js','.ts','.tsx','.jsx'}


def source_paths(root):
    # Only this public theme/server configuration is allowed from the private config directory.
    public_config=Path(root)/'.streamlit/config.toml'
    if public_config.is_file() and not public_config.is_symlink():
        yield public_config
    for folder,dirs,files in os.walk(root):
        dirs[:]=sorted(d for d in dirs if d not in EXCLUDED and not d.startswith('.venv'))
        for name in sorted(files):
            path=Path(folder)/name
            if name.startswith('.env') or 'secret' in name.lower() or path.is_symlink():continue
            if path.suffix.lower() in EXTENSIONS or name in ('.gitignore','Dockerfile'):
                yield path


def snapshot(root,output):
    root=Path(root).resolve();output=Path(output).resolve()
    if output.exists() and any(output.iterdir()):raise FileExistsError('源码交付目录非空，禁止覆盖')
    paths=[p for p in source_paths(root) if not p.is_relative_to(output)]
    # Fail without echoing token contents if a source file appears to contain a real key.
    for path in paths:
        if path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):
            if re.search(rb'sk-[A-Za-z0-9]{24,}',path.read_bytes()):
                raise ValueError('源码疑似包含密钥，停止打包：'+path.relative_to(root).as_posix())
    output.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output/'source.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in paths:archive.write(path,path.relative_to(root).as_posix())
    try:
        commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
        status=subprocess.check_output(['git','status','--short'],cwd=root,text=True,encoding='utf-8',stderr=subprocess.DEVNULL)
    except (FileNotFoundError,subprocess.CalledProcessError):commit='not_git';status='not_git'
    result=dict(commit=commit,workspace_status=status,files={p.relative_to(root).as_posix():sha256(p) for p in paths},
                source_zip_sha256=sha256(output/'source.zip'),included_untracked_files=True,
                excluded=sorted(EXCLUDED),public_configuration_included=['.streamlit/config.toml'],
                note='源码与应用资产快照；数据、历史、Secrets、依赖安装目录不在包内。.streamlit仅含公开config.toml。依赖与模型按锁文件安装。')
    write_json(output/'source_manifest.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo-root',type=Path,default=Path('.'));parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=snapshot(args.repo_root,args.output);print(result['source_zip_sha256']);print(len(result['files']))
