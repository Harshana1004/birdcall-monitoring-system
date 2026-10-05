"""
Device sample rate: 16 kHz (current) vs 24 kHz vs 32 kHz, with the
current firmware DSP (esp32-dsp-1.3.0: detection on the 1 kHz-filtered
copy, x4 peak gate, 0.5 s minimum region, unfiltered upload with the
20 Hz DC blocker, peak normalisation, silence padding).

The Western Amazon recordings are 32 kHz, so 32 kHz is native and 16/24
kHz are resampled. Also reports the upload volume per hour of audio for
each rate (PCM16 WAV payload; protocol overhead is added in RESULTS.md).
Location filter on.

    backend/.venv/Scripts/python evaluation_ea/run_sample_rate_eval.py
"""

import shutil
import sys
from math import gcd
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfilt

sys.argv = sys.argv[:1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_padding_aggregation_eval as E  # noqa: E402

OUT = E.OUT / "sample_rate"
WORK = OUT / "_clips"
RATES = [16000, 24000, 32000]


def build(files, rate, work):
    work.mkdir(parents=True, exist_ok=True)
    window_len = E.WINDOW_S * rate
    dc_block = butter(1, 20.0 / (rate / 2), btype="highpass", output="sos")
    rows = []
    for file_index, path in enumerate(files, 1):
        audio, sr = sf.read(path, dtype="float32")
        if sr != rate:
            g = gcd(sr, rate)
            audio = resample_poly(audio, rate // g, sr // g).astype(np.float32)
        for w in range(len(audio) // window_len):
            raw = audio[w * window_len: (w + 1) * window_len]
            result = E.edge_reference.edge_pipeline(raw, rate)
            if not result.rois:
                continue
            upload = sosfilt(dc_block, raw).astype(np.float32)
            upload /= max(float(np.max(np.abs(upload))), 1e-12)
            for index, start_s, end_s, samples in result.rois:
                clip_id = f"{file_index:02d}_{w:04d}_{index:02d}"
                a = max(0, int(round(start_s * rate)))
                sf.write(work / f"{clip_id}.wav", np.clip(upload[a: a + len(samples)], -1, 1),
                         rate, subtype="PCM_16")
                rows.append({"clip_id": clip_id, "filename": path.name,
                             "roi_start_s": w * E.WINDOW_S + start_s,
                             "roi_end_s": w * E.WINDOW_S + end_s,
                             "roi_duration_s": end_s - start_s,
                             "samples": len(samples)})
        E.log(f"{rate} Hz [{file_index}/{len(files)}] {path.name}")
    return pd.DataFrame(rows)


def main():
    files = sorted(E.DATA.glob("*.flac"))
    OUT.mkdir(parents=True, exist_ok=True)
    gt = pd.read_csv(E.EVAL / "results" / "ground_truth.csv")
    gt = gt[gt["scientific_name"].notna() & (gt["scientific_name"] != "unknown")]
    allowed = E.location_species(files)

    rows = []
    for rate in RATES:
        out = OUT / f"sr_{rate}"
        out.mkdir(exist_ok=True)
        csv = out / "predictions.csv"
        if not csv.exists():
            work = WORK / str(rate)
            rois = build(files, rate, work)
            rois.to_csv(out / "rois.csv", index=False)
            E.log(f"{rate} Hz: BirdNET on {len(rois)} clips ...")
            df = E.run_birdnet(sorted(work.glob("*.wav")))
            df["clip_id"] = df["input"].str.replace(".wav", "", regex=False)
            df.drop(columns="input").to_csv(csv, index=False)
            shutil.rmtree(work, ignore_errors=True)
        rois = pd.read_csv(out / "rois.csv", dtype={"clip_id": str})
        preds = E.to_absolute("silence", pd.read_csv(csv, dtype={"clip_id": str}), rois)
        preds["scientific_name"] = preds["label"].str.split("_").str[0]

        hours = len(files)
        payload = (rois["samples"] * 2 + 44).sum()
        for name, threshold in (("threshold 0.25", 0.25), ("threshold 0.15", 0.15)):
            sel = E.select(preds, allowed=allowed, threshold=threshold, aggregation=None)
            row = {"sample_rate": rate, "selection": name, "rois_per_hour": len(rois) / hours,
                   "roi_audio_min_per_hour": rois.roi_duration_s.sum() / 60 / hours,
                   "wav_mb_per_hour": payload / 1e6 / hours, "predictions": len(sel)}
            for label, (tp, fp, fn) in {
                "event_overlap": E.event_metrics(gt, sel, 0.0),
                "species_5min": E.presence_metrics(gt, sel, 300),
                "species_recording": E.presence_metrics(gt, sel, None),
            }.items():
                p, r, f1 = E.prf(tp, fp, fn)
                row.update({f"{label}_precision": p, f"{label}_recall": r, f"{label}_f1": f1})
            rows.append(row)
    shutil.rmtree(WORK, ignore_errors=True)

    table = pd.DataFrame(rows).sort_values(["selection", "sample_rate"])
    table.to_csv(OUT / "sample_rate_metrics.csv", index=False)
    cols = ["sample_rate", "selection", "rois_per_hour", "roi_audio_min_per_hour", "wav_mb_per_hour",
            "event_overlap_recall", "species_5min_precision", "species_5min_recall", "species_5min_f1",
            "species_recording_precision", "species_recording_recall", "species_recording_f1"]
    with pd.option_context("display.width", 250, "display.float_format", "{:.3f}".format):
        print(table[cols].to_string(index=False))


if __name__ == "__main__":
    main()
