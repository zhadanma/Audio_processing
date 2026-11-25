#!/usr/bin/env python
"""M0 分离结果的客观校验：重建误差、电平统计、频谱图。

只做机器可判定的检查（不能替代人耳听感）：
1. 重建误差：所有 stem 求和 vs 原始混音/DrumSep 输入，残差能量比
2. 电平统计：每轨 RMS / 峰值 / 削波样本占比
3. 频谱图：把各轨频谱画成一张对照图，便于肉眼发现异常（如空轨、全频噪声）

用法:
    python scripts/m0_analyze.py --original "songs/xxx.mp3" \
        --stems .scratch/m0/stage1_htdemucs_6s/stems \
        --sub-stems .scratch/m0/stage2_drumsep/stems \
        --sub-input .scratch/m0/stage1_htdemucs_6s/stems/drums.wav \
        --out .scratch/m0
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import soundfile as sf


def load(path: Path) -> tuple[np.ndarray, int]:
    """读成立体声 (2, N) float32。"""
    audio, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    return np.ascontiguousarray(audio[:, :2].T), sr


def db(value: float) -> float:
    return round(20 * math.log10(max(value, 1e-12)), 1)


def level_stats(audio: np.ndarray) -> dict:
    peak = float(np.abs(audio).max())
    rms = float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))
    clipped = int(np.count_nonzero(np.abs(audio) >= 0.999))
    return {
        "peak_dbfs": db(peak),
        "rms_dbfs": db(rms),
        "clipped_samples": clipped,
        "clipped_pct": round(100 * clipped / audio.size, 4),
    }


def residual_db(target: np.ndarray, approx: np.ndarray) -> float:
    n = min(target.shape[1], approx.shape[1])
    diff = target[:, :n] - approx[:, :n]
    ref = float(np.sqrt(np.mean(np.square(target[:, :n], dtype=np.float64))))
    err = float(np.sqrt(np.mean(np.square(diff, dtype=np.float64))))
    return db(err / max(ref, 1e-12))


def spectrograms(rows: list[tuple[str, Path]], out_png: Path, sr_hint: int = 44100) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import librosa

    # Windows 上默认字体没有中文，指定雅黑/黑体，避免标签变成方框
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(len(rows), 1, figsize=(13, 1.6 * len(rows)), sharex=True)
    if len(rows) == 1:
        axes = [axes]
    for ax, (name, path) in zip(axes, rows):
        audio, sr = load(path)
        mono = audio.mean(axis=0)
        spec = np.abs(librosa.stft(mono, n_fft=2048, hop_length=512))
        spec_db = librosa.amplitude_to_db(spec, ref=np.max)
        ax.imshow(spec_db, origin="lower", aspect="auto", cmap="magma",
                  extent=(0, len(mono) / sr, 0, sr / 2000))
        ax.set_ylabel(f"{name}\nkHz", rotation=0, labelpad=28, fontsize=8)
        ax.tick_params(labelsize=7)
    axes[-1].set_xlabel("时间 (s)")
    fig.suptitle("M0 分轨频谱对照", fontsize=11)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=110)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description="M0 分离结果客观校验")
    ap.add_argument("--original", required=True, help="原始歌曲")
    ap.add_argument("--stems", required=True, help="一级 stem 目录")
    ap.add_argument("--sub-stems", help="二级（DrumSep）stem 目录")
    ap.add_argument("--sub-input", help="二级模型的输入（drums stem）")
    ap.add_argument("--out", default=".scratch/m0", help="输出目录")
    ap.add_argument("--no-plot", action="store_true", help="跳过频谱图")
    args = ap.parse_args()

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {}

    original, sr = load(Path(args.original).resolve())
    stems = {p.stem: p for p in sorted(Path(args.stems).resolve().glob("*.wav"))}
    stems.update({p.stem: p for p in sorted(Path(args.stems).resolve().glob("*.flac"))})
    arrays = {name: load(p)[0] for name, p in stems.items()}

    report["sample_rate"] = sr
    report["duration_s"] = round(original.shape[1] / sr, 1)
    report["stems"] = {name: level_stats(a) for name, a in arrays.items()}

    total = np.zeros_like(original)
    for a in arrays.values():
        n = min(total.shape[1], a.shape[1])
        total[:, :n] += a[:, :n]
    report["mix_sum"] = level_stats(total)
    report["stage1_reconstruction_db"] = residual_db(original, total)

    if args.sub_stems:
        sub = {p.stem: p for p in sorted(Path(args.sub_stems).resolve().glob("*.wav"))}
        sub_arrays = {name: load(p)[0] for name, p in sub.items()}
        report["sub_stems"] = {name: level_stats(a) for name, a in sub_arrays.items()}
        if args.sub_input:
            src, _ = load(Path(args.sub_input).resolve())
            acc = np.zeros_like(src)
            for a in sub_arrays.values():
                n = min(acc.shape[1], a.shape[1])
                acc[:, :n] += a[:, :n]
            report["stage2_reconstruction_db"] = residual_db(src, acc)

    (out_dir / "metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_plot:
        rows = [(n, p) for n, p in stems.items()]
        if args.sub_stems:
            rows += [(f"drums/{p.stem}", p) for p in
                     sorted(Path(args.sub_stems).resolve().glob("*.wav"))]
        spectrograms(rows, out_dir / "stems_spectrogram.png", sr)
        report["spectrogram"] = str(out_dir / "stems_spectrogram.png")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[m0] 指标已写入 {out_dir / 'metrics.json'}")


if __name__ == "__main__":
    main()
