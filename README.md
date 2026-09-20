# music-taste-analyzer

> 把你的音乐库变成一份**客观的**审美画像 —— 本地声学测量 + 多模态模型"听"后描述，两路证据交叉验证。

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Dependencies](https://img.shields.io/badge/deps-numpy%20%7C%20pyyaml%20%7C%20ffmpeg%20%7C%20curl-lightgrey)]()

---

## 这是什么

大多数人对自己"喜欢什么音乐"的描述，停留在**标签层面**："我听电子""我喜欢日系""我口味挺杂的"。

但标签是别人给你的，而且很粗。两个人标签都是"电子"，实际听感可能差出十万八千里 —— 一个是 100 BPM 的 Ambient，一个是 175 BPM 的硬核 Hardcore。

这个工具做的是：**不看标签，直接测声音。**

它把你的音乐库逐首拆开，输出两层结果：

| 层 | 产出 | 用途 |
|---|---|---|
| **逐首** | `<曲名>.md` + `<曲名>.json` | 每首歌的结构、编制、调性、声学指标 |
| **聚合** | `REPORT.md` | 整个曲库的审美分布：曲风、编制偏好、情绪、调性、速度、动态 |

---

## 它解决什么问题

核心矛盾是：**"音乐品味"这件事既需要主观描述，又需要客观度量，而单一手段都不够。**

- **纯人工打标签** → 主观、不一致、无法规模化，而且你会不自觉地美化自己
- **纯声学分析** → 能算出频谱质心，但说不出"这是 J-Pop 还是 Trance"
- **纯让大模型听** → 描述很漂亮，但你无法验证它是不是在编

**所以这个工具同时走两条路，然后让它们互相印证。**

---

## 工作原理

```
                    ┌──────────────────┐
   FLAC / MP3 / WAV │   music_dir      │
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
      ┌───────▼────────┐          ┌─────────▼──────────┐
      │  A. 本地声学   │          │  B. 多模态模型"听"  │
      │  (numpy, 免费) │          │  (ffmpeg→base64→API)│
      └───────┬────────┘          └─────────┬──────────┘
              │                             │
   调性 / 响度 / 波峰因数            风格 / 编制 / 情绪
   频谱质心 / 频段占比                结构 / BPM / 首副歌时间
   起音密度                          （自然语言描述）
              │                             │
              └──────────────┬──────────────┘
                             │
                    ┌────────▼─────────┐
                    │  <曲名>.json/.md │
                    └────────┬─────────┘
                             │  aggregate
                    ┌────────▼─────────┐
                    │   REPORT.md      │
                    └──────────────────┘
```

### A 路 · 本地声学测量

只用 `numpy`，不花一分钱，可无限跑：

| 指标 | 说明 |
|---|---|
| **调性** | 基于色度向量与 24 个大小调模板做相关匹配 |
| **整体响度** | dBFS（RMS） |
| **波峰因数** | 峰值/RMS 之比 —— 判断动态压缩程度 |
| **频谱质心** | "亮度"，值越高越偏高频 |
| **三频段占比** | 低 / 中 / 高频能量分布 |
| **起音密度** | 每秒起音次数，反映节奏密度 |

### B 路 · 让模型"听"

把音频转码成 base64 内嵌进 `messages`，走 OpenAI 兼容协议：

- **转码**：`ffmpeg -vn`（`-vn` 很关键 —— 不少 FLAC 内嵌的封面实际是 WebP 却标成 PNG，会让 ffmpeg 直接报错退出）
- **基座**：`numpy` 未参与，纯 API
- **关闭思考链**：同时下发 `enable_thinking: false` 与 `thinking: {"type":"disabled"}`，覆盖不同厂商的参数习惯
- **大 body**：payload **写入文件后用 `--data-binary @file`**。直接把 base64 当命令行参数会撞上 `Argument list too long`（4MB 就能触发）

---

## 快速开始

### 1. 依赖

```bash
# 系统
ffmpeg --version        # 转码 + 本地解码
curl --version          # 调 API（大 body 用，不走 Python HTTP 栈）

# Python
pip install -r requirements.txt
```

### 2. 配置

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`：

```yaml
music_dir: /path/to/your/music
output_dir: ./output
work_dir: /tmp/mta-work

model:
  provider: dashscope                    # 阿里云百炼
  name: qwen3.8-omni-flash
  api_key_env: DASHSCOPE_API_KEY
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  disable_thinking: true                 # 关思考链，省约 35% token
  max_tokens: 1600

batch:
  workers: 5                             # 并发数（I/O 密集，5 左右合适）
  bitrate: 128k                          # 转码码率
  skip_existing: true                    # 断点续跑
```

```bash
export DASHSCOPE_API_KEY=sk-xxxxxxxx
```

### 3. 跑

```bash
python3 -m src.batch --config config.yaml        # 逐首分析
python3 -m src.aggregate --config config.yaml    # 聚合出 REPORT.md
```

**断点续跑**：`skip_existing: true` 时，已有结果的曲目直接跳过。中断了重跑即可，不会重复烧 token。

```bash
python3 -m src.batch --config config.yaml --limit 5      # 先试 5 首
python3 -m src.batch --config config.yaml --workers 8    # 覆盖并发数
```

---

## 输出

### 逐首 `<曲名>.md`

````markdown
# track-01.flac

- 调性：**F 小调**（相关 0.855）
- 响度：-10.92 dBFS ｜ 波峰因数：10.92 dB
- 亮度（频谱质心）：3521.6 Hz
- 频段：低 0.1644 ／ 中 0.2982 ／ 高 0.5363
- 起音密度：5.17 次/秒

---

这是一首典型的日系高速电子舞曲，带有强烈的 Vocaloid 流行乐与复古街机游戏音乐
（Chiptune）融合的风格……

### 1. 风格 / 流派
* **核心风格**：J-Pop / 高速电子舞曲 (High-speed EDM)
* **细分元素**：Vocaloid 编曲逻辑、Trance/Techno 四四拍驱动、8-bit 街机音色

### 2. 乐器 & 音色
* **人声**：高度合成的虚拟歌手音色，咬字极快，机械阶梯状音准
* **合成器**：锯齿波主音、快速琶音、失真贝斯（Reese Bass / Acid）
...
````

### 聚合 `REPORT.md`

九个维度的分布统计：曲风构成、编制偏好、情绪图谱、语言分布、大小调、调性分布、速度分布、结构偏好（多久进第一次副歌）、声学特征中位值。

---

## 命令行

| 命令 | 说明 |
|---|---|
| `python3 -m src.batch --config <file>` | 批量分析整个音乐库 |
| `python3 -m src.batch --config <file> --limit N` | 只处理前 N 首（调试） |
| `python3 -m src.batch --config <file> --workers N` | 覆盖并发数 |
| `python3 -m src.aggregate --config <file>` | 聚合生成 `REPORT.md` |

---

## 设计取舍

**为什么用 `curl` 而不是 `requests`？**
音频 base64 后动辄 4MB+，Python HTTP 栈在这个量级上容易踩超时/内存的坑，而 `curl -N --data-binary @file` 的行为可预测、可调试。少一个依赖，多一分确定性。

**为什么 `--data-binary @file` 而不是 `-d`？**
`-d` 会把内容当命令行参数传，撞上内核的 argv 长度上限（`OSError(7, 'Argument list too long')`，4MB 左右就会触发）。

**为什么两路证据缺一不可？**
声学指标可验证但说不出风格；模型描述生动但无法验证。**把两者放在同一份报告里，读者可以自己交叉检查** —— 比如模型说"极度压缩"，你可以去看波峰因数是不是真的低。

**为什么先聚合语言分布要读 `.lrc`？**
音频里没有语言标签。有歌词文件的按歌词判，没有的标记为未知 —— 宁可缺失，不要瞎猜。

---

## 已知限制

- **BPM 与"首次副歌时间"来自模型判断**，不是本地节拍跟踪，存在误差
- **调性检测对无调性或强转调曲目不可靠**（相关系数会整体偏低，报告里会显示）
- **语言分布依赖 `.lrc` 歌词文件**，纯音乐或没歌词的曲目会缺失
- **不是音乐推荐系统** —— 它只描述你已有的库，不预测你会喜欢什么
- API 侧有额度限制。本项目在 347 首 Hi-Res 曲库上消耗约 93.5 万 token

---

## 依赖

| 类型 | 依赖 | 必需 |
|---|---|---|
| 系统 | `ffmpeg` | ✅（转码 + 本地解码） |
| 系统 | `curl` | ✅（API 调用） |
| Python | `numpy >= 1.24` | ✅（声学分析） |
| Python | `pyyaml >= 6.0` | ✅（配置） |

**没有** `requests`、`librosa`、`torch`、`soundfile`。声学部分是从 `ffmpeg` 的原始 PCM 输出直接算的。

---

## License

[MIT](LICENSE)
