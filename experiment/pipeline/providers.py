"""Strict research adapter around the existing V2 text provider. Never persists secrets."""
from pathlib import Path
import os


class ResearchTextProvider:
    mode = 'live'

    def __init__(self, backend, *, allow_paid=False, transport_is_mock=False):
        self.backend = backend
        self.allow_paid = allow_paid
        self.transport_is_mock = transport_is_mock

    def request_payload(self, system_prompt, user_prompt, parameters):
        return self.backend.strict_request(system_prompt, user_prompt, parameters)

    def preflight(self):
        if not self.allow_paid:
            raise ValueError('缺少本次真实文字调用费用授权；未发送请求')
        if not self.backend._api_key:
            raise ValueError('安全配置未提供文字模型密钥；未发送请求')

    def generate(self, system_prompt, user_prompt, parameters):
        self.preflight()
        payload = self.request_payload(system_prompt, user_prompt, parameters)
        raw = self.backend.generate_strict(payload)
        text = self.backend._extract_text(raw)
        if not text:
            raise RuntimeError('真实模型未返回文字，禁止替代结果')
        from experiment.pipeline.io import digest
        return dict(text=text, raw_api_response=raw, raw_api_response_sha256=digest(raw),usage=raw.get('usage', 'unknown'),
                    response_model=raw.get('model', 'unknown'), model_version='unknown',
                    system_fingerprint=raw.get('system_fingerprint', 'unknown'),
                    response_id=raw.get('id', 'unknown'), cost='unknown',
                    finish_reason=raw.get('choices', [{}])[0].get('finish_reason', 'unknown'),
                    actual_parameters={k: v for k, v in payload.items() if k not in ('model', 'messages')},
                    unsupported_parameters={'seed': 'API未声明支持；不发送；真实输出不承诺逐字一致'},
                    transport_is_mock=self.transport_is_mock)


def configured_provider(settings, *, allow_paid=False, secure_values=None):
    from v2.providers.text import DeepSeekTextProvider
    if settings['provider'] != 'deepseek':
        raise ValueError('未知真实文字provider')
    if secure_values is None:
        secure_values = {}
        path = Path(__file__).resolve().parents[2] / '.streamlit' / 'secrets.toml'
        if path.is_file():
            import tomllib
            try:values = tomllib.loads(path.read_text(encoding='utf-8-sig'))
            except (tomllib.TOMLDecodeError,UnicodeError):
                raise ValueError('现有安全配置格式无法解析；未读取或导出密钥内容') from None
            secure_values = {k: values.get(k, '') for k in ('V2_DEEPSEEK_API_KEY', 'V2_DEEPSEEK_BASE_URL')}
        for key in ('V2_DEEPSEEK_API_KEY', 'V2_DEEPSEEK_BASE_URL'):
            if os.environ.get(key):
                secure_values[key] = os.environ[key]
    backend = DeepSeekTextProvider(secure_values.get('V2_DEEPSEEK_API_KEY', ''),
        model=settings['model'], base_url=secure_values.get('V2_DEEPSEEK_BASE_URL') or 'https://api.deepseek.com')
    return ResearchTextProvider(backend, allow_paid=allow_paid)
