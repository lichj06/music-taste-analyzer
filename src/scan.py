"""目录扫描：找音频文件、找配对歌词。

集中一处，是为了让 batch / acoustic_cli / lyrics 三处的「扫哪些文件」
和「相对路径怎么算」保持一致，别再各写一遍 os.listdir。
"""
import os

AUDIO_EXT = (".flac", ".mp3", ".wav", ".m4a", ".ogg")


def audio_files(root, recursive=True):
    """返回 [(相对路径（含扩展名）, 绝对路径)]，按相对路径排序。

    - root 是单个文件时，返回 [(文件名, 该文件)]
    - recursive=False 只看第一层（旧版行为）
    """
    if os.path.isfile(root):
        return [(os.path.basename(root), root)]
    if not os.path.isdir(root):
        return []
    found = []
    if recursive:
        for dirpath, _dirs, names in os.walk(root):
            for name in names:
                if name.lower().endswith(AUDIO_EXT):
                    full = os.path.join(dirpath, name)
                    found.append((os.path.relpath(full, root), full))
    else:
        for name in os.listdir(root):
            if name.lower().endswith(AUDIO_EXT):
                found.append((name, os.path.join(root, name)))
    return sorted(found)


def paired_lyrics(music_dir, recursive=True):
    """返回 {相对路径去扩展名: 该 .lrc 的绝对路径}。

    配对规则是**同目录 + 同名**：`sub/a.flac` 只认 `sub/a.lrc`，
    子目录里的 a.lrc 不会被拿去配父目录的 a.flac。
    """
    pairs = {}
    if not os.path.isdir(music_dir):
        return pairs
    rels = []
    if recursive:
        for dirpath, _dirs, names in os.walk(music_dir):
            for name in names:
                if name.lower().endswith(".lrc"):
                    full = os.path.join(dirpath, name)
                    rels.append((os.path.relpath(full, music_dir), full))
    else:
        for name in os.listdir(music_dir):
            if name.lower().endswith(".lrc"):
                rels.append((name, os.path.join(music_dir, name)))
    for rel, full in rels:
        pairs[os.path.splitext(rel)[0]] = full
    return pairs
