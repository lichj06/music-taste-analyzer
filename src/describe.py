"""把一首音频交给多模态模型，拿回客观描述。

流程：ffmpeg 转码 → base64 → POST /chat/completions（流式）→ 拼接文本
"""
import base64
import json
import os
import subprocess
import time


def transcode(src, dst, bitrate="128k", max_bytes=7_400_000):
    """转成单声道/立体声小体积 MP3。返回 (成功, 大小或错误信息)。

    -vn 用于跳过视频流：部分 FLAC 内嵌封面实际是 WebP 却标记为 PNG，会让 ffmpeg 报错退出。
    """
    if os.path.exists(dst):
        os.remove(dst)
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", src, "-vn",
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

    ok, info = transcode(path, mp3, cfg["batch"]["bitrate"])
    if not ok:
        return False, info, {}

    b64 = base64.b64encode(open(mp3, "rb").read()).decode()
    payload = {
        "model": m["name"],
        "messages": [{
            "role": "user",
            "content": [
                {"type": "input_audio", "input_audio": {"data": f"data:;base64,{b64}"}},
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
    last_err = ""
    for attempt in range(1, retries + 1):
        r = subprocess.run(
            ["curl", "-s", "-N", "-m", "300", "-o", resp_path, "-w", "%{http_code}",
             "-H", f"Authorization: Bearer {key}",
             "-H", "Content-Type: application/json",
             "-X", "POST", "--data-binary", "@" + body_path,
             f"{m['base_url']}/chat/completions"],
            capture_output=True, text=True,
        )
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
