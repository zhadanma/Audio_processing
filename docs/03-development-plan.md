# 音乐分轨处理桌面应用 · 开发计划与里程碑

| 文档信息 | |
|---|---|
| 版本 | v0.1（初稿） |
| 日期 | 2026-11-24 |
| 关联文档 | [需求规格说明书](01-requirements.md) · [架构设计](02-architecture.md) |
| 总工期 | 约 3~4 周（单人、业余时间估算，视 M0 实测调整） |

---

## 1. 环境搭建

> 说明：本机 `py` launcher 已损坏（指向不存在的 `D:\Python`），一律使用 conda 环境。目标 Python 3.11（兼容性优先于 3.13）。

```powershell
conda create -n musep python=3.11 -y
```

```powershell
conda activate musep
```

安装 PyTorch（CUDA 12.4 轮子，适配 RTX 4060）：

```powershell
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
```

安装应用依赖：

```powershell
pip install demucs==4.0.1 sounddevice soundfile pyqtgraph PySide6 "numpy<2" soxr pydantic audio-separator
```

开发期安装 ffmpeg（分发阶段替换为 LGPL 构建，见架构文档 AD-6）：

```powershell
winget install --id Gyan.FFmpeg --accept-source-agreements
```

> 以上版本为**基线**，以 M0 验证结果为准并写入 `pyproject.toml` 锁定。若 `audio-separator` 需 GPU 推理，按其文档选择对应的 GPU 发行包。

验证环境：

```powershell
python -c "import torch,demucs,sounddevice,PySide6,pyqtgraph; print(torch.__version__, torch.cuda.is_available())"
```

---

## 2. 仓库结构

按[架构设计 §4](02-architecture.md) 的目录结构初始化仓库。`main` 分支保持可运行；每个里程碑打 tag（`v0.1.0` / `v0.2.0` / `v1.0.0`）。

---

## 3. 里程碑

### M0 · 环境与可行性验证（0.5~1 天）

**目标**：证明"6 轨 + 级联细分"在本机可跑、速度可接受、依赖版本可锁定。

任务：

1. 按 §1 搭建环境，解决依赖冲突，记录**最终可用的版本组合**
2. 编写 `scripts/m0_check.py`：
   - 输入：`tests/fixtures/source/demo.mp3`（用户自备一首 3~5 分钟歌曲）
   - 步骤：htdemucs_6s 全曲分离 → 对 drums 输出跑 DrumSep → 对 vocals 输出跑 Karaoke
   - 记录：各阶段耗时、峰值显存、输出轨数与时长，写入 `.scratch/m0/report.txt`
3. 听感初评：每级输出人工试听，记录串音与伪影的主观感受（写入 `docs/quality-log.md`）
4. 最小播放验证：20 行脚本用 sounddevice 播放 6 轨 wave 混合，确认设备工作正常

**退出标准**：

- 4 分钟歌曲六轨分离 ≤ 90 s（GPU）
- DrumSep 与 Karaoke 模型均能加载并产出预期轨道
- 依赖版本组合写入文档并在后续锁定
- 若任一模型不可用 → 对应需求（FR-204/205/206）降级为"隐藏功能"并在需求评审记录

### M1 · MVP v0.1（5~8 天）

**目标**：完成 P0 需求的完整闭环：导入 → 六轨分离 → 调音 → 导出。

任务（按依赖顺序）：

1. 应用骨架：`main.py`、主窗口布局、设置读写、全局异常钩子
2. `Importer`：ffmpeg 解码、44.1 kHz/立体声/float32 统一、元数据
3. `Demucs6sAdapter` + `SeparationPipeline`（单阶段）：进度、取消、原子落盘
4. `ProjectStore`：项目创建/打开、`project.json`、备份恢复
5. `AudioEngine`：多轨加载、播放/暂停/seek、`ResolvedMix`、增益斜坡
6. `MixParams` + `MixParamsResolver`：静音/独奏/组规则（先按平铺轨道实现，组规则随 M2 接入）
7. `WaveformPeaks` + `WaveformView`：峰值计算、多轨绘制、播放头
8. `TrackTree` + `TransportBar`：M/S/滑块、快捷键基础
9. `MixdownExporter`：混音导出 WAV/FLAC、峰值归一化、进度与取消
10. 打包 spike：PyInstaller `--onedir` 打一次包，确认 torch 可用（风险 R-2 提前暴露）

**退出标准**：

- 三首不同风格歌曲完整走通流程，导出的混音与试听一致（同一份混音数学）
- 分离/导出中途取消不损坏项目
- 播放期间调整滑块无爆音、无 underrun
- PyInstaller 产物能启动并完成一次六轨分离

### M2 · v0.2（4~6 天）

**目标**：完成 P1 需求：级联细分、项目体验、设置完善。

任务：

1. `DrumsepAdapter`、`KaraokeAdapter` 接入流水线；轨道树支持组展开/收起，子轨替换父轨参与混音（FR-204/205/308）
2. `ModelManager` UI：模型状态列表、下载进度、取消/重试、离线导入
3. 混音状态自动保存、最近项目列表、缓存占用管理（FR-602/604）
4. 快捷键完善、主音量、音频输出设备选择（FR-305/701）
5. 单轨批量导出（FR-503）、默认导出目录（FR-505）
6. MP3 导出（ffmpeg 可用时，FR-502）
7. 长音频提示与内存保护（FR-105）

**退出标准**：P1 需求全部通过验收；细分结果的组增益/静音/独奏行为符合需求 §3.3.2。

### M3 · v1.0 发布（4~6 天）

**目标**：可交付给非开发用户的稳定版本。

任务：

1. 首次运行向导：模型检查/下载、计算设备自检
2. 错误处理全面覆盖（FR-801~803）：ffmpeg 缺失、OOM、下载失败、磁盘不足、项目损坏
3. 日志系统与"关于"页（FR-704）：版本、许可、质量声明、日志入口
4. 正式打包：PyInstaller onedir、ffmpeg vendor（LGPL）、可选 Inno Setup 安装器
5. 完整 QA 清单执行 + 性能复测（同 M0 基准曲目）
6. 文档收尾：README、质量记录归档、许可复核（R-7 相关）

**退出标准**：干净 Windows 11 机器（无 Python/ffmpeg）安装后全流程可用；QA 清单 100% 通过。

### 里程碑总览

| 里程碑 | 交付 | 估算 |
|---|---|---|
| M0 | 环境验证报告 + 锁定依赖 | 0.5~1 天 |
| M1 | MVP v0.1 | 5~8 天 |
| M2 | v0.2 | 4~6 天 |
| M3 | v1.0 | 4~6 天 |

---

## 4. 验证与 QA

### 4.1 听感测试协议

- 参考曲目（3 首）：流行（人声/鼓/贝斯密集）、钢琴为主、电子（合成器多）
- 每级输出按 1~5 分记录：人声残留、鼓组串音、低频浑浊、伪影/水声感
- 结果追加到 `docs/quality-log.md`（含模型版本、耗时、机器负载），作为模型升级的回归基线

### 4.2 QA 清单（M1 起每里程碑回归）

- [ ] 导入：wav/mp3/flac/m4a/ogg 各一，错误格式给出提示
- [ ] 3/6/10 分钟歌曲的分离耗时与内存
- [ ] 分离中取消 → 无半成品、项目可继续使用
- [ ] 分离中关闭窗口 → 按提示行为执行
- [ ] 播放中快速拖动多个滑块 → 无爆音、无崩溃
- [ ] 只想贝斯：静音其余轨后导出，与"仅导出贝斯轨"结果一致
- [ ] 独奏 + 静音组合的组规则抽查（需求 §3.3.2 真值表）
- [ ] 展开/收起细分组 → 播放内容正确切换
- [ ] 导出 WAV/FLAC 重新导入校验时长与峰值
- [ ] 断网状态：已有模型时全功能可用
- [ ] 模型目录被删除后再次分离 → 自动重新下载
- [ ] 损坏 project.json → 从 .bak 恢复提示
- [ ] 拔掉/切换音频设备后播放 → 不崩溃（可提示）

---

## 5. 编码规范与约定

- Python 3.11，全量类型注解；`ruff`（lint + format）与 `pytest` 本地执行
- 领域层（`core/separation/project/io`）不 import Qt；UI 通过控制器调用
- 长操作一律走 `JobRunner`，UI 线程禁止 sleep/join/同步等待
- 异常约定：领域异常映射为用户可行动文案；禁止裸 `except`
- 日志：`logging` + 滚动文件（`%LOCALAPPDATA%/AudioProcessing/logs/`），回调线程禁止记录
- 提交粒度：一个功能一个提交；提交信息说明"为什么"

---

## 6. 依赖清单（基线，M0 锁定）

```toml
[project]
name = "audio-processing"
version = "0.1.0"
requires-python = ">=3.11,<3.13"
dependencies = [
  "PySide6>=6.7,<6.9",
  "numpy>=1.26,<2.0",
  "sounddevice>=0.4.6",
  "soundfile>=0.12",
  "pyqtgraph>=0.13",
  "pydantic>=2.6",
  "demucs==4.0.1",
  "torch>=2.4",
  "torchaudio>=2.4",
  "soxr>=0.3",
  "audio-separator>=0.24",
]
```

> 版本号是待验证基线；M0 之后以实测通过的精确版本回填并锁定（含 CUDA 轮子版本）。

---

## 7. 下一步（M0 具体动作）

1. 创建 conda 环境并安装依赖，解决冲突 → 记录可用版本组合
2. 用户提供一首 3~5 分钟测试歌曲，放到 `tests/fixtures/source/`
3. 编写并运行 `scripts/m0_check.py`，采集耗时/显存/听感
4. 评审本三份文档中的开放问题（需求 Q-1~Q-5、架构 O-1~O-5），拍板后更新文档
