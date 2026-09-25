# music-taste-analyzer

> 把你的音乐库变成一份**客观的**审美画像 —— 本地声学测量 + 多模态模型"听"后描述，两路证据交叉验证。

[![Python](https://img.shields.io/badge/python-3.12%20tested%20%7C%20%E2%89%A53.10-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Dependencies](https://img.shields.io/badge/deps-numpy%20%7C%20pyyaml%20%7C%20ffmpeg%20%7C%20curl-lightgrey)]()

---

## 30 秒看懂

### 这是什么

把你的音乐库变成一份体检单：不看标签，直接测声音本身。

### 要解决什么问题

你想说清自己喜欢什么音乐，最后只能挤出"我听电子""我口味挺杂"这种话。可标签是别人贴的，还特别粗 —— 两个人都说自己听电子，一个听的是 100 BPM 的氛围乐，一个听的是 175 BPM 的硬核。想认真搞明白自己的品味，光靠标签和感觉是不够的。

### 我做了什么

两路一起走。一路在本地把每首歌的声音拆开量一遍：什么调、多响、亮不亮、节奏密不密，全部算成数字。另一路把歌的前 60 秒丢给多模态大模型，让它像人一样"听"完，再用自然语言写出风格、编制和情绪。两条路的结论放进同一份报告里，谁都能对着互相核对，模型要是瞎编，数字那边对不上。

### 做出来了什么

- **能跑通**：本机实测 2 首真实音频，成功 2 / 失败 0，耗时 1.8 秒；其中一首测出调性 F 小调（相关 0.855）、响度 -10.92 dBFS、亮度 3521.6 Hz、起音 5.17 次/秒。
- **曲库规模是实测的**：353 个音频文件（349 FLAC + 3 MP3 + 1 WAV），总时长 21.26 小时，合计 12.89 GiB —— 统计用的两条命令写在下文，任何人都能重跑。
- **有聚合产物**：一条命令生成 `REPORT.md`，给出曲风构成、编制偏好、情绪图谱等九个维度的分布统计。
- **成本可查**：本地那一路只用 `numpy` + `ffmpeg`，不装 `torch`、`librosa`，不联网也不花钱，可以无限跑。

### 为什么做这个

起因是一个具体的不满：我能列出几十首喜欢的歌，却说不清自己到底喜欢它们的什么。网上的歌单和推荐又都建立在标签上，粗到没有解释力。既然"我觉得好听"不可信，别人贴的标签也不可信，那就只剩一条路 —— 自己去量。这个项目本质上是一次自我测量的尝试：把主观听感拆成可以复算的数字，再用模型去补充数字说不出来的那部分。而且我很在意一件事 —— 模型描述得再漂亮也无法验证，所以我把两路证据摆在同一份报告里，让人自己交叉检查。

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

> ⚠️ **这一路会把音频片段上传到第三方 API（默认阿里云百炼）。**
> 请自行确认版权与隐私：上传的是**前 60 秒**（`batch.transcode_seconds` 可调），
> 不是整首；即便如此，曲目仍是可识别的。不想上传就别配 `DASHSCOPE_API_KEY`，
> 只用 A 路（`src.acoustic_cli`）—— 那条路完全不联网。

- **截断**：`ffmpeg -t 60`，只送前 60 秒（整首上传既无必要，也放大了版权与体积风险）
- **转码**：`ffmpeg -vn`（`-vn` 很关键 —— 不少 FLAC 内嵌的封面实际是 WebP 却标成 PNG，会让 ffmpeg 直接报错退出）
- **基座**：`numpy` 未参与，纯 API
- **关闭思考链**：同时下发 `enable_thinking: false` 与 `thinking: {"type":"disabled"}`，覆盖不同厂商的参数习惯（**能否省 token 未做对照实验**）
- **大 body**：payload **写入文件后用 `--data-binary @file`**。直接把 base64 当命令行参数会撞上 `Argument list too long`（4MB 就能触发）
- **密钥不上命令行**：认证头写在 0600 的 curl 配置文件里，用 `curl -K` 读取，用完即删 —— `-H "Authorization: Bearer sk-..."` 会让 Key 出现在 `ps` / `/proc/*/cmdline` 里

---

## 快速开始

### 0. 先跑 A 路（不用 Key、不联网、不要配置）

拿到仓库的人第一条命令就能出结果 —— 不需要申请任何 API Key：

```bash
python3 -m src.acoustic_cli /path/to/your/music --limit 3 --json acoustic.json
```

单文件也可以：`python3 -m src.acoustic_cli "某首.flac"`。默认递归子目录，
只看第一层加 `--no-recursive`。

本机实测输出（真实音频，文件名此处匿名成 `track-01/02`，数值未改）：

```
$ python3 -m src.acoustic_cli ./music --json acoustic.json
[1/2] track-01.flac
[2/2] track-02.flac

track-01.flac
  调性          F 小调（0.855）
  响度 dBFS     -10.92
  波峰因数 dB     10.92
  质心 Hz       3521.6
  低/中/高       0.1644/0.2982/0.5363
  起音/秒        5.17
track-02.flac
  调性          F 小调（0.723）
  响度 dBFS     -12.73
  波峰因数 dB     11.95
  质心 Hz       1930.6
  低/中/高       0.2665/0.4324/0.2972
  起音/秒        4.34

逐首数值 → acoustic.json
完成：成功 2 / 失败 0 / 共 2，耗时 1.8 秒
```

### 1. 依赖

```bash
# 系统
ffmpeg --version        # 转码 + 本地解码（实测 6.1.1）
curl --version          # 调 API（大 body 用，不走 Python HTTP 栈）

# Python（版本已钉死；国内网络慢就加镜像源）
pip install -r requirements.txt
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

Python **≥ 3.10**（本项目只在 **3.12.3** 上实测过，其它版本未验证）。

### 2. 配置（只跑 A 路可以整段跳过）

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
  disable_thinking: true                 # 关思考链（是否省 token 未做对照实验）
  max_tokens: 1600

batch:
  workers: 5                             # 并发数（I/O 密集，5 左右合适）
  bitrate: 128k                          # 转码码率
  transcode_seconds: 60                  # 只把前 N 秒上传给第三方 API
  skip_existing: true                    # 断点续跑
```

```bash
export DASHSCOPE_API_KEY=sk-xxxxxxxx
```

### 3. 跑

```bash
python3 -m src.batch --config config.yaml        # 逐首分析（会用 API）
python3 -m src.aggregate --config config.yaml    # 聚合出 REPORT.md
```

**断点续跑**：`skip_existing: true` 时，已有结果的曲目直接跳过。中断了重跑即可，不会重复烧 token。

```bash
python3 -m src.batch --config config.yaml --limit 5      # 先试 5 首
python3 -m src.batch --config config.yaml --workers 8    # 覆盖并发数
```

**扫描范围**：`batch` 与 `lyrics.scan` 默认**递归子目录**（`--no-recursive` 关掉）。
歌词配对要求 **`.lrc` 与音频同目录且同名**：`sub/a.flac` 只认 `sub/a.lrc`，不会去父目录找。
`acoustic_cli` 同样默认递归。

---

## 输出

### 逐首 `<曲名>.md`

> 示例说明：**曲名已匿名化**（真实曲名不外泄），下面 6 行声学数值是那条音轨的真实测量结果，
> 可用 `python3 -m src.acoustic_cli` 复算；紧随其后的模型描述段落是**示意文本，不是实测输出**
> （本仓库没有保存那次 API 调用产物，无法核对）。

````markdown
# track-01.flac

- 调性：**F 小调**（相关 0.855）
- 响度：-10.92 dBFS ｜ 波峰因数：10.92 dB
- 亮度（频谱质心）：3521.6 Hz
- 频段：低 0.1644 ／ 中 0.2982 ／ 高 0.5363
- 起音密度：5.17 次/秒

---

（以下为示意文本）这是一首典型的日系高速电子舞曲，带有强烈的 Vocaloid 流行乐与复古街机游戏音乐
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
| `python3 -m src.acoustic_cli <文件或目录> --json out.json` | **只跑 A 路**：本地声学，不联网、不要 Key |
| `python3 -m src.acoustic_cli <目录> --limit N --no-recursive` | 限制数量 / 关掉递归 |
| `python3 -m src.batch --config <file>` | 批量分析整个音乐库（会用 API） |
| `python3 -m src.batch --config <file> --limit N` | 只处理前 N 首（调试） |
| `python3 -m src.batch --config <file> --workers N --no-recursive` | 覆盖并发数 / 只扫第一层 |
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
- **语言分布依赖 `.lrc` 歌词文件**（且必须与音频**同目录同名**），纯音乐或没歌词的曲目会缺失
- **不是音乐推荐系统** —— 它只描述你已有的库，不预测你会喜欢什么
- **只上传前 60 秒**给第三方 API，模型看不到后半首（`batch.transcode_seconds` 可调）
- 曲库规模（**估计值**，无产物可追溯）：本项目约消耗 90 万 token 量级。
  仓库里没有留下那次运行的 `output/` 日志，**这个数字无法复核**，仅作额度预估用
- 库规模（**实测**，可复核）：见下节

### 本机曲库规模（实测，附复算命令）

```bash
cd /path/to/music
find . -type f \( -iname '*.flac' -o -iname '*.mp3' -o -iname '*.wav' \
  -o -iname '*.m4a' -o -iname '*.ogg' \) | wc -l      # 文件数
find . -type f -iname '*.flac' -o -type f -iname '*.mp3' -o -type f -iname '*.wav' | xargs -n1 -P8 \
  ffprobe -v error -show_entries format=duration -of csv=p=0 | awk '{s+=$1} END {print s/3600" 小时"}'
```

实测结果（2026-09-23，作者的本地音乐库，递归含子目录；路径不写进仓库）：

| 指标 | 数值 |
|---|---|
| 音频文件 | **353** 个（349 FLAC + 3 MP3 + 1 WAV；其中 4 个在 `_待替换/` 子目录） |
| 非递归（只看第一层） | 349 个 |
| 总时长 | **21.26 小时**（ffprobe 合计 76540.8 秒） |
| 总字节 | 13,837,769,702 B ≈ **12.89 GiB**（13.84 GB） |

> 早前版本写的「347 首 / 12.9 GB / 20.6 小时」与实测对不上，已按上表更正。
> 统计方法是上面两条命令，任何人都能重跑。

---

## 依赖

| 类型 | 依赖 | 版本 | 必需 |
|---|---|---|---|
| 系统 | `ffmpeg` | 实测 6.1.1（≥ 4.x 应可用） | ✅（转码 + 本地解码） |
| 系统 | `curl` | 任意近期版本 | ✅（API 调用） |
| Python | `numpy` | `==1.26.4`（`requirements.txt` 已钉死） | ✅（声学分析） |
| Python | `PyYAML` | `==6.0.1` | ✅（配置） |
| Python | Python 本体 | ≥ 3.10，**仅在 3.12.3 上实测** | ✅ |

国内装不上 PyPI 就用镜像：`pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple`

**没有** `requests`、`librosa`、`torch`、`soundfile`。声学部分是从 `ffmpeg` 的原始 PCM 输出直接算的。

---

## 隐私与版权

| 事项 | 现状 |
|---|---|
| 上传内容 | B 路会把**前 60 秒**音频 base64 后 POST 给第三方 API（默认阿里云百炼）。整首不上传 |
| 不想上传怎么办 | 只用 `python3 -m src.acoustic_cli`，那条路不联网、不需要 Key |
| API Key | 写在权限 0600 的 curl 配置文件里用 `-K` 读取，用完删除；**不进 argv**，不会出现在 `ps` 里 |
| 临时文件 | `work_dir` 收窄到 0700，`payload.json` / `resp.sse` 为 0600 |
| 分析产物 | `output/`、`*.log`、`*.jsonl` 已加入 `.gitignore` —— 逐首画像含曲名，属于隐私数据 |
| 产物里的路径 | 只记相对文件名（`track.flac`），不记本机绝对路径 |
| 仓库里的示例 | 示例曲名已匿名化（`track-01.flac`） |

---

## License

[MIT](LICENSE)
