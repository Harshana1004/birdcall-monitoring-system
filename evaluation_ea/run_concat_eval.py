"""
Concatenating device ROI snippets into longer audio before BirdNET,
compared with BirdNET on each snippet (run_padding_aggregation_eval.py,
"silence" variant).

Within a recording, consecutive ROIs (device pipeline, same gate) are
joined into one file while the gap between one ROI's end and the next
ROI's start is <= GAP seconds; the device's ROI audio is joined end to
end with 10 ms crossfades (the time between ROIs was never uploaded).

BirdNET splits each joined file into 3 s windows. A window's prediction
is mapped back to recording time as one interval from the earliest to
the latest real moment of the ROI audio inside that window; then the
same location filter, top-10, thresholds and metrics as
run_padding_aggregation_eval.py are applied.

    backend/.venv/Scripts/python evaluation_ea/run_concat_eval.py
"""

import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import resample_poly

sys.argv = sys.argv[:1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_padding_aggregation_eval as E  # noqa: E402

OUT = E.OUT / "concat"
WORK = OUT / "_clips"
GATES = [2, 8]
GAPS = [10, 60]
FADE = int(0.010 * E.SR)


def roi_audio(files, gate):
    """ROI samples per file, as the device uploads them, with their times."""
    E.edge_reference.MIN_PEAK_FACTOR = gate
    window_len = E.WINDOW_S * E.SR
    out = {}
    for path in files:
        audio, sr = sf.read(path, dtype="float32")
        audio = resample_poly(audio, 1, sr // E.SR).astype(np.float32)
        items = []
        for w in range(len(audio) // window_len):
            result = E.edge_reference.edge_pipeline(audio[w * window_len: (w + 1) * window_len], E.SR)
            for _, start, end, samples in result.rois:
                items.append((w * E.WINDOW_S + start, w * E.WINDOW_S + end, samples))
        out[path.name] = items
    return out


def build(files, gate, gap, rois_by_file):
    """Writes joined WAVs; returns segment map rows (clip, clip_start, clip_end, real_start)."""
    work = WORK / f"x{gate}_g{gap}"
    work.mkdir(parents=True, exist_ok=True)
    seg_rows = []
    for file_index, path in enumerate(files, 1):
        items = rois_by_file[path.name]
        groups, current = [], []
        for item in items:
            if current and item[0] - current[-1][1] > gap:
                groups.append(current)
                current = []
            current.append(item)
        if current:
            groups.append(current)

        for g, group in enumerate(groups):
            clip_id = f"{file_index:02d}_{g:04d}"
            audio = np.zeros(0, np.float32)
            for start, end, samples in group:
                offset = max(0, len(audio) - FADE) if len(audio) else 0
                audio = E.crossfade_concat(audio, samples, FADE) if len(audio) else samples
                seg_rows.append({"clip_id": clip_id, "filename": path.name,
                                 "clip_start": offset / E.SR,
                                 "clip_end": offset / E.SR + (end - start),
                                 "real_start": start})
            sf.write(work / f"{clip_id}.wav", np.clip(audio, -1, 1), E.SR, subtype="PCM_16")
    segments = pd.DataFrame(seg_rows)
    return work, segments, len({r["clip_id"] for r in seg_rows})


def to_absolute(preds, segments):
    """One interval per BirdNET window: earliest..latest real time of ROI audio inside it."""
    rows = []
    by_clip = {c: g for c, g in segments.groupby("clip_id")}
    for p in preds.itertuples(index=False):
        seg = by_clip[p.clip_id]
        a = np.maximum(seg.clip_start.values, p.start)
        b = np.minimum(seg.clip_end.values, p.end)
        inside = b > a
        if not inside.any():
            continue
        real_a = seg.real_start.values[inside] + (a[inside] - seg.clip_start.values[inside])
        real_b = seg.real_start.values[inside] + (b[inside] - seg.clip_start.values[inside])
        rows.append({"filename": seg.filename.iloc[0], "label": p.label, "confidence": p.confidence,
                     "start_s": real_a.min(), "end_s": real_b.max(),
                     "group": f"{p.clip_id}|{p.start}"})
    df = pd.DataFrame(rows)
    df["scientific_name"] = df["label"].str.split("_").str[0]
    return df


def main():
    files = sorted(E.DATA.glob("*.flac"))
    OUT.mkdir(parents=True, exist_ok=True)

    absolute, info = {}, []
    for gate in GATES:
        rois_by_file = None
        for gap in GAPS:
            csv = OUT / f"predictions_x{gate}_g{gap}.csv"
            seg_csv = OUT / f"segments_x{gate}_g{gap}.csv"
            if not (csv.exists() and seg_csv.exists()):
                if rois_by_file is None:
                    E.log(f"gate x{gate}: regenerating ROI audio")
                    rois_by_file = roi_audio(files, gate)
                work, segments, n_clips = build(files, gate, gap, rois_by_file)
                segments.to_csv(seg_csv, index=False)
                E.log(f"gate x{gate}, gap {gap} s: {len(segments)} ROIs joined into {n_clips} files; BirdNET ...")
                df = E.run_birdnet(sorted(work.glob("*.wav")))
                df["clip_id"] = df["input"].str.replace(".wav", "", regex=False)
                df.drop(columns="input").to_csv(csv, index=False)
                shutil.rmtree(work, ignore_errors=True)
                E.log(f"  {len(df)} predictions")
            segments = pd.read_csv(seg_csv, dtype={"clip_id": str})
            preds = pd.read_csv(csv, dtype={"clip_id": str})
            absolute[(gate, f"concat {gap}s")] = to_absolute(preds, segments)
            durations = segments.groupby("clip_id").clip_end.max()
            info.append({"gate": gate, "join": f"concat {gap}s", "rois": len(segments),
                         "files": segments.clip_id.nunique(),
                         "median_file_s": durations.median(),
                         "files_under_3s_percent": 100 * (durations < 3).mean()})

    shutil.rmtree(WORK, ignore_errors=True)
    print(pd.DataFrame(info).to_string(index=False, float_format="{:.1f}".format))

    gt = pd.read_csv(E.EVAL / "results" / "ground_truth.csv")
    gt = gt[gt["scientific_name"].notna() & (gt["scientific_name"] != "unknown")]
    allowed = E.location_species(files)

    rows = []
    for (gate, join), preds in absolute.items():
        for name, threshold in (("threshold 0.25", 0.25), ("threshold 0.15", 0.15)):
            sel = E.select(preds, allowed=allowed, threshold=threshold, aggregation=None)
            row = {"gate": gate, "join": join, "selection": name, "predictions": len(sel)}
            for label, (tp, fp, fn) in {
                "event_overlap": E.event_metrics(gt, sel, 0.0),
                "species_5min": E.presence_metrics(gt, sel, 300),
                "species_recording": E.presence_metrics(gt, sel, None),
            }.items():
                p, r, f1 = E.prf(tp, fp, fn)
                row.update({f"{label}_precision": p, f"{label}_recall": r, f"{label}_f1": f1})
            rows.append(row)

    # Per-snippet baseline from the main evaluation.
    base = pd.read_csv(E.OUT / "metrics.csv")
    base = base[base.location_filter & (base.variant == "silence")
                & base.selection.isin(["threshold 0.25", "threshold 0.15"])
                & base.gate.astype(str).isin([str(g) for g in GATES])].copy()
    base["join"] = "per snippet"
    base["gate"] = base["gate"].astype(int)
    table = pd.concat([base[list(rows[0].keys())], pd.DataFrame(rows)], ignore_index=True)
    table = table.sort_values(["gate", "selection", "join"])
    table.to_csv(OUT / "concat_metrics.csv", index=False)
    with pd.option_context("display.width", 250, "display.float_format", "{:.3f}".format):
        print(table.to_string(index=False))


if __name__ == "__main__":
    main()
