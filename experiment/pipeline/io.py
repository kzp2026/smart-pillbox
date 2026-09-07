from __future__ import annotations

import hashlib
import json
from pathlib import Path


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode('utf-8')


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(value))
    return path


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def inside(root: Path, relative: str) -> Path:
    path = (root/relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('文件路径超出本次运行目录')
    return path


def table(path: Path, sheets: dict[str, list[dict]]) -> Path:
    from openpyxl import Workbook
    wb = Workbook(); wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name[:31]); keys = list(dict.fromkeys(k for r in rows for k in r))
        ws.append(keys)
        for row in rows:
            values=[]
            for key in keys:
                val=row.get(key,'')
                if isinstance(val,(dict,list,tuple)): val=json.dumps(val,ensure_ascii=False,sort_keys=True)
                if isinstance(val,str) and val.startswith(('=','+','-','@')): val="'"+val
                values.append(val)
            ws.append(values)
        ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
    path.parent.mkdir(parents=True,exist_ok=True); wb.save(path)
    return path
