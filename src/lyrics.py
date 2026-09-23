"""依据 .lrc 歌词的字符构成判定语言。

比从音频描述里猜准得多：描述里人声的说法太自由。
"""
import os
import re

from . import scan as scan_files

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


def scan(music_dir, recursive=True):
    """返回 {相对路径(无扩展): 语言}。没有配对 .lrc 的记为器乐。

    扁平目录下 key 就是文件名，与旧版一致；子目录里的曲目 key 形如 `sub/a`。
    """
    lrc = scan_files.paired_lyrics(music_dir, recursive)
    out = {}
    for rel, _full in scan_files.audio_files(music_dir, recursive):
        base = os.path.splitext(rel)[0]
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
