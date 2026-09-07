from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone

import pandas as pd


VERSION = 'paper-evidence-v1'
MAX_ROWS = 20000
PROVENANCE_FIELDS = ('platform', 'product_ref', 'collection_method', 'collected_at',
                     'date_range', 'sampling', 'permission_note', 'anonymization_note')
METADATA_FIELDS = ('rating', 'date', 'variant', 'channel')


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def digest(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def cell_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ''
    return str(value).strip()


def redact(text: str) -> str:
    text = re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)', '[手机号]', text)
    return re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[邮箱]', text)


def prepare_dataset(dataframe: pd.DataFrame, source: bytes, filename: str,
                    columns: dict, provenance: dict, min_length: int = 2,
                    deduplicate: bool = True) -> dict:
    if not 1 <= min_length <= 100:
        raise ValueError('最短评论长度须在 1–100 之间。')
    if len(dataframe) > MAX_ROWS:
        raise ValueError('单次论文实验最多 20000 行，请先按研究抽样方案划分文件。')
    if not dataframe.columns.is_unique:
        raise ValueError('列名重复，请先给每列唯一名称。')
    if not columns.get('comment') or any(c not in dataframe.columns for c in columns.values() if c):
        raise ValueError('字段映射不存在，请重新选择评论和元数据列。')
    counts = dict(raw=len(dataframe), empty=0, too_short=0, duplicate=0, valid=0)
    records, exclusions, seen = [], [], set()
    for number, (_, row) in enumerate(dataframe.iterrows(), 2):
        text = unicodedata.normalize('NFKC', cell_text(row[columns['comment']]))
        text = re.sub(r'\s+', ' ', text).strip()
        # ID reflects normalized, redacted evidence, not an account or username.
        text = redact(text)
        fingerprint = hashlib.sha256(text.encode('utf-8')).hexdigest()
        reason = 'empty' if not text else 'too_short' if len(text) < min_length else ''
        if not reason and deduplicate and fingerprint in seen:
            reason = 'duplicate'
        if reason:
            counts[reason] += 1
            exclusions.append({'source_row': number, 'reason': reason})
            continue
        seen.add(fingerprint)
        comment_id = fingerprint if deduplicate else f'{fingerprint}-{number}'
        record = {'comment_id': comment_id, 'source_row': number, 'text': text}
        for field in METADATA_FIELDS:
            record[field] = redact(cell_text(row[columns[field]])) if columns.get(field) else ''
        records.append(record)
    if not records:
        raise ValueError('清洗后没有有效评论，请检查评论列和最短长度。')
    counts['valid'] = len(records)
    card = {
        'version': VERSION, 'filename': filename.replace('\\', '/').split('/')[-1],
        'input_sha256': hashlib.sha256(source).hexdigest(),
        'dataset_sha256': digest(records), 'counts': counts, 'column_mapping': columns,
        'cleaning': {'min_length': min_length, 'deduplicate': deduplicate, 'normalization': 'NFKC+whitespace',
                     'redaction': '手机号和邮箱自动遮盖；姓名、地址及其他身份信息需人工复核'},
        'provenance': {k: str(provenance.get(k, '')).strip() for k in PROVENANCE_FIELDS},
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    return {'card': card, 'records': records, 'exclusions': exclusions}
