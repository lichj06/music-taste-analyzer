"""把逐首结果聚合成审美报告。

用法：
    python -m src.aggregate --config config.yaml
输出：output_dir/REPORT.md
"""
import argparse
import json
import os
import re
import statistics
from collections import Counter

from . import config as cfgmod

# 流派关键词（只在「1) 风格与流派」一节内匹配，避免全文误命中）
GENRE = {
    "Vocaloid/虚拟歌手": ["vocaloid", "虚拟歌手", "合成歌声", "初音", "术力口", "合成女声"],
    "电子/舞曲": ["电子", "edm", "future bass", "house", "techno", "dubstep", "synthwave",
                 "glitch", "drum and bass", "dnb", "hardcore", "trance", "dance"],
    "摇滚": ["摇滚", "rock", "朋克", "punk", "金属", "metal", "后摇", "post-rock"],
    "流行": ["流行", "pop", "j-pop", "jpop", "city pop"],
    "R&B/灵魂": ["r&b", "rnb", "灵魂乐", "soul", "funk", "放克", "neo soul", "蓝调"],
    "嘻哈/说唱": ["嘻哈", "说唱", "rap", "hip-hop", "hip hop", "trap"],
    "爵士": ["爵士", "jazz", "bossa", "swing"],
    "民谣/原声": ["民谣", "folk", "原声", "acoustic", "指弹"],
    "纯器乐": ["纯器乐", "器乐作品", "无人声", "instrumental"],
    "游戏/动画配乐": ["配乐", "原声带", "ost", "游戏音乐", "动画音乐", "soundtrack", "bgm"],
    "古典/管弦": ["管弦", "交响", "古典", "orchestral", "室内乐"],
    "氛围/环境": ["ambient", "环境音乐", "氛围音乐", "drone"],
    "二次元/ACG": ["anisong", "动漫歌曲", "动画歌曲", "acg", "二次元"],
}
INSTR = ["钢琴", "电吉他", "木吉他", "贝斯", "鼓", "合成器", "弦乐", "小提琴", "大提琴",
         "萨克斯", "长笛", "小号", "pad", "pluck", "琶音", "arpeggio", "808", "sub bass",
         "hi-hat", "失真", "电子鼓", "vocal chop", "人声切片"]
MOOD = ["明亮", "忧郁", "黑暗", "温暖", "激烈", "宁静", "欢快", "悲伤", "紧张", "舒缓",
        "怀旧", "梦幻", "压迫", "宏大", "轻盈", "躁动", "温柔", "冷峻", "空灵", "热烈",
        "孤独", "焦虑", "希望", "绝望", "俏皮", "神圣", "荒诞", "克制", "宣泄"]
SECTIONS_RE = re.compile(r"\n\s*(?:#{1,6}\s*)?\*{0,2}([1-5])\s*[).）]\s*")


def sections(text):
    parts = SECTIONS_RE.split(text)
    out = {}
    for i in range(1, len(parts) - 1, 2):
        try:
            out[int(parts[i])] = parts[i + 1]
        except ValueError:
            continue
    return out


def load(output_dir):
    rows = []
    for name in sorted(os.listdir(output_dir)):
        if not name.endswith(".json") or name.startswith("_"):
            continue
        try:
            rec = json.load(open(os.path.join(output_dir, name), encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        text = rec.get("description") or ""
        sec = sections(text)
        blob = " ".join(sec.values()) or text
        rows.append({
            "title": rec.get("title", name[:-5]),
            "genres": [g for g, ws in GENRE.items()
                       if any(w.lower() in (sec.get(1) or "").lower() for w in ws)],
            "instruments": [w for w in INSTR if w.lower() in (sec.get(2) or "").lower()],
            "moods": [w for w in MOOD if w in (sec.get(5) or sec.get(4) or "")],
            "bpm": next(iter([int(x) for x in re.findall(r"(\d{2,3})\s*(?:BPM|bpm)", text)
                              if 40 <= int(x) <= 260]), None),
            "chorus": _first_chorus(sec.get(3) or ""),
            "acoustic": rec.get("acoustic") or {},
        })
    return rows


def _first_chorus(text):
    for m in re.finditer(r"(\d{1,2}):(\d{2})", text):
        if re.search(r"副歌|Drop|drop|Chorus|chorus|高潮|サビ|爆发",
                     text[m.end():m.end() + 45]):
            return int(m.group(1)) * 60 + int(m.group(2))
    return None


def build(rows, langs):
    n = len(rows)
    lines = ["# 曲库审美分析报告", "",
             f"> 样本：**{n}** 首 · 由 music-taste-analyzer 自动生成", "", "---", ""]

    def table(title, counter, total=n):
        lines.extend([f"## {title}", "", "| 项 | 曲目 | 占比 |", "|---|---:|---:|"])
        for k, v in counter.most_common():
            lines.append(f"| {k} | {v} | {v*100//max(total,1)}% |")
        lines.append("")

    gc, ic, mc = Counter(), Counter(), Counter()
    bpms, keys, modes, choruses = [], Counter(), Counter(), []
    for r in rows:
        gc.update(r["genres"]); ic.update(r["instruments"]); mc.update(r["moods"])
        if r["bpm"]:
            bpms.append(r["bpm"])
        if r["chorus"]:
            choruses.append(r["chorus"])
        acc = r["acoustic"]
        if acc.get("key"):
            keys[f"{acc['key']} {acc['mode']}"] += 1
            modes[acc["mode"]] += 1

    table("一、曲风构成", gc)
    table("二、编制偏好（音色）", ic)
    table("三、情绪图谱", mc)
    if langs:
        table("四、语言分布（依据歌词文件）", Counter(langs.values()), len(langs))
    if modes:
        table("五、大小调", modes, sum(modes.values()))
        table("六、调性分布", keys, sum(keys.values()))

    if bpms:
        lines += ["## 七、速度分布", "",
                  f"- 可估计 BPM：{len(bpms)} / {n}",
                  f"- 中位 **{statistics.median(bpms):.0f} BPM**，均值 **{statistics.mean(bpms):.0f}**",
                  f"- 区间 {min(bpms)}–{max(bpms)}", ""]
    if choruses:
        lines += ["## 八、结构偏好：多久进入第一次副歌/Drop", "",
                  f"- 可判定：{len(choruses)} / {n}",
                  f"- 中位 **{statistics.median(choruses):.0f} 秒**", ""]

    # 声学聚合
    def med(field, scale=1):
        vals = [r["acoustic"][field] for r in rows
                if r["acoustic"].get(field) is not None]
        return round(statistics.median(vals) * scale, 2) if vals else None
    lines += ["## 九、声学特征（本地测量）", "",
              "| 指标 | 中位值 |", "|---|---:|",
              f"| 频谱质心（亮度） | {med('centroid_hz')} Hz |",
              f"| 波峰因数（动态） | {med('crest_db')} dB |",
              f"| 频段-低频 | {med('bass_ratio', 100)}% |",
              f"| 频段-中频 | {med('mid_ratio', 100)}% |",
              f"| 频段-高频 | {med('high_ratio', 100)}% |",
              f"| 起音密度 | {med('onset_rate')} 次/秒 |",
              f"| 整体响度 | {med('rms_dbfs')} dBFS |", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="聚合生成审美报告")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()
    cfg = cfgmod.load(args.config)
    rows = load(cfg["output_dir"])
    if not rows:
        raise SystemExit(f"{cfg['output_dir']} 里没有结果，先跑 src.batch")
    lang_file = os.path.join(cfg["output_dir"], "_languages.json")
    langs = json.load(open(lang_file, encoding="utf-8")) if os.path.exists(lang_file) else {}
    report = build(rows, langs)
    out = os.path.join(cfg["output_dir"], "REPORT.md")
    open(out, "w", encoding="utf-8").write(report)
    print(f"已生成 {out}（基于 {len(rows)} 首）")


if __name__ == "__main__":
    main()
