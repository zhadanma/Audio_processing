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
| `htdemucs_6s` | demucs 官方（dl.fbaipublicfiles.com） | **已下载** `5c90dfd2-34c22ccb.th`，MSST `config_htdemucs_6stems.yaml`，6 轨 | 待跑通验证 |
| `drumsep_mdx23c`（6 轨，aufr33+jarredou v0.1） | `github.com/jarredou/models` Release | **失效**：账号 404，Release 链接不可用（风险 R-3 发生） | 改用 ZFTurbo v1.0.5 Release 的 `model_drumsep.th`（167 MB，HDemucs 架构，4 轨：kick/snare/cymbals/toms，`config_drumsep.yaml`）验证流水线；产品需寻找稳定镜像并锁定校验和 |
| karaoke（主唱/和声） | 候选 `becruily/mel-band-roformer-karaoke`（HF，34 likes） | 待下载验证 | MSST `model_type=mel_band_roformer` 推理 |

**测量结果**

| 日期 | 阶段 | 模型 | 素材 | 耗时 | 显存峰值 | 听感 | 备注 |
|---|---|---|---|---|---|---|---|
| 2026-11-24 | 一级 | htdemucs_6s | 合成 4 min | 待测 | 待测 | 不适用（合成音频） | 计时用 |
| 2026-11-24 | 二级-鼓 | DrumSep htdemucs（4 轨） | 待测 | 待测 | 待测 | 待测 | — |
| 2026-11-24 | 二级-人声 | Karaoke | 待测 | 待测 | 待测 | 待测 | — |

**备注**

- 合成音频用于计时和流水线验证，不用于质量评估；真实歌曲听感需用户提供测试曲目后补充。
- 应用端自动权限审核服务间歇性超时，M0 执行阶段被暂时阻塞（非项目问题）。
