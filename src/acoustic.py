"""本地声学分析：调性判定 + 响度/动态/频谱/节奏特征。

纯信号处理，不调用任何 API。每首只取前 N 秒（默认 90 秒），对统计足够。
"""
import subprocess

import numpy as np

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Kessler 调性轮廓（业界经典，非深度学习）
PROFILE_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                          2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
PROFILE_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                          2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

NFFT = 2048
HOP = 512


def decode(path, sample_rate, max_seconds):
    """ffmpeg 解码为单声道 float32。失败返回 None。"""
    try:
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-t", str(max_seconds), "-i", path,
             "-ac", "1", "-ar", str(sample_rate), "-f", "s16le",
             "-acodec", "pcm_s16le", "-"],
            capture_output=True, timeout=180,
        ).stdout
    except Exception:  # noqa: BLE001
        return None
    if len(raw) < NFFT * 4 * 2:
        return None
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _frames(x, n=NFFT, hop=HOP):
    m = 1 + (len(x) - n) // hop
    if m < 2:
        return None
    idx = np.arange(n)[None, :] + hop * np.arange(m)[:, None]
    return x[idx]


def key_of(frames, sample_rate):
    """色度图 + 轮廓相关 → (主音, 调式, 相关系数, 与相对调的差值)。"""
    spec = np.abs(np.fft.rfft(frames * np.hanning(NFFT)[None, :], axis=1))
    freqs = np.fft.rfftfreq(NFFT, 1.0 / sample_rate)
    keep = (freqs >= 65) & (freqs <= 2000)          # 聚焦和声区间
    pitch_class = np.round(12 * np.log2(freqs[keep] / 440.0)).astype(int) % 12
    spec = spec[:, keep]
    chroma = np.zeros(12)
    for pc in range(12):
        sel = pitch_class == pc
        if sel.any():
            chroma[pc] = spec[:, sel].sum()
    if chroma.sum() <= 0:
        return None
    chroma = chroma / chroma.sum()

    scored = []
    for tonic in range(12):
        rotated = np.roll(chroma, -tonic)
        for mode, profile in (("大调", PROFILE_MAJOR), ("小调", PROFILE_MINOR)):
            scored.append((float(np.corrcoef(rotated, profile)[0, 1]), tonic, mode))
    scored.sort(reverse=True)
    best = scored[0]
    # 相对调（大调往下 3 个半音 = 关系小调）
    alt_mode = "小调" if best[2] == "大调" else "大调"
    alt_tonic = (best[1] - 3) % 12 if best[2] == "大调" else (best[1] + 3) % 12
    alt = next((s for s in scored if s[1] == alt_tonic and s[2] == alt_mode), (0, 0, ""))
    return NOTES[best[1]], best[2], round(best[0], 3), round(best[0] - alt[0], 3)


def features(x, frames, sample_rate):
    """响度 / 动态 / 频谱 / 节奏。"""
    out = {}
    rms = float(np.sqrt(np.mean(x ** 2)))
    peak = float(np.max(np.abs(x)))
    out["rms_dbfs"] = round(20 * np.log10(rms + 1e-9), 2)
    out["peak_dbfs"] = round(20 * np.log10(peak + 1e-9), 2)
    # 波峰因数 ≈ 动态范围；越小说明压得越狠
    out["crest_db"] = round(20 * np.log10((peak + 1e-9) / (rms + 1e-9)), 2)
    seg_rms = np.sqrt(np.mean(frames ** 2, axis=1)) + 1e-9
    lo, hi = np.percentile(20 * np.log10(seg_rms), [10, 95])
    out["dyn_range_db"] = round(float(hi - lo), 2)

    spec = np.abs(np.fft.rfft(frames * np.hanning(NFFT)[None, :], axis=1)) + 1e-12
    freqs = np.fft.rfftfreq(NFFT, 1.0 / sample_rate)
    total = spec.sum(axis=1) + 1e-12
    out["centroid_hz"] = round(float((spec * freqs[None, :]).sum(axis=1).mean()
                                     / total.mean()), 1)
    cum = np.cumsum(spec, axis=1) / total[:, None]
    out["rolloff85_hz"] = round(float(freqs[np.argmax(cum >= 0.85, axis=1)].mean()), 1)

    def band(lo_hz, hi_hz):
        sel = (freqs >= lo_hz) & (freqs < hi_hz)
        return float(spec[:, sel].sum() / spec.sum())
    out["bass_ratio"] = round(band(20, 250), 4)
    out["mid_ratio"] = round(band(250, 2000), 4)
    out["high_ratio"] = round(band(2000, 11025), 4)
    # 频谱平坦度：噪声性 vs 音调性
    gmean = np.exp(np.mean(np.log(spec), axis=1))
    out["flatness"] = round(float((gmean / (spec.mean(axis=1) + 1e-12)).mean()), 4)

    # 起音密度：谱通量峰值计数
    flux = np.maximum(0, np.diff(spec, axis=0)).mean(axis=1)
    flux = flux / (flux.max() + 1e-12)
    thr = float(np.mean(flux) + 0.5 * np.std(flux))
    gap = max(1, int(0.10 * sample_rate / HOP))
    onsets, i = 0, 0
    while i < len(flux):
        if flux[i] > thr:
            j = i
            while j + 1 < len(flux) and flux[j + 1] > flux[j]:
                j += 1
            onsets += 1
            i = j + gap
        else:
            i += 1
    seconds = len(flux) * HOP / sample_rate
    out["onset_rate"] = round(onsets / seconds, 2) if seconds else 0.0
    out["zcr"] = round(float(np.mean(np.abs(np.diff(np.sign(x))) > 0)), 4)
    return out


def _tempo(frames, sample_rate):
    """自相关 + 速度先验的 BPM 估计。

    注意：在密集电子乐上不可靠（八度歧义），本项目不把它当结论使用。
    """
    spec = np.abs(np.fft.rfft(frames * np.hanning(NFFT)[None, :], axis=1))
    flux = np.maximum(0, np.diff(spec, axis=0)).mean(axis=1)
    flux = flux - flux.mean()
    ac = np.correlate(flux, flux, "full")[len(flux) - 1:]
    ac /= (ac[0] + 1e-12)
    best = (-1.0, None, 0.0)
    for bpm in np.arange(50.0, 210.0, 0.5):
        lag = int(round(60.0 * sample_rate / HOP / bpm))
        if lag < 2 or lag >= len(ac):
            continue
        prior = np.exp(-0.5 * (np.log2(bpm / 125.0) / 0.9) ** 2)   # 以 125 BPM 为中心
        score = float(ac[lag]) * prior
        if score > best[0]:
            best = (score, bpm, float(ac[lag]))
    return (round(best[1], 1) if best[1] else None, round(best[2], 3))


def analyze(path, sample_rate=22050, max_seconds=90):
    """返回一首歌的全部本地声学结果；解码失败返回 None。"""
    x = decode(path, sample_rate, max_seconds)
    if x is None:
        return None
    frames = _frames(x)
    if frames is None:
        return None
    out = {"duration_analyzed": round(len(x) / sample_rate, 1)}
    k = key_of(frames, sample_rate)
    if k:
        out["key"], out["mode"], out["key_corr"], out["key_margin"] = k
    out.update(features(x, frames, sample_rate))
    tempo, conf = _tempo(frames, sample_rate)
    if tempo:
        out["tempo_est"], out["tempo_conf"] = tempo, conf
    return out
