"""Translate caption phrases locally using Ollama; explicit failures, no fake translations."""
import json
import os
from urllib import request, error


def translate_phrases(phrases):
    """Return exactly one natural English phrase per input phrase in the same order."""
    if not phrases:
        return []
    model = os.getenv('OPENSHORTS_OLLAMA_MODEL', 'qwen3:4b')
    url = os.getenv('OPENSHORTS_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/') + '/api/chat'
    payload = {
        'model': model,
        'stream': False,
        'format': 'json',
        'options': {'temperature': 0},
        'messages': [
            {'role': 'system', 'content': 'You translate spoken Hindi or mixed Hindi-English captions to natural English. Preserve names, numbers, and meaning. Do not transliterate Hindi into Roman Hindi. Return ONLY a JSON object with the key "translations", containing exactly one string for each input item in the same order. Do not add commentary.'},
            {'role': 'user', 'content': '/no_think\nTranslate the following caption phrases into English as a JSON object with translations: ' + json.dumps(phrases, ensure_ascii=False)}
        ]
    }
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with request.urlopen(req, timeout=240) as response:
            output = json.load(response)
    except (OSError, TimeoutError, error.URLError) as exc:
        raise RuntimeError(f'English captions need Ollama running at {url} with model {model}. Details: {exc}') from exc
    try:
        raw = output['message']['content']
        parsed = json.loads(raw)
        translations = parsed['translations']
        if not isinstance(translations, list) or len(translations) != len(phrases):
            raise ValueError('Incorrect number of translated phrases')
        if not all(isinstance(t, str) and t.strip() for t in translations):
            raise ValueError('Empty translation')
        return [t.strip() for t in translations]
    except (ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f'Ollama returned invalid English caption JSON: {exc}') from exc
