"""
What the device should upload: same ROIs (device detection on the
1 kHz-filtered signal, gates x8/x4/x2), different upload audio:

  hpf1000     today: causal 4th-order 1 kHz high-pass (results from
              run_padding_aggregation_eval.py, "silence" variant)
  unfiltered  only the device's 20 Hz DC blocker
  hpf150      gentle causal 4th-order 150 Hz high-pass

All filters run over the 10 s window (as on the device), then the
window is peak-normalised and the exact ROI cut out; silence padding
(as uploaded today). Same location filter, top-10, thresholds and
metrics as the main evaluation. Also reports, for the x2 gate, how many
of the raw-detected events that lie inside an ROI BirdNET now finds.

    backend/.venv/Scripts/python evaluation_ea/run_upload_filter_eval.py
"""

import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf
from scipy.signal import butter, resample_poly, sosfilt

sys.argv = sys.argv[:1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_padding_aggregation_eval as E  # noqa: E402

OUT = E.OUT / "upload_filter"
WORK = OUT / "_clips"
GATES = [8, 4, 2]
UPLOADS = {
    "unfiltered": butter(1, 20.0 / (E.SR / 2), btype="highpass", output="sos"),
    "hpf150": butter(4, 150.0 / (E.SR / 2), btype="highpass", output="sos"),
}


def build_clips(files, gate, work):
    E.edge_reference.MIN_PEAK_FACTOR = gate
    window_len = E.WINDOW_S * E.SR
    rows = []
    for name in UPLOADS:
        (work / name).mkdir(parents=True, exist_ok=True)
    for file_index, path in enumerate(files, 1):
        audio, sr = sf.read(path, dtype="float32")
        audio = resample_poly(audio, 1, sr // E.SR).astype(np.float32)
        for w in range(len(audio) // window_len):
            raw = audio[w * window_len: (w + 1) * window_len]
            result = E.edge_reference.edge_pipeline(raw, E.SR)
            if not result.rois:
                continue
            windows = {}
            for name, sos in UPLOADS.items():
                x = sosfilt(sos, raw).astype(np.float32)
                windows[name] = x / max(float(np.max(np.abs(x))), 1e-12)
            for index, start_s, end_s, samples in result.rois:
                clip_id = f"{file_index:02d}_{w:04d}_{index:02d}"
                a = max(0, int(round(start_s * E.SR)))
                b = a + len(samples)
                for name, x in windows.items():
                    sf.write(work / name / f"{clip_id}.wav", np.clip(x[a:b], -1, 1), E.SR, subtype="PCM_16")
                rows.append({"clip_id": clip_id, "filename": path.name,
                             "roi_start_s": w * E.WINDOW_S + start_s,
                             "roi_end_s": w * E.WINDOW_S + end_s,
                             "roi_duration_s": end_s - start_s})
        E.log(f"gate x{gate} [{file_index}/{len(files)}] clips written")
    return pd.DataFrame(rows)


def main():
    files = sorted(E.DATA.glob("*.flac"))
    OUT.mkdir(parents=True, exist_ok=True)

    gt = pd.read_csv(E.EVAL / "results" / "ground_truth.csv")
    gt = gt[gt["scientific_name"].notna() & (gt["scientific_name"] != "unknown")].reset_index(drop=True)
    allowed = E.location_species(files)

    absolute = {}
    for gate in GATES:
        out = OUT / f"gate_x{gate}"
        out.mkdir(exist_ok=True)
        rois_csv = out / "rois.csv"
        if not all((out / f"predictions_{u}.csv").exists() for u in UPLOADS):
            work = WORK / f"x{gate}"
            rois = build_clips(files, gate, work)
            rois.to_csv(rois_csv, index=False)
            for name in UPLOADS:
                csv = out / f"predictions_{name}.csv"
                if csv.exists():
                    continue
                E.log(f"gate x{gate}: BirdNET on {len(rois)} '{name}' clips ...")
                df = E.run_birdnet(sorted((work / name).glob("*.wav")))
                df["clip_id"] = df["input"].str.replace(".wav", "", regex=False)
                df.drop(columns="input").to_csv(csv, index=False)
                E.log(f"  {len(df)} predictions")
            shutil.rmtree(work, ignore_errors=True)
        rois = pd.read_csv(rois_csv, dtype={"clip_id": str})
        for name in UPLOADS:
            preds = pd.read_csv(out / f"predictions_{name}.csv", dtype={"clip_id": str})
            df = E.to_absolute("silence", preds, rois)
            df["scientific_name"] = df["label"].str.split("_").str[0]
            absolute[(gate, name)] = (df, rois)
        # Today's 1 kHz upload, from the main evaluation (same ROIs).
        base_rois = pd.read_csv(E.OUT / f"gate_x{gate}" / "rois.csv", dtype={"clip_id": str})
        base = pd.read_csv(E.OUT / f"gate_x{gate}" / "predictions_silence.csv", dtype={"clip_id": str})
        df = E.to_absolute("silence", base, base_rois)
        df["scientific_name"] = df["label"].str.split("_").str[0]
        absolute[(gate, "hpf1000")] = (df, base_rois)
        assert len(base_rois) == len(rois), "ROIs differ from the main evaluation"
    shutil.rmtree(WORK, ignore_errors=True)

    rows = []
    for (gate, upload), (preds, _) in absolute.items():
        for use_filter in (False, True):
            for name, threshold in (("threshold 0.25", 0.25), ("threshold 0.15", 0.15)):
                sel = E.select(preds, allowed=allowed if use_filter else None,
                               threshold=threshold, aggregation=None)
                row = {"gate": gate, "upload": upload, "location_filter": use_filter,
                       "selection": name, "predictions": len(sel)}
                for label, (tp, fp, fn) in {
                    "event_overlap": E.event_metrics(gt, sel, 0.0),
                    "species_5min": E.presence_metrics(gt, sel, 300),
                    "species_recording": E.presence_metrics(gt, sel, None),
                }.items():
                    p, r, f1 = E.prf(tp, fp, fn)
                    row.update({f"{label}_precision": p, f"{label}_recall": r, f"{label}_f1": f1})
                rows.append(row)
    table = pd.DataFrame(rows)
    table["order"] = table["upload"].map({"hpf1000": 0, "hpf150": 1, "unfiltered": 2})
    table = table.sort_values(["location_filter", "selection", "gate", "order"]).drop(columns="order")
    table.to_csv(OUT / "upload_filter_metrics.csv", index=False)

    view = table[table.location_filter]
    cols = ["gate", "upload", "selection", "predictions", "event_overlap_precision", "event_overlap_recall",
            "species_5min_precision", "species_5min_recall", "species_5min_f1",
            "species_recording_precision", "species_recording_recall", "species_recording_f1"]
    with pd.option_context("display.width", 250, "display.float_format", "{:.3f}".format):
        print(view[cols].to_string(index=False))

    # Inside-ROI detection rate (x2): raw-detected events overlapped by an ROI.
    def hits(preds):
        by = {k: g for k, g in preds.groupby(["filename", "scientific_name"])}
        out = np.zeros(len(gt), bool)
        for i, (f, s, a, b) in enumerate(gt[["filename", "scientific_name", "start_time_seconds", "end_time_seconds"]].itertuples(index=False)):
            p = by.get((f, s))
            if p is not None:
                out[i] = ((p.start_s.values < b) & (p.end_s.values > a)).any()
        return out

    raw = E.to_absolute("raw", pd.read_csv(E.OUT / "predictions_raw.csv"), None)
    raw["scientific_name"] = raw["label"].str.split("_").str[0]
    raw_hit = hits(E.select(raw, allowed=allowed, threshold=0.25, aggregation=None))
    for gate in GATES:
        rois = absolute[(gate, "hpf1000")][1]
        by_file = {f: g for f, g in rois.groupby("filename")}
        inside = np.zeros(len(gt), bool)
        for i, (f, a, b) in enumerate(gt[["filename", "start_time_seconds", "end_time_seconds"]].itertuples(index=False)):
            r = by_file.get(f)
            if r is not None:
                inside[i] = ((r.roi_start_s.values < b) & (r.roi_end_s.values > a)).any()
        target = raw_hit & inside
        parts = []
        for upload in ("hpf1000", "hpf150", "unfiltered"):
            h = hits(E.select(absolute[(gate, upload)][0], allowed=allowed, threshold=0.25, aggregation=None))
            parts.append(f"{upload} {h[target].mean():.1%}")
        print(f"gate x{gate}: of {target.sum()} raw-detected events inside an ROI, BirdNET on the snippet finds: "
              + ", ".join(parts))


if __name__ == "__main__":
    main()
