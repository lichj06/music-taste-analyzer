"""配置加载：读取 config.yaml 并填充默认值。"""
import os
import sys

DEFAULTS = {
    "music_dir": "./music",
    "output_dir": "./output",
    "work_dir": "/tmp/mta-work",
    "model": {
        "provider": "dashscope",
        "name": "qwen3.8-omni-flash",
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "disable_thinking": True,
        "max_tokens": 1600,
    },
    "batch": {"workers": 5, "bitrate": "128k", "skip_existing": True,
              "transcode_seconds": 60},
    "local": {"sample_rate": 22050, "max_seconds": 90},
}

PROMPT = (
    "请用中文客观描述这段音乐，分五部分："
    "1) 风格与流派；2) 乐器与音色特点；"
    "3) 段落结构（尽量标出时间点，如 0:00 前奏、0:45 副歌）；"
    "4) 节奏与速度感（给 BPM 估计）；5) 情绪氛围。"
    "只做客观描述，不要评价好坏。"
)


def _merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(path="config.yaml"):
    cfg = DEFAULTS
    if os.path.exists(path):
        try:
            import yaml  # 可选依赖
            with open(path, encoding="utf-8") as fh:
                cfg = _merge(DEFAULTS, yaml.safe_load(fh) or {})
        except ImportError:
            print("提示：未安装 PyYAML，改用内置默认配置。pip install pyyaml", file=sys.stderr)
    cfg["prompt"] = PROMPT
    return cfg


def api_key(cfg):
    env = cfg["model"]["api_key_env"]
    key = os.environ.get(env)
    if not key:
        sys.exit(f"缺少环境变量 {env}，请先 export {env}=<你的 API Key>")
    return key
