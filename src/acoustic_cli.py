"""纯本地声学 CLI —— 只跑 A 路，不联网、不需要任何 API Key。

用途：让任何人拿到仓库后**立刻**能复现出结果，不必先申请付费 Key。

用法：
    python3 -m src.acoustic_cli <文件或目录> [--json out.json]
    python3 -m src.acoustic_cli /path/to/music --json out.json --limit 5

输出：stdout 一张可读表；`--json` 时另存逐首原始数值。
"""
import argparse
import json
import os
import sys
import time

from . import acoustic, scan

AUDIO_EXT = scan.AUDIO_EXT          # 兼容旧引用；实现统一在 src/scan.py

FIELDS = [
    ("调性", lambda r: (f"{r['key']} {r['mode']}（{r['key_corr']}）" if r.get("key") else "未判定")),
    ("响度 dBFS", lambda r: r.get("rms_dbfs")),
    ("波峰因数 dB", lambda r: r.get("crest_db")),
    ("质心 Hz", lambda r: r.get("centroid_hz")),
    ("低/中/高", lambda r: f"{r.get('bass_ratio')}/{r.get('mid_ratio')}/{r.get('high_ratio')}"),
    ("起音/秒", lambda r: r.get("onset_rate")),
]


def iter_audio(root, recursive=True):
    """返回 [(相对路径, 绝对路径)]，按路径排序。转发到 src.scan.audio_files。"""
    return scan.audio_files(root, recursive)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python3 -m src.acoustic_cli",
        description="本地声学分析（不联网、不需要 API Key）",
    )
    ap.add_argument("path", help="音频文件或目录")
    ap.add_argument("--json", dest="json_out", default=None, help="把逐首原始数值写入该 JSON")
    ap.add_argument("--sample-rate", type=int, default=22050)
    ap.add_argument("--max-seconds", type=float, default=90)
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 个文件")
    ap.add_argument("--no-recursive", action="store_true", help="只处理目录第一层")
    args = ap.parse_args(argv)

    items = iter_audio(args.path, recursive=not args.no_recursive)
    if args.limit:
        items = items[: args.limit]
    if not items:
        print(f"没有找到音频文件：{args.path}", file=sys.stderr)
        return 1

    started = time.time()
    records, failed = [], []
    for i, (rel, full) in enumerate(items, 1):
        print(f"[{i}/{len(items)}] {rel}", file=sys.stderr, flush=True)
        r = acoustic.analyze(full, args.sample_rate, args.max_seconds)
        if r is None:
            failed.append(rel)
            print(f"    解码失败，跳过", file=sys.stderr, flush=True)
            continue
        r["file"] = rel          # 只存相对文件名，避免把本机绝对路径带进产物
        records.append(r)

    if not records:
        print("全部解码失败，无结果。", file=sys.stderr)
        return 1

    print()
    for r in records:
        print(r["file"])
        for label, get in FIELDS:
            print(f"  {label:<11} {get(r)}")
    print()

    if args.json_out:
        payload = {
            "_note": "由 src.acoustic_cli 生成的本地声学测量结果（未调用任何 API）",
            "input": args.path if not os.path.isabs(args.path) else os.path.basename(args.path),
            "sample_rate": args.sample_rate,
            "max_seconds": args.max_seconds,
            "count": len(records),
            "tracks": records,
        }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print(f"逐首数值 → {args.json_out}")

    print(f"完成：成功 {len(records)} / 失败 {len(failed)} / 共 {len(items)}"
          f"，耗时 {time.time() - started:.1f} 秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
