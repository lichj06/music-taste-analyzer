# music-taste-analyzer

> Turn your music library into an **objective** aesthetic profile — local acoustic measurement crossed with a multimodal model that actually *listens*.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Dependencies](https://img.shields.io/badge/deps-numpy%20%7C%20pyyaml%20%7C%20ffmpeg%20%7C%20curl-lightgrey)]()

[中文文档](README.md) · **English**

---

## What this is

Most people describe their taste in **tags** — "I listen to electronic", "I like J-pop", "my taste is pretty mixed".

But tags are coarse and handed to you by someone else. Two libraries both tagged "electronic" can sit 75 BPM apart: one is ambient, the other is hardcore.

This tool ignores tags and **measures the sound itself**.

| Output layer | Files | What it gives you |
|---|---|---|
| Per track | `<track>.md` + `<track>.json` | Structure, instrumentation, key, acoustic metrics |
| Library | `REPORT.md` | Distributions across genre, instrumentation, mood, key, tempo, dynamics |

---

## Why two sources of evidence

The core problem: musical taste needs both **subjective description** and **objective measurement**, and neither alone is enough.

- **Manual tagging** — subjective, inconsistent, doesn't scale, and you unconsciously flatter yourself
- **Acoustic analysis alone** — you get a spectral centroid, but it can't tell you J-pop from trance
- **Model listening alone** — beautiful prose you have no way to verify

**So this tool runs both paths and lets them falsify each other.**

If the model claims a track is "heavily compressed", check the crest factor in the same report. If it really is under 8 dB, the model heard it. If it says 15 dB, it's making things up.

---

## How it works

```
                    ┌──────────────────┐
   FLAC / MP3 / WAV │   music_dir      │
                    └────────┬─────────┘
              ┌──────────────┴──────────────┐
      ┌───────▼────────┐          ┌─────────▼──────────┐
      │  A. Local      │          │  B. Multimodal      │
      │  (numpy, free) │          │  (ffmpeg→b64→API)   │
      └───────┬────────┘          └─────────┬──────────┘
    key / loudness / crest      genre / instrumentation
    centroid / band ratios      mood / structure / BPM
    onset density               (natural language)
              └──────────────┬──────────────┘
                    ┌────────▼─────────┐
                    │ <track>.json/.md │
                    └────────┬─────────┘
                    ┌────────▼─────────┐
                    │   REPORT.md      │
                    └──────────────────┘
```

**Path A** uses only `numpy`: chroma-based key detection against Krumhansl-Kessler profiles, RMS/peak/crest factor, spectral centroid and rolloff, three-band energy ratios, spectral flatness, and spectral-flux onset density.

**Path B** transcodes to mp3, base64-encodes, and sends it inline over any OpenAI-compatible endpoint.

See **[docs/METHOD.md](docs/METHOD.md)** for the full methodology, including exactly when each metric is unreliable.

---

## Quick start

```bash
# System deps
ffmpeg --version
curl --version

# Python deps
pip install -r requirements.txt

# Configure
cp config.example.yaml config.yaml   # then edit music_dir
export DASHSCOPE_API_KEY=sk-xxxxxxxx

# Run
python3 -m src.batch     --config config.yaml   # per-track analysis
python3 -m src.aggregate --config config.yaml   # build REPORT.md
```

**Resumable.** With `skip_existing: true`, finished tracks are skipped — interrupt and re-run without burning tokens twice.

```bash
python3 -m src.batch --config config.yaml --limit 5     # try 5 tracks first
python3 -m src.batch --config config.yaml --workers 8   # override concurrency
```

---

## Design decisions

**Why `curl` instead of `requests`?**
An encoded audio payload is easily 4 MB+. `curl -N --data-binary @file` behaves predictably at that size, is trivially debuggable, and removes a dependency.

**Why `--data-binary @file` instead of `-d`?**
`-d` passes the body through argv and hits `ARG_MAX`: `OSError: [Errno 7] Argument list too long` triggers at roughly 4 MB.

**Why `ffmpeg -vn`?**
Many FLAC files embed cover art that is actually WebP but labelled PNG. ffmpeg aborts on those. Skipping the video stream sidesteps it entirely.

**Why disable the thinking chain?**
`enable_thinking: false` and `thinking: {"type": "disabled"}` are both sent, because vendors disagree on which one they honour. Measured saving: ~35% of output tokens.

**Why medians in the aggregate?**
Musical feature distributions have long tails; one experimental track drags a mean away. Medians don't move.

**Why is BPM not from the local estimator?**
Autocorrelation suffers octave ambiguity — 175 BPM and 87.5 BPM produce peaks at the same lags. The estimator exists and is reported as a cross-check, but the headline BPM comes from the model. **Better to document an unreliable number than to publish a precise-looking wrong one.**

---

## Requirements

| Kind | Dependency | Needed |
|---|---|---|
| System | `ffmpeg` | ✅ transcode + local decode |
| System | `curl` | ✅ API calls |
| Python | `numpy >= 1.24` | ✅ acoustic analysis |
| Python | `pyyaml >= 6.0` | ✅ config |

**No** `requests`, `librosa`, `torch`, or `soundfile`. The acoustic path works directly on raw PCM piped out of `ffmpeg`.

---

## Scope

This describes **what is in your library** — it is not a recommender and does not predict what you should listen to.

Validated on a 347-track, 12.9 GB Hi-Res library (~20.6 hours), consuming ~935k tokens.

---

## License

[MIT](LICENSE)
