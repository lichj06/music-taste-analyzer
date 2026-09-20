"""依据 .lrc 歌词的字符构成判定语言。

比从音频描述里猜准得多：描述里人声的说法太自由。
"""
import os
import re

KANA = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
HAN = re.compile(r"[\u4e00-\u9fff]")
HANGUL = re.compile(r"[\uac00-\ud7af]")
LATIN = re.compile(r"[A-Za-z]")


def classify(text):
    kana, han = len(KANA.findall(text)), len(HAN.findall(text))
    hangul, latin = len(HANGUL.findall(text)), len(LATIN.findall(text))
    if kana >= 5:
        return "日语"           # 有假名即日语，即便带中文翻译行
    if hangul >= 5:
        return "韩语"
    # 英语歌常配中文翻译：拉丁字母显著多于汉字时判英语
    if latin >= 60 and latin > han * 1.6:
        return "英语"
    if han >= 10:
        return "中文"
    if latin >= 20:
        return "英语"
    return "其他/纯音乐"


def scan(music_dir):
    """返回 {音频文件名(无扩展): 语言}。没有配对 .lrc 的记为器乐。"""
    audio_ext = (".flac", ".mp3", ".wav", ".m4a", ".ogg")
    lrc = {}
    for name in os.listdir(music_dir):
        if name.lower().endswith(".lrc"):
            lrc[os.path.splitext(name)[0]] = os.path.join(music_dir, name)
    out = {}
    for name in os.listdir(music_dir):
        if not name.lower().endswith(audio_ext):
            continue
        base = os.path.splitext(name)[0]
        path = lrc.get(base)
        if not path:
            out[base] = "无歌词(器乐/无人声)"
            continue
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            out[base] = "读取失败"
            continue
        out[base] = classify(text)
    return out
