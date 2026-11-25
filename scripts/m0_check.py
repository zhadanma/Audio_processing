#!/usr/bin/env python
"""M0 验证脚本：环境报告 + MSST(htdemucs_6s) 分离耗时/显存 + 可选 DrumSep 二级验证。

用法:
    python scripts/m0_check.py --input path/to/song.mp3
    python scripts/m0_check.py --synthetic --minutes 4
    python scripts/m0_check.py --synthetic --minutes 4 --drumsep
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / ".scratch" / "m0"
MSST_DIR = ROOT / ".scratch" / "tools" / "msst"

HTDEMUCS_6S = {
    "name": "htdemucs_6s",
    "model_type": "htdemucs",
    "config": MSST_DIR / "configs" / "config_htdemucs_6stems.yaml",
    "weights": ROOT / ".scratch" / "tools" / "demucs_6s.th",
}
DRUMSEP = {
    "name": "drumsep_htdemucs",
    "model_type": "htdemucs",
    "config": MSST_DIR / "configs" / "config_drumsep.yaml",
    "weights": ROOT / ".scratch" / "tools" / "drumsep" / "model_drumsep_htdemucs.th",
}


def env_report(device_arg: str) -> dict:
    import torch

    rep = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
    }
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        rep["gpu"] = props.name
        rep["vram_gb"] = round(props.total_memory / 1024**3, 1)
    rep["device_used"] = "cuda" if (torch.cuda.is_available() and device_arg != "cpu") else "cpu"

    try:
        import sounddevice as sd

        rep["audio_output"] = str(sd.query_devices(kind="output")["name"])
    except Exception as exc:
        rep["audio_output"] = f"unavailable: {exc}"
    return rep


def gen_synthetic(path: Path, minutes: float, sr: int = 44100) -> None:
    """合成一段"有鼓/贝斯/和弦"的测试音频（仅用于计时与流水线验证，不用于质量评估）。"""
    import numpy as np

    total = int(sr * minutes * 60)
    mono = np.zeros(total, dtype=np.float32)
    beat = 0.5  # 120 BPM
    beats = int(total / sr / beat)
    rng = np.random.default_rng(42)

    def add(sig: np.ndarray, at: float) -> None:
        i = int(at * sr)
        if i >= total:
            return
        end = min(i + len(sig), total)
        mono[i:end] += sig[: end - i]

    tt = np.arange(int(sr * 0.4)) / sr
    kick = (np.exp(-tt * 18) * np.sin(2 * np.pi * 55 * tt)).astype(np.float32) * 0.5
    hat_env = np.exp(-np.arange(int(sr * 0.05)) / sr * 60).astype(np.float32)

    bass_notes = [55.0, 55.0, 82.41, 73.42]
    chords = [
        (220.0, 261.63, 329.63),
        (196.0, 246.94, 293.66),
        (174.61, 220.0, 261.63),
        (196.0, 246.94, 329.63),
    ]

    for b in range(beats):
        t0 = b * beat
        add(kick, t0)
        if b % 2 == 1:
            sn = (rng.standard_normal(int(sr * 0.08)) * 0.15).astype(np.float32)
            sn *= np.exp(-np.arange(len(sn)) / sr * 30).astype(np.float32)
            add(sn, t0)
        add((rng.standard_normal(len(hat_env)) * 0.03).astype(np.float32) * hat_env, t0 + beat / 2)

        f = bass_notes[b % 4]
        tb = np.arange(int(sr * 0.45)) / sr
        bass = (0.25 * np.sin(2 * np.pi * f * tb) * np.minimum(1, tb * 20)).astype(np.float32)
        add(bass, t0)

        if b % 2 == 0:
            dur = beat * 2 * 0.9
            tc = np.arange(int(sr * dur)) / sr
            env = np.minimum(1.0, np.minimum(tc * 10, (dur - tc) * 10)).astype(np.float32)
            chord = np.zeros_like(env)
            for cf in chords[(b // 2) % 4]:
                chord += (
                    np.sin(2 * np.pi * cf * tc).astype(np.float32)
                    + 0.3 * np.sin(2 * np.pi * cf * 2 * tc).astype(np.float32)
                )
            add(chord * env * 0.04, t0)

    mono = np.tanh(mono).astype(np.float32)
    stereo = np.stack([mono, mono * 0.9])
    pcm16 = (np.clip(stereo, -1, 1).T * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm16.tobytes())


def audio_info(path: Path) -> dict:
    import soundfile as sf

    info = sf.info(str(path))
    return {
        "path": str(path),
        "duration_s": round(info.duration, 1),
        "sample_rate": info.samplerate,
        "channels": info.channels,
    }


def _vram_sampler(stop: dict, result: dict) -> None:
    peak = 0
    while not stop.get("stop"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5,
            )
            val = int(out.stdout.strip().splitlines()[0])
            peak = max(peak, val)
        except Exception:
            pass
        time.sleep(0.5)
    result["peak_mb"] = peak


def run_msst(job: dict, src: Path, out_dir: Path, device_index: int = 0) -> dict:
    in_dir = out_dir / "input"
    stems_dir = out_dir / "stems"
    in_dir.mkdir(parents=True, exist_ok=True)
    stems_dir.mkdir(parents=True, exist_ok=True)
    target = in_dir / src.name
    if target.resolve() != src.resolve():
        shutil.copy2(src, target)

    cmd = [
        sys.executable, str(MSST_DIR / "inference.py"),
        "--model_type", job["model_type"],
        "--config_path", str(job["config"]),
        "--start_check_point", str(job["weights"]),
        "--input_folder", str(in_dir),
        "--store_dir", str(stems_dir),
        "--device_ids", str(device_index),
    ]
    stop: dict = {}
    vram: dict = {}
    sampler = threading.Thread(target=_vram_sampler, args=(stop, vram), daemon=True)
    sampler.start()
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=str(MSST_DIR), capture_output=True, text=True)
        elapsed = time.perf_counter() - t0
    finally:
        stop["stop"] = True
        sampler.join(timeout=3)

    if proc.returncode != 0:
        tail = (proc.stdout + "\n" + proc.stderr)[-3000:]
        raise RuntimeError(f"MSST 推理失败（{job['name']}）:\n{tail}")

    files = sorted(str(p) for p in stems_dir.glob("*") if p.is_file())
    return {
        "model": job["name"],
        "wall_s": round(elapsed, 1),
        "vram_used_peak_mb": vram.get("peak_mb"),
        "files": files,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="M0 可行性验证（MSST 推理）")
    ap.add_argument("--input", help="输入音频文件")
    ap.add_argument("--synthetic", action="store_true", help="生成合成测试音频")
    ap.add_argument("--minutes", type=float, default=4.0, help="合成音频时长（分钟）")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--drumsep", action="store_true", help="对 drums 轨追加 DrumSep 二级验证")
    args = ap.parse_args()

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    report: dict = {"env": env_report(args.device)}

    if args.synthetic:
        src = out_root / f"synthetic_{args.minutes:g}min.wav"
        print(f"[m0] 生成合成测试音频 {src} ...")
        gen_synthetic(src, args.minutes)
    elif args.input:
        src = Path(args.input).expanduser().resolve()
    else:
        ap.error("需要 --input <音频文件> 或 --synthetic")

    if not src.exists():
        raise SystemExit(f"输入文件不存在: {src}")

    print(f"[m0] 输入音频: {src}")
    report["input"] = audio_info(src)
    print(f"[m0] 时长 {report['input']['duration_s']} s, "
          f"{report['input']['sample_rate']} Hz, {report['input']['channels']} ch")

    print("[m0] 阶段1: htdemucs_6s 六轨分离 ...")
    res1 = run_msst(HTDEMUCS_6S, src, out_root / "stage1_htdemucs_6s")
    report["htdemucs_6s"] = res1
    print(f"[m0]   完成: {res1['wall_s']} s（含模型加载），显存峰值约 {res1['vram_used_peak_mb']} MB")
    for f in res1["files"]:
        info = audio_info(Path(f))
        print(f"[m0]   - {Path(f).name}: {info['duration_s']} s")

    if args.drumsep:
        drums = next((Path(f) for f in res1["files"] if "drum" in Path(f).name.lower()), None)
        if drums is None:
            raise SystemExit("未找到 drums stem，无法运行 DrumSep")
        print(f"[m0] 阶段2: DrumSep 鼓组细分（输入 {drums.name}）...")
        res2 = run_msst(DRUMSEP, drums, out_root / "stage2_drumsep")
        report["drumsep"] = res2
        print(f"[m0]   完成: {res2['wall_s']} s，显存峰值约 {res2['vram_used_peak_mb']} MB")
        for f in res2["files"]:
            print(f"[m0]   - {Path(f).name}")

    report_path = out_root / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[m0] 报告已写入 {report_path}")


if __name__ == "__main__":
    main()
