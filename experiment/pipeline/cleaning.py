from __future__ import annotations

import re
import unicodedata
from pathlib import Path


def normalize(value: object) -> str:
    import pandas as pd
    if value is None or pd.isna(value): return ''
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC',str(value))).strip()


def redact(text: str) -> str:
    text=re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)','[手机号已匿名]',text)
    return re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[邮箱已匿名]',text)


def clean_input(path: Path, config: dict) -> tuple[list[dict],list[dict],dict]:
    import pandas as pd
    frame=pd.read_excel(path) if path.suffix.lower()=='.xlsx' else pd.read_csv(path,encoding='utf-8-sig')
    if config['comment_column'] not in frame:
        raise ValueError('配置的评论列不存在')
    records,audit,seen=[],[],{}
    counts=dict(raw=len(frame),valid=0,empty=0,duplicate=0,too_short=0,removed=0,merged=0)
    for index,record in enumerate(frame.to_dict('records'),start=1):
        raw=record.get(config['comment_column']);raw_text='' if raw is None or pd.isna(raw) else str(raw)
        original=normalize(raw_text)
        cleaned=redact(original)
        cid=f'C{index:04d}'
        row=dict(comment_id=cid,source_row=index+1,original_comment=redact(raw_text),cleaned_comment=cleaned,
                 result='retained',reason='',duplicate_of='',rating=normalize(record.get(config.get('rating_column',''))),
                 date=normalize(record.get(config.get('date_column',''))),product_version=normalize(record.get(config.get('version_column',''))),
                 source_channel=normalize(record.get(config.get('channel_column',''))) or config.get('source_channel',''))
        # Deduplicate normalized originals, before masking: distinct private values must not be merged accidentally.
        if not original:
            row.update(result='removed',reason='empty');counts['empty']+=1
        elif len(original)<config['min_length']:
            row.update(result='removed',reason='too_short');counts['too_short']+=1
        elif config['deduplicate'] and original in seen:
            row.update(result='merged_duplicate',reason='normalized_exact_duplicate',duplicate_of=seen[original]);counts['duplicate']+=1
        else:
            seen[original]=cid;records.append(dict(row));counts['valid']+=1
        audit.append(row)
    counts['merged']=counts['duplicate'];counts['removed']=counts['empty']+counts['too_short']
    if not records: raise ValueError('清洗后无有效评论')
    assert counts['raw']==counts['valid']+counts['removed']+counts['merged']
    return records,audit,counts
