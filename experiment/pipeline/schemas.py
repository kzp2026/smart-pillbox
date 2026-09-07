from pathlib import Path
from functools import lru_cache
from experiment.pipeline.io import read_json


@lru_cache(maxsize=8)
def _validator(kind):
    from jsonschema import Draft202012Validator
    return Draft202012Validator(read_json(Path(__file__).resolve().parents[1]/'schemas'/(kind+'.schema.json')))


def validate(kind,value):
    errors=sorted(_validator(kind).iter_errors(value),key=lambda e:str(e.path))
    if errors:raise ValueError('实验数据结构校验失败 '+kind+'：'+str(list(errors[0].path)))
