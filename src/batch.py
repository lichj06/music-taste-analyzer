"""批量分析管道：扫描音乐目录 → 逐首（模型描述 + 本地声学 + 歌词语言）→ 落盘。

用法：
    python -m src.batch --config config.yaml
    python -m src.batch --config config.yaml --workers 5 --limit 20
"""
import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import acoustic, config as cfgmod, describe, lyrics

AUDIO_EXT = (".flac", ".mp3", ".wav", ".m4a", ".ogg")


def _safe(name):
    return name.replace("/", "_").replace("\\", "_")


def run_one(path, base, cfg, key, lock, stats, log):
    target_md = os.path.join(cfg["output_dir"], _safe(base) + ".md")
    target_json = os.path.join(cfg["output_dir"], _safe(base) + ".json")
    if cfg["batch"]["skip_existing"] and os.path.exists(target_json):
        with lock:
            stats["skip"] += 1
        return

    record = {"file": path, "title": base}
    ok, text, usage = describe.describe(path, cfg, key)
    if not ok:
        with lock:
            stats["err"] += 1
        log(f"ERR  {base[:34]:<36} {text}")
        return
    record["description"] = text
    record["usage"] = usage

    local = acoustic.analyze(path, cfg["local"]["sample_rate"], cfg["local"]["max_seconds"])
    if local:
        record["acoustic"] = local

    with lock:
        stats["ok"] += 1
        stats["tokens"] += usage.get("total_tokens", 0)
        done = stats["ok"] + stats["skip"] + stats["err"]
        log(f"[{done}] OK  {base[:34]:<36} {usage.get('total_tokens', 0):>5}tok")

    with open(target_json, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=1)

    lines = [f"# {base}", ""]
    if local:
        k = f"{local['key']} {local['mode']}" if local.get("key") else "未判定"
        lines += [
            f"- 调性：**{k}**（相关 {local.get('key_corr')}）",
            f"- 响度：{local.get('rms_dbfs')} dBFS ｜ 波峰因数：{local.get('crest_db')} dB",
            f"- 亮度（频谱质心）：{local.get('centroid_hz')} Hz",
            f"- 频段：低 {local.get('bass_ratio')} ／ 中 {local.get('mid_ratio')} ／ 高 {local.get('high_ratio')}",
            f"- 起音密度：{local.get('onset_rate')} 次/秒",
            "",
        ]
    lines += ["---", "", text, ""]
    with open(target_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description="批量分析音乐库")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 首（调试用）")
    args = ap.parse_args()

    cfg = cfgmod.load(args.config)
    key = cfgmod.api_key(cfg)
    workers = args.workers or cfg["batch"]["workers"]
    os.makedirs(cfg["output_dir"], exist_ok=True)
    os.makedirs(cfg["work_dir"], exist_ok=True)

    files = sorted(f for f in os.listdir(cfg["music_dir"]) if f.lower().endswith(AUDIO_EXT))
    if args.limit:
        files = files[: args.limit]
    total = len(files)

    # 歌词语言判定（本地，一次性）
    langs = lyrics.scan(cfg["music_dir"])
    with open(os.path.join(cfg["output_dir"], "_languages.json"), "w", encoding="utf-8") as fh:
        json.dump(langs, fh, ensure_ascii=False, indent=1)

    lock = threading.RLock()
    stats = {"ok": 0, "skip": 0, "err": 0, "tokens": 0}
    started = time.time()

    def log(msg):
        with lock:
            line = f"[{time.strftime('%H:%M:%S')}] {msg}"
            print(line, flush=True)

    log(f"共 {total} 首，并发 {workers}，模型 {cfg['model']['name']}")
    # 每首用独立工作目录，避免并发下互相覆盖临时文件
    base_cfg = cfg
    futs = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, name in enumerate(files):
            base = os.path.splitext(name)[0]
            sub = dict(base_cfg)
            sub["work_dir"] = os.path.join(base_cfg["work_dir"], f"w{i}")
            futs.append(pool.submit(run_one, os.path.join(base_cfg["music_dir"], name),
                                    base, sub, key, lock, stats, log))
        for fut in as_completed(futs):
            try:
                fut.result()          # 必须取回结果，否则异常会被静默吞掉
            except Exception as exc:  # noqa: BLE001
                with lock:
                    stats["err"] += 1
                log(f"ERR  未捕获异常：{exc!r}")

    log(f"完成：成功 {stats['ok']} / 跳过 {stats['skip']} / 失败 {stats['err']} / 共 {total}")
    log(f"累计 token {stats['tokens']:,}  墙钟 {(time.time()-started)/60:.1f} 分钟")
    log(f"歌词语言表 → {cfg['output_dir']}/_languages.json")


if __name__ == "__main__":
    main()
