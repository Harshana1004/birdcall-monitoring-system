"""
Which device processing step makes BirdNET miss calls that ARE inside
an ROI? Same 3 s clips (the "context" spans of the x2-gate ROIs),
cut from the original recordings and processed step by step:

  orig32     original 32 kHz audio (what raw BirdNET hears)
  16k        resampled to 16 kHz (device sample rate: nothing > 8 kHz)
  16k_hpf    + the device's causal 1 kHz high-pass over the 10 s window
  device     + peak normalisation = the "context" variant already run
             by run_padding_aggregation_eval.py (predictions reused)

    backend/.venv/Scripts/python evaluation_ea/run_snippet_degradation_eval.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfilt

sys.argv = sys.argv[:1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_padding_aggregation_eval as E  # noqa: E402

OUT = E.OUT / "degradation"
WORK = OUT / "_clips"
STEPS = ["orig32", "16k", "16k_hpf"]
SAMPLE = 3000


def main():
    files = sorted(E.DATA.glob("*.flac"))
    rois = pd.read_csv(E.OUT / "gate_x2" / "rois.csv", dtype={"clip_id": str})
    rois = rois.sample(n=min(SAMPLE, len(rois)), random_state=7).sort_values("clip_id")
    OUT.mkdir(parents=True, exist_ok=True)
    sos = butter(4, 1000.0 / (E.SR / 2), btype="highpass", output="sos")

    if not all((OUT / f"predictions_{s}.csv").exists() for s in STEPS):
        for s in STEPS:
            (WORK / s).mkdir(parents=True, exist_ok=True)
        for name, group in rois.groupby("filename"):
            audio32, sr = sf.read(E.DATA / name, dtype="float32")
            audio16 = resample_poly(audio32, 1, sr // E.SR).astype(np.float32)
            for r in group.itertuples(index=False):
                a, b = r.context_origin_s, r.context_end_s
                w0 = int(r.window_start_s * E.SR)
                window = sosfilt(sos, audio16[w0: w0 + E.WINDOW_S * E.SR]).astype(np.float32)
                clips = {
                    "orig32": (audio32[int(a * sr): int(b * sr)], sr),
                    "16k": (audio16[int(a * E.SR): int(b * E.SR)], E.SR),
                    "16k_hpf": (window[int((a - r.window_start_s) * E.SR): int((b - r.window_start_s) * E.SR)], E.SR),
                }
                for s, (x, rate) in clips.items():
                    sf.write(WORK / s / f"{r.clip_id}.wav", x, rate, subtype="FLOAT")
            E.log(f"clips for {name}")
        for s in STEPS:
            csv = OUT / f"predictions_{s}.csv"
            if not csv.exists():
                E.log(f"BirdNET on {s}")
                df = E.run_birdnet(sorted((WORK / s).glob("*.wav")))
                df["clip_id"] = df["input"].str.replace(".wav", "", regex=False)
                df.drop(columns="input").to_csv(csv, index=False)
        import shutil
        shutil.rmtree(WORK, ignore_errors=True)

    gt = pd.read_csv(E.EVAL / "results" / "ground_truth.csv")
    gt = gt[gt.scientific_name.notna() & (gt.scientific_name != "unknown")].reset_index(drop=True)
    allowed = E.location_species(files)

    def hits(preds):
        by = {k: g for k, g in preds.groupby(["filename", "scientific_name"])}
        out = np.zeros(len(gt), bool)
        for i, (f, s, a, b) in enumerate(gt[["filename", "scientific_name", "start_time_seconds", "end_time_seconds"]].itertuples(index=False)):
            p = by.get((f, s))
            if p is not None:
                out[i] = ((p.start_s.values < b) & (p.end_s.values > a)).any()
        return out

    def prepare(preds):
        df = preds[preds.clip_id.isin(rois.clip_id)].merge(rois, on="clip_id")
        df["start_s"] = df["context_origin_s"] + df["start"]
        df["end_s"] = np.minimum(df["context_origin_s"] + df["end"], df["context_end_s"])
        df["group"] = df["clip_id"] + "|" + df["start"].astype(str)
        df["scientific_name"] = df["label"].str.split("_").str[0]
        return E.select(df, allowed=allowed, threshold=0.25, aggregation=None)

    # Events inside the sampled clips (any overlap) that raw BirdNET detects.
    raw = pd.read_csv(E.OUT / "predictions_raw.csv")
    raw = E.to_absolute("raw", raw, None)
    raw["scientific_name"] = raw["label"].str.split("_").str[0]
    raw_hit = hits(E.select(raw, allowed=allowed, threshold=0.25, aggregation=None))
    inside = np.zeros(len(gt), bool)
    by_file = {f: g for f, g in rois.groupby("filename")}
    for i, (f, a, b) in enumerate(gt[["filename", "start_time_seconds", "end_time_seconds"]].itertuples(index=False)):
        r = by_file.get(f)
        if r is not None:
            inside[i] = ((r.context_origin_s.values < b) & (r.context_end_s.values > a)).any()
    target = inside & raw_hit
    print(f"{SAMPLE} sampled clips; {inside.sum()} annotated events inside them, "
          f"{target.sum()} of those detected by raw BirdNET on the full recording")

    rows = []
    for s in STEPS + ["device"]:
        csv = (E.OUT / "gate_x2" / "predictions_context.csv") if s == "device" else OUT / f"predictions_{s}.csv"
        h = hits(prepare(pd.read_csv(csv, dtype={"clip_id": str})))
        rows.append({"step": s, "clip_hits_of_raw_detected": h[target].mean(),
                     "clip_hits_of_all_inside": h[inside].mean()})
    table = pd.DataFrame(rows)
    table.to_csv(OUT / "degradation.csv", index=False)
    print(table.to_string(index=False, float_format="{:.1%}".format))


if __name__ == "__main__":
    main()
