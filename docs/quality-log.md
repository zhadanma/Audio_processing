# 质量记录（quality-log）

模型版本、机器环境、耗时、显存与听感评分记录。每次模型升级或分离参数调整后追加记录，作为回归基线。

## 评分说明

听感按 1~5 分：1 = 不可用；3 = 明显串音但可用；5 = 几乎无串音。逐项记录人声残留、鼓组串音、低频浑浊、伪影。

## 记录

### 2026-11-24 · M0 环境与可行性验证

**环境**

| 项 | 值 |
|---|---|
| 机器 | RTX 4060 Laptop GPU 8 GB |
| Python | 3.12.15（`.scratch/m0-venv`，`--system-site-packages` 引用 crea3） |
| torch | 2.14.1+cu130（复用本机 crea3 环境，CUDA 验证通过） |
| 系统 | Windows 11 |
| ffmpeg | 7.1.0（conda `musep` 环境，conda-forge GPL 构建，仅开发期使用；分发换 LGPL） |

**环境处理记录（网络与依赖）**

- PyTorch CUDA 轮子下载（约 2.5 GB）因网络限速（约 150~220 KB/s，GitHub/阿里云/PyTorch CDN 均慢）放弃，改为复用本机 `crea3` 环境的 torch 2.14.1+cu130。
- torchaudio 上游实际止于 2.11（与 torch 2.14 无官方配对版本）；实测 **torchaudio 2.11.0+cu130 可在 torch 2.14.1 下 import**，但其音频 I/O 接口改为强制依赖 TorchCodec。本项目推理链全程使用 soundfile/librosa 做 I/O，不依赖 torchaudio I/O。
- demucs PyPI 版 4.0.1 缺少 `demucs.api` 模块。分离统一改用 MSST（Music-Source-Separation-Training）`inference.py` 推理，htdemucs_6s 与 DrumSep 均由其加载；demucs 包仅作为模型结构依赖。
- MSST 推理栈安装于 `.scratch/m0-venv`：librosa、soundfile、soxr、scipy、matplotlib、omegaconf、ml_collections、einops、julius、dora-search、lameenc、openunmix、demucs==4.0.1（--no-deps）。

**模型权重可用性**

| model_id | 计划来源 | 状态 | 处置 |
|---|---|---|---|
| `htdemucs_6s` | demucs 官方（dl.fbaipublicfiles.com） | **已下载并跑通** `demucs_6s.th`，MSST `config_htdemucs_6stems.yaml`，6 轨 | 2026-11-25 实测通过，见下文 |
| `drumsep_mdx23c`（6 轨，aufr33+jarredou v0.1） | `github.com/jarredou/models` Release | **失效**：账号 404，Release 链接不可用（风险 R-3 发生） | 改用 ZFTurbo v1.0.5 Release 的 `model_drumsep_htdemucs.th`（160 MB，HDemucs 架构，4 轨：kick/snare/cymbals/toms，`config_drumsep.yaml`）；**已跑通**，但 6 轨需求未满足 |
| karaoke（主唱/和声） | 候选 `becruily/mel-band-roformer-karaoke`（HF，34 likes） | **仍待下载验证** | MSST `model_type=mel_band_roformer` 推理 |

**测量结果**

> 2026-11-24 的合成音频计时计划已由 2026-11-25 的真实歌曲实测取代，见下一节。

| 日期 | 阶段 | 模型 | 素材 | 耗时 | 显存峰值 | 听感 | 备注 |
|---|---|---|---|---|---|---|---|
| 2026-11-24 | 一级 | htdemucs_6s | 合成 4 min | — | — | 不适用（合成音频） | 计划用，未执行 |
| 2026-11-24 | 二级-鼓 | DrumSep htdemucs（4 轨） | — | — | — | — | 计划用，未执行 |
| 2026-11-24 | 二级-人声 | Karaoke | — | — | — | — | 无权重 |

**备注**

- 合成音频用于计时和流水线验证，不用于质量评估；真实歌曲听感需用户提供测试曲目后补充。
- 应用端自动权限审核服务间歇性超时，M0 执行阶段被暂时阻塞（非项目问题）。

---

### 2026-11-25 · M0 实测（真实歌曲，流水线跑通）

**素材**：`BENI - 瞳をとじて.mp3`，340.5 s，44.1 kHz / 立体声（放在 `songs/`，不入版本库）

**环境**：RTX 4060 Laptop 8 GB / 驱动 610.74 / torch 2.14.1+cu130 / venv Python 3.12.15 / CUDA fp32

**测量结果**（`scripts/m0_check.py`；显存为 `nvidia-smi` 全卡占用峰值，含桌面与浏览器，非纯模型占用）

| 阶段 | 模型 | 推理配置 | 耗时 | 显存峰值 | 输出 |
|---|---|---|---|---|---|
| 一级 | htdemucs_6s | chunk 11 s / batch 8（上游默认） | 96.8 s | 7708 MB | 6 轨 16-bit WAV |
| 一级 | htdemucs_6s | chunk 11 s / **batch 1** | 52.3 s | 6726 MB | 6 轨 16-bit WAV |
| 一级 | htdemucs_6s | chunk 11 s / batch 1（空闲 GPU 复测） | 50.5 s | 2519 MB | 6 轨 16-bit WAV |
| 二级-鼓 | DrumSep htdemucs（4 轨） | chunk 40 s / batch 8（上游默认） | **>20 min 未完成，中止** | 7809 MB | — |
| 二级-鼓 | DrumSep htdemucs（4 轨） | chunk 40 s / **batch 1** | 68.7 s | 5165 MB | kick / snare / cymbals / toms |
| 二级-鼓 | DrumSep htdemucs（4 轨） | chunk 20 s / batch 1 | 69.9 s | 5443 MB | 同上 |

**结论**

1. **性能达标**：5.7 分钟歌曲一级 52.3 s + 二级 68.7 s，全程 121.5 s；线性换算 4 分钟歌曲一级约 37 s，满足 NFR-1（≤90 s），且优于架构 §9.1 的 30~60 s 目标上界。
2. **`batch_size` 是 8 GB 显存的关键参数（新发现，涉及 R-4 / R-6 / FR-803）**：DrumSep 默认 chunk 40 s × batch 8 意味着单次前向 320 s 音频，打满显存后触发 WDDM 分页颠簸——GPU 利用率 100%、功耗却只有约 31 W，20 分钟没有任何输出；改成 batch 1 后 68.7 s 完成（差 17 倍以上）。一级 batch 8 虽能跑完，但显存峰值贴到 7.7 GB 且比 batch 1 慢近 2 倍。**产品在 8 GB 卡上应默认 batch=1，16 GB 以上再放开**，这也直接降低 FR-803 的 OOM 概率。
3. **输出格式偏差**：MSST 在峰值 >1.0 时写 16-bit WAV 而不是 FLAC（AD-4 要求 FLAC stem）。产品侧需显式转码：`--pcm_type FLOAT` 自行编码 FLAC，或统一归一化后写 FLAC。
4. **客观校验**（`scripts/m0_analyze.py`）：
   - 一级六轨求和 vs 原曲残差 **-15.9 dB**。已用 FFT 交叉相关复核对齐：最佳 lag = 0 样本（残差 -16.3 dB），**可排除 mp3 编码延迟导致的对齐偏差**；电平也无异常（原曲峰值 -0.4 / RMS -11.5 dBFS，六轨求和 0.0 / -12.0 dBFS）。故残差来自 6 源模型本身不保证能量守恒（配置 `min_mean_abs=0.001` 还会把极安静的源块置零）。**产品不能假设 sum(stems) == 原曲**，A/B 试听原曲与分轨时会有轻微电平差。
   - 二级四轨求和 vs 鼓轨残差 **-26.9 dB**，明显好于一级。
   - 所有 stem 无削波；vocals 峰值 0.0 dBFS；六轨求和有 2 个样本触及 1.0 → 导出必须默认峰值归一化（FR-501）。
   - toms 轨 RMS -42.2 dB（近乎空轨），此类素材下 DrumSep 的 toms 输出偏弱。
   - 频谱对照图 `docs/m0/2026-11-25-stems_spectrogram.png`：各轨频段分布符合预期（bass 低通、drums 宽带瞬态、vocals 中频），未见空轨或全频噪声等异常。
5. **需求/架构偏差**：DrumSep 实际只有 4 轨（kick/snare/cymbals/toms），**FR-204 要求的 hh/ride/crash 未实现**；架构 §8 的模型表仍写 `drumsep_mdx23c` 6 轨，需修订。
6. **Karaoke（主唱/和声）仍未验证**，权重未下载，是 M2 的最大未知项。

**待办**：人耳听感评分（1~5 分：人声残留 / 鼓组串音 / 低频浑浊 / 伪影）尚未进行。试听素材在 `.scratch/m0/stage1_htdemucs_6s/stems/` 与 `.scratch/m0/stage2_drumsep/stems/`。

**证据归档**：`docs/m0/2026-11-25-report.json`（脚本原始报告）、`docs/m0/2026-11-25-metrics.json`（客观指标）、`docs/m0/2026-11-25-stems_spectrogram.png`（频谱对照）。
