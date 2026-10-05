"""
Padding x temporal-aggregation evaluation of the deployed pipeline.

Question: for short ROIs (< 3 s, BirdNET's fixed input), what should
fill the rest of BirdNET's window, and does combining BirdNET scores
across snippets over time improve precision/recall?

Pipeline under test = what the ESP32 actually does (not the backend's
whole-file reference): 16 kHz audio in consecutive 10 s windows,
firmware/birdcall_device/tools/verify/edge_reference.py (the
bit-exact Python model of the firmware DSP: 1 kHz HPF before
detection, 2 x median extent, peak gate), exact ROI, no padding.
The peak-gate factor (ROI_MIN_PEAK_FACTOR) is a third factor:
8 (deployed), 4, and 2 (= no extra gate beyond the 2 x median
threshold).

Padding variants (ROIs >= 3 s are identical in all of them):

  silence   ROI as uploaded today; BirdNET appends digital silence
  noise     ROI + noise synthesised from the ROI's own quietest
            frames (server-side, no extra 4G data)
  repeat    ROI tiled (10 ms crossfades) to 3 s (server-side)
  context   3 s of real audio centred on the ROI, taken from the
            device's filtered window (costs extra 4G data)

plus "raw": BirdNET on the original full recordings (upper bound;
no ROIs).

BirdNET is run once per variant with a low threshold (0.05), large
top-k and no species list; the location filter, confidence threshold,
top-10-per-interval and temporal aggregation are applied afterwards
in analysis (stage 3), so every combination is compared on identical
BirdNET output.

Dataset caveat: Western Amazon (Peru) soundscapes, not Sri Lanka.
The location filter therefore uses the recording site (approx.
-12.53, -69.05, Madre de Dios -- the dataset ships no coordinates)
and each file's date. Relative differences between variants carry
over; absolute numbers will differ for Sri Lankan birds.

Stages are resumable (outputs are skipped if present):

    cd <repo root>
    backend/.venv/Scripts/python evaluation_ea/run_padding_aggregation_eval.py [--files N]
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import butter, istft, resample_poly, sosfilt, stft

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "firmware" / "birdcall_device" / "tools" / "verify"))

import edge_reference  # noqa: E402
from src.core.config import settings  # noqa: E402
from src.services.birdnet import BirdNetService  # noqa: E402

EVAL = ROOT / "evaluation_ea"
DATA = EVAL / "soundscape_data"
OUT = EVAL / "results" / "padding_aggregation"
WORK = OUT / "_clips"  # temporary WAVs, deleted after each BirdNET run

SR = 16000
WINDOW_S = 10
BIRDNET_S = 3.0
SITE = (-12.53, -69.05)
VARIANTS = ["silence", "noise", "repeat", "context"]
GATES = [8, 4, 2]

RUN_THRESHOLD = 0.05
RUN_TOP_K = 25
SERVER_TOP_K = settings.birdnet_max_predictions_per_interval  # 10


def log(message: str) -> None:
    print(time.strftime("%H:%M:%S"), message, flush=True)


# ============================================================
# Stage 1: device ROIs and padded clips
# ============================================================


def crossfade_concat(a: np.ndarray, b: np.ndarray, fade: int) -> np.ndarray:
    fade = min(fade, len(a), len(b))
    if fade == 0:
        return np.concatenate([a, b])
    ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    mixed = a[-fade:] * (1 - ramp) + b[:fade] * ramp
    return np.concatenate([a[:-fade], mixed, b[fade:]])


def noise_like(roi: np.ndarray, length: int, seed: int) -> np.ndarray:
    """Noise with the spectrum of the ROI's quietest 20% of frames."""
    nper = 256
    if len(roi) < nper * 2:
        profile = np.full(nper // 2 + 1, np.sqrt(np.mean(roi**2)) + 1e-9)
    else:
        _, _, z = stft(roi, SR, nperseg=nper, noverlap=nper // 2)
        mag = np.abs(z)
        frame_energy = (mag**2).sum(axis=0)
        quiet = frame_energy <= np.percentile(frame_energy, 20)
        profile = mag[:, quiet].mean(axis=1)
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(length + nper * 2).astype(np.float32)
    _, _, zw = stft(white, SR, nperseg=nper, noverlap=nper // 2)
    zs = zw / (np.abs(zw) + 1e-12) * profile[:, None]
    _, shaped = istft(zs, SR, nperseg=nper, noverlap=nper // 2)
    return shaped[nper: nper + length].astype(np.float32)


def make_clip(variant: str, roi: np.ndarray, window: np.ndarray,
              roi_start_sample: int, seed: int) -> tuple[np.ndarray, int, int]:
    """
    Returns (clip, origin_sample, real_end_sample), in window samples:
    clip time 0 is window sample `origin`; real (non-synthetic) audio
    in the clip ends at window sample `real_end`.
    """
    need = int(BIRDNET_S * SR)
    roi_end_sample = roi_start_sample + len(roi)

    if len(roi) >= need or variant == "silence":
        return roi, roi_start_sample, roi_end_sample

    fade = int(0.010 * SR)

    if variant == "noise":
        fill = noise_like(roi, need - len(roi) + fade, seed)
        return crossfade_concat(roi, fill, fade)[:need], roi_start_sample, roi_end_sample

    if variant == "repeat":
        clip = roi
        while len(clip) < need:
            clip = crossfade_concat(clip, roi, fade)
        return clip[:need], roi_start_sample, roi_end_sample

    if variant == "context":
        centre = (roi_start_sample + roi_end_sample) // 2
        start = max(0, min(centre - need // 2, len(window) - need))
        return window[start: start + need], start, start + need

    raise ValueError(variant)


def stage_rois(files: list[Path], gate: int, out: Path, work: Path) -> pd.DataFrame:
    rois_csv = out / "rois.csv"
    if rois_csv.exists() and all(
        (work / v).exists() or (out / f"predictions_{v}.csv").exists()
        for v in VARIANTS
    ):
        return pd.read_csv(rois_csv, dtype={"clip_id": str})

    out.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(work, ignore_errors=True)
    for variant in VARIANTS:
        (work / variant).mkdir(parents=True)
    edge_reference.MIN_PEAK_FACTOR = gate

    sos = butter(4, 1000.0 / (SR / 2), btype="highpass", output="sos")
    rows = []
    window_len = WINDOW_S * SR

    for file_index, path in enumerate(files, 1):
        audio, sr = sf.read(path, dtype="float32")
        audio = resample_poly(audio, 1, sr // SR).astype(np.float32)
        n_windows = len(audio) // window_len
        kept = rejected = 0

        for w in range(n_windows):
            raw = audio[w * window_len: (w + 1) * window_len]
            result = edge_reference.edge_pipeline(raw, SR)
            rejected += result.rejected
            if not result.rois:
                continue
            # The device's filtered, normalized window (as in edge_pipeline).
            filtered = sosfilt(sos, raw).astype(np.float32)
            window = filtered / result.band_peak

            for index, start_s, end_s, samples in result.rois:
                roi_start = max(0, int(round(start_s * SR)))
                clip_id = f"{file_index:02d}_{w:04d}_{index:02d}"
                for variant in VARIANTS:
                    clip, origin, real_end = make_clip(
                        variant, samples, window, roi_start, seed=zlib.crc32(clip_id.encode()))
                    sf.write(work / variant / f"{clip_id}.wav",
                             np.clip(clip, -1, 1), SR, subtype="PCM_16")
                    if variant == "silence":
                        rows.append({
                            "clip_id": clip_id, "filename": path.name,
                            "window_start_s": w * WINDOW_S,
                            "roi_start_s": w * WINDOW_S + start_s,
                            "roi_end_s": w * WINDOW_S + end_s,
                            "roi_duration_s": end_s - start_s,
                            "noise_floor_dbfs": result.noise_floor_dbfs,
                        })
                    if variant == "context":
                        rows[-1]["context_origin_s"] = w * WINDOW_S + origin / SR
                        rows[-1]["context_end_s"] = w * WINDOW_S + real_end / SR
                kept += 1

        log(f"gate x{gate} [{file_index}/{len(files)}] {path.name}: {n_windows} windows, "
            f"{kept} ROIs, {rejected} quiet regions rejected")

    df = pd.DataFrame(rows, columns=[
        "clip_id", "filename", "window_start_s", "roi_start_s", "roi_end_s",
        "roi_duration_s", "noise_floor_dbfs", "context_origin_s", "context_end_s"])
    df.to_csv(rois_csv, index=False)
    return pd.read_csv(rois_csv, dtype={"clip_id": str})


# ============================================================
# Stage 2: BirdNET runs
# ============================================================


def run_birdnet(paths: list[Path]) -> pd.DataFrame:
    model = BirdNetService._get_or_load_model()
    result = BirdNetService._predict(
        model,
        [str(p) for p in paths],
        top_k=RUN_TOP_K,
        default_confidence_threshold=RUN_THRESHOLD,
        batch_size=settings.birdnet_batch_size,
        n_workers=settings.birdnet_workers,
        n_producers=settings.birdnet_producers,
        prefetch_ratio=settings.birdnet_prefetch_ratio,
    )
    df = result.to_dataframe()
    cols = {c.lower(): c for c in df.columns}
    out = pd.DataFrame({
        "input": df[cols["input"]].astype(str).map(lambda p: Path(p).name),
        "start": df[cols["start_time"]].map(BirdNetService._time_value_to_seconds),
        "end": df[cols["end_time"]].map(BirdNetService._time_value_to_seconds),
        "label": df[cols["species_name"]].astype(str),
        "confidence": df[cols["confidence"]].astype(float),
    })
    return out[out["confidence"] >= RUN_THRESHOLD]


def stage_birdnet(out: Path, work: Path, gate: int) -> dict[str, pd.DataFrame]:
    predictions = {}

    for variant in VARIANTS:
        csv = out / f"predictions_{variant}.csv"
        if not csv.exists():
            paths = sorted((work / variant).glob("*.wav"))
            log(f"gate x{gate}: BirdNET on {len(paths)} '{variant}' clips ...")
            started = time.time()
            df = run_birdnet(paths)
            df["clip_id"] = df["input"].str.replace(".wav", "", regex=False)
            df.drop(columns="input").to_csv(csv, index=False)
            log(f"  done in {time.time() - started:.0f} s, {len(df)} predictions")
            shutil.rmtree(work / variant, ignore_errors=True)
        predictions[variant] = pd.read_csv(csv, dtype={"clip_id": str})

    return predictions


def stage_raw(files: list[Path]) -> pd.DataFrame:
    csv = OUT / "predictions_raw.csv"
    if not csv.exists():
        log(f"BirdNET on {len(files)} raw recordings ...")
        started = time.time()
        df = run_birdnet(files)
        df.rename(columns={"input": "filename"}).to_csv(csv, index=False)
        log(f"  done in {time.time() - started:.0f} s, {len(df)} predictions")
    return pd.read_csv(csv)


def to_absolute(variant: str, preds: pd.DataFrame, rois: pd.DataFrame) -> pd.DataFrame:
    """Prediction intervals in recording time, clipped to real audio."""
    if variant == "raw":
        out = preds.copy()
        out["start_s"], out["end_s"] = out["start"], out["end"]
        out["group"] = out["filename"] + "|" + out["start"].astype(str)
        return out

    df = preds.merge(rois, on="clip_id")
    if variant == "context":
        origin = df["context_origin_s"].where(df["roi_duration_s"] < BIRDNET_S, df["roi_start_s"])
        real_end = df["context_end_s"].where(df["roi_duration_s"] < BIRDNET_S, df["roi_end_s"])
    else:
        origin, real_end = df["roi_start_s"], df["roi_end_s"]
    df["start_s"] = origin + df["start"]
    df["end_s"] = np.minimum(origin + df["end"], real_end)
    df = df[df["end_s"] > df["start_s"]].copy()
    df["group"] = df["clip_id"] + "|" + df["start"].astype(str)
    return df


# ============================================================
# Stage 3: analysis
# ============================================================


def location_species(files: list[Path]) -> dict[str, set[str]]:
    """Allowed labels per recording: geo model at the site, in its week."""
    from src.services.species_filter import (
        NON_LOCATION_CLASSES, FilterLocation, SpeciesFilterService)

    service = SpeciesFilterService()
    labels = BirdNetService.species_labels()
    allowed = {}
    for path in files:
        day = datetime.strptime(path.stem.split("_")[3], "%Y%m%d").replace(
            hour=10, tzinfo=timezone.utc)
        # Site local time (UTC-5) is the same date at 10:00Z.
        f = service.species_filter(FilterLocation(points=(SITE,), label="site"),
                                   day, labels)
        allowed[path.name] = set(f.species) | NON_LOCATION_CLASSES
    return allowed


def select(preds: pd.DataFrame, *, allowed, threshold, aggregation) -> pd.DataFrame:
    df = preds
    if allowed is not None:
        df = df[[label in allowed[f] for label, f in zip(df["label"], df["filename"])]]
    # Server keeps the top 10 per BirdNET interval (after the filter).
    df = df.sort_values("confidence", ascending=False).groupby("group").head(SERVER_TOP_K)

    if aggregation is None:
        return df[df["confidence"] >= threshold]

    block_s, low, n_required, high = aggregation
    df = df[df["confidence"] >= low].copy()
    df["block"] = (df["start_s"] // block_s).astype(int)
    keys = ["filename", "block", "label"]
    stats = df.groupby(keys)["confidence"].agg(["max", "count"]).reset_index()
    accepted = stats[(stats["max"] >= high) | (stats["count"] >= n_required)][keys]
    return df.merge(accepted, on=keys)


def event_metrics(gt: pd.DataFrame, preds: pd.DataFrame, iou_min: float) -> tuple[int, int, int]:
    """Greedy one-to-one matching (same file + species, overlap, IoU >= iou_min)."""
    tp = 0
    by_key = {key: p for key, p in preds.groupby(["filename", "scientific_name"])}
    for key, g in gt.groupby(["filename", "scientific_name"]):
        p = by_key.get(key)
        if p is None:
            continue
        gs, ge = g["start_time_seconds"].to_numpy()[:, None], g["end_time_seconds"].to_numpy()[:, None]
        ps, pe = p["start_s"].to_numpy()[None, :], p["end_s"].to_numpy()[None, :]
        inter = np.clip(np.minimum(ge, pe) - np.maximum(gs, ps), 0, None)
        union = (ge - gs) + (pe - ps) - inter
        iou = np.where(union > 0, inter / union, 0)
        ok = (inter > 0) & (iou >= iou_min)
        gi, pi = np.nonzero(ok)
        order = np.lexsort((-p["confidence"].to_numpy()[pi], -iou[gi, pi]))
        used_g = np.zeros(len(g), dtype=bool)
        used_p = np.zeros(len(p), dtype=bool)
        for a, b in zip(gi[order].tolist(), pi[order].tolist()):
            if used_g[a] or used_p[b]:
                continue
            used_g[a] = used_p[b] = True
            tp += 1
    return tp, len(preds) - tp, len(gt) - tp


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def presence_metrics(gt: pd.DataFrame, preds: pd.DataFrame, block_s: float | None):
    """Species present per recording (block_s None) or per time block."""
    def pairs_gt():
        out = set()
        for f, s, a, b in gt[["filename", "scientific_name", "start_time_seconds", "end_time_seconds"]].itertuples(index=False):
            if block_s is None:
                out.add((f, s))
            else:
                for k in range(int(a // block_s), int((b - 1e-9) // block_s) + 1):
                    out.add((f, s, k))
        return out

    def pairs_pred():
        out = set()
        for f, s, a, b in preds[["filename", "scientific_name", "start_s", "end_s"]].itertuples(index=False):
            if block_s is None:
                out.add((f, s))
            else:
                for k in range(int(a // block_s), int((b - 1e-9) // block_s) + 1):
                    out.add((f, s, k))
        return out

    g, p = pairs_gt(), pairs_pred()
    return len(g & p), len(p - g), len(g - p)


def stage_analysis(files: list[Path], runs: dict, raw: pd.DataFrame) -> None:
    gt = pd.read_csv(EVAL / "results" / "ground_truth.csv")
    gt = gt[gt["scientific_name"].notna() & (gt["scientific_name"] != "unknown")]
    gt = gt[gt["filename"].isin([f.name for f in files])]

    allowed = location_species(files)
    log(f"location filter: {min(len(a) for a in allowed.values())}-"
        f"{max(len(a) for a in allowed.values())} labels per recording")

    absolute = {}
    for key, variant, preds, rois in [(("raw", "-"), "raw", raw, None)] + [
        ((variant, gate), variant, preds, rois)
        for gate, (rois, predictions) in runs.items()
        for variant, preds in predictions.items()
    ]:
        df = to_absolute(variant, preds, rois)
        df["scientific_name"] = df["label"].str.split("_").str[0]
        absolute[key] = df

    configs = [("threshold 0.25", 0.25, None), ("threshold 0.15", 0.15, None),
               ("threshold 0.10", 0.10, None)]
    for block in (60, 300):
        for low, n in ((0.10, 2), (0.10, 3), (0.15, 2)):
            configs.append((f"agg {block}s: max>=0.25 or {n}x>={low:.2f}", None,
                            (block, low, n, 0.25)))

    rows = []
    for (variant, gate), preds in absolute.items():
        for use_filter in (False, True):
            for name, threshold, aggregation in configs:
                sel = select(preds, allowed=allowed if use_filter else None,
                             threshold=threshold, aggregation=aggregation)
                row = {"gate": gate, "variant": variant, "location_filter": use_filter,
                       "selection": name, "predictions": len(sel)}
                for label, (tp, fp, fn) in {
                    "event_overlap": event_metrics(gt, sel, 0.0),
                    "event_iou0.1": event_metrics(gt, sel, 0.1),
                    "species_recording": presence_metrics(gt, sel, None),
                    "species_5min": presence_metrics(gt, sel, 300),
                }.items():
                    p, r, f1 = prf(tp, fp, fn)
                    row.update({f"{label}_precision": p, f"{label}_recall": r, f"{label}_f1": f1})
                rows.append(row)
        log(f"analysed {variant} (gate {gate})")

    table = pd.DataFrame(rows)
    table.to_csv(OUT / "metrics.csv", index=False)

    summary = pd.DataFrame([{
        "gate": gate,
        "recordings": len(files),
        "ground_truth_events": len(gt),
        "rois": len(rois),
        "rois_under_3s_percent": 100 * (rois["roi_duration_s"] < BIRDNET_S).mean(),
        "roi_audio_minutes_per_hour": rois["roi_duration_s"].sum() / 60 / len(files),
        "context_extra_upload_percent": 100 * (
            (rois["context_end_s"] - rois["context_origin_s"]).sum()
            / max(rois["roi_duration_s"].sum(), 1e-9) - 1),
    } for gate, (rois, _) in runs.items()])
    summary.to_csv(OUT / "summary.csv", index=False)
    print(summary.to_string(index=False))

    view = table[table["selection"].isin(["threshold 0.25", "threshold 0.15",
                                          "agg 300s: max>=0.25 or 2x>=0.10"])]
    cols = ["gate", "variant", "location_filter", "selection", "predictions",
            "event_overlap_precision", "event_overlap_recall", "event_overlap_f1",
            "species_5min_precision", "species_5min_recall", "species_5min_f1",
            "species_recording_precision", "species_recording_recall", "species_recording_f1"]
    with pd.option_context("display.width", 250, "display.max_columns", 20,
                           "display.float_format", "{:.3f}".format):
        print(view[cols].to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", type=int, default=None, help="only the first N recordings")
    args = parser.parse_args()

    global OUT, WORK
    files = sorted(DATA.glob("*.flac"))
    if args.files:
        files = files[: args.files]
        OUT = OUT.parent / f"padding_aggregation_n{args.files}"
        WORK = OUT / "_clips"
    OUT.mkdir(parents=True, exist_ok=True)

    log(f"{len(files)} recordings -> {OUT}")
    runs = {}
    for gate in GATES:
        out, work = OUT / f"gate_x{gate}", WORK / f"gate_x{gate}"
        rois = stage_rois(files, gate, out, work)
        log(f"gate x{gate}: {len(rois)} ROIs "
            f"({(rois['roi_duration_s'] < BIRDNET_S).mean():.0%} shorter than 3 s)")
        runs[gate] = (rois, stage_birdnet(out, work, gate))
    raw = stage_raw(files)
    shutil.rmtree(WORK, ignore_errors=True)
    stage_analysis(files, runs, raw)


if __name__ == "__main__":
    main()
