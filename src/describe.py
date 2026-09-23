"""把一首音频交给多模态模型，拿回客观描述。

流程：ffmpeg 转码 → base64 → POST /chat/completions（流式）→ 拼接文本
"""
import base64
import json
import os
import subprocess
import time


def _restrict(path, mode):
    """把临时文件/目录的权限收窄。失败不致命：某些文件系统（如 FAT/SMB）不支持 chmod。"""
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _curl_quote(value):
    """转义 curl 配置文件里双引号字符串的内容。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _write_curl_cfg(path, url, key):
    """把认证信息写进 curl 的 -K 配置文件，而不是命令行参数。

    `curl -H "Authorization: Bearer sk-..."` 会让 Key 出现在 `ps` / `/proc/*/cmdline` 里，
    同机其它用户可读到。走 -K 文件（0600）就不进 argv。
    """
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# 含 API Key，权限 0600，用完即删 —— 请勿提交到版本库\n")
        fh.write(f'header = "Authorization: Bearer {_curl_quote(key)}"\n')
        fh.write('header = "Content-Type: application/json"\n')
        fh.write(f'url = "{_curl_quote(url)}"\n')
    _restrict(path, 0o600)


def transcode(src, dst, bitrate="128k", max_bytes=7_400_000, max_seconds=60):
    """转成小体积 MP3。返回 (成功, 大小或错误信息)。

    -vn 用于跳过视频流：部分 FLAC 内嵌封面实际是 WebP 却标记为 PNG，会让 ffmpeg 报错退出。
    -t 用于截断时长：**整首版权音频会被上传到第三方 API**，只送前 max_seconds 秒，
    既是隐私/版权最小化，也顺带把体积压到 base64 上限以内。
    """
    if os.path.exists(dst):
        os.remove(dst)
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-t", str(max_seconds), "-i", src, "-vn",
             "-b:a", bitrate, "-ar", "44100", "-ac", "2", dst],
            check=True, capture_output=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return False, "ffmpeg 超时"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:120]
    size = os.path.getsize(dst) if os.path.exists(dst) else 0
    if size == 0:
        return False, "转码产出为空"
    if size > max_bytes:
        return False, f"转码后 {size/1048576:.1f}MB 超出 base64 上限，请降低 bitrate"
    return True, size


def describe(path, cfg, key, retries=3):
    """返回 (成功, 描述文本或错误, usage 字典)。"""
    m = cfg["model"]
    work = cfg["work_dir"]
    os.makedirs(work, exist_ok=True)
    mp3 = os.path.join(work, "track.mp3")

    ok, info = transcode(path, mp3, cfg["batch"]["bitrate"],
                         max_seconds=cfg["batch"].get("transcode_seconds", 60))
    if not ok:
        return False, info, {}

    b64 = base64.b64encode(open(mp3, "rb").read()).decode()
    # 这里给 data URI 补了 MIME（audio/mpeg）并显式加 input_audio.format。
    # 注意：阿里云百炼官方文档的示例写的是 `data:;base64,{b64}`，**既没有 MIME 也没有 format**
    # （https://www.alibabacloud.com/help/en/model-studio/qwen3-omni-captioner ）。
    # 两种写法都符合 RFC 2397 / OpenAI 兼容规范，但本项**未实测** ——
    # 提交时没有调用付费 API。若真机返回 400，先把 "format" 去掉重试。
    payload = {
        "model": m["name"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "input_audio",
                 "input_audio": {"data": f"data:audio/mpeg;base64,{b64}", "format": "mp3"}},
                {"type": "text", "text": cfg["prompt"]},
            ],
        }],
        "stream": True,
        "max_tokens": m["max_tokens"],
    }
    if m.get("disable_thinking"):
        # 百炼（DashScope）用 enable_thinking；DeepSeek 官方用 thinking.type
        payload["enable_thinking"] = False
        payload["thinking"] = {"type": "disabled"}

    # 必须写入文件再用 @file 传给 curl：
    # base64 后的音频有数 MB，直接作为命令行参数会触发 OSError(7, 'Argument list too long')
    body_path = os.path.join(work, "payload.json")
    with open(body_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    resp_path = os.path.join(work, "resp.sse")
    curl_cfg = os.path.join(work, "curl.cfg")
    _restrict(work, 0o700)
    _restrict(body_path, 0o600)
    _write_curl_cfg(curl_cfg, f"{m['base_url']}/chat/completions", key)
    last_err = ""
    try:
        for attempt in range(1, retries + 1):
            r = subprocess.run(
                ["curl", "-s", "-N", "-m", "300", "-o", resp_path, "-w", "%{http_code}",
                 "-X", "POST", "--data-binary", "@" + body_path,
                 "-K", curl_cfg],
                capture_output=True, text=True,
            )
            if not os.path.exists(resp_path):
                # curl 连不上（DNS 失败、端口拒绝）时不会创建 -o 指定的文件，
                # 直接 open() 会抛 FileNotFoundError 把整批任务带崩
                last_err = (f"curl 未产生响应文件（curl 退出码 {r.returncode}，"
                            f"HTTP {r.stdout or '000'}）：网络不可达 / base_url 写错 / DNS 失败")
                time.sleep(3 * attempt)
                continue
            text = open(resp_path, encoding="utf-8", errors="replace").read()
            if text.strip().startswith("{") and '"error"' in text:
                try:
                    last_err = json.loads(text)["error"].get("message", "")[:200]
                except Exception:  # noqa: BLE001
                    last_err = text[:200]
                time.sleep(3 * attempt)
                continue
            chunks, usage = [], {}
            for line in text.split("\n"):
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data == "[DONE]":
                    continue
                try:
                    obj = json.loads(data)
                except Exception:  # noqa: BLE001
                    continue
                if obj.get("usage"):
                    usage = obj["usage"]
                for ch in obj.get("choices") or []:
                    piece = (ch.get("delta") or {}).get("content")
                    if piece:
                        chunks.append(piece)
            if chunks:
                return True, "".join(chunks), usage
            last_err = f"HTTP {r.stdout} 空响应"
            time.sleep(3 * attempt)
        return False, last_err, {}
    finally:
        _remove(curl_cfg)      # Key 不留在磁盘上
