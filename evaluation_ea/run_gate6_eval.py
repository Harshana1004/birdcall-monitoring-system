"""
x6 peak gate with the deployed upload (esp32-dsp-1.2.0: detection on the
1 kHz-filtered copy, unfiltered upload), compared with the x8/x4/x2
"unfiltered" results of run_upload_filter_eval.py. Location filter on.

    backend/.venv/Scripts/python evaluation_ea/run_gate6_eval.py
"""

import shutil
import sys
from pathlib import Path

import pandas as pd

sys.argv = sys.argv[:1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_padding_aggregation_eval as E  # noqa: E402
import run_upload_filter_eval as U  # noqa: E402

GATE = 6


def main():
    files = sorted(E.DATA.glob("*.flac"))
    out = U.OUT / f"gate_x{GATE}"
    out.mkdir(parents=True, exist_ok=True)
    csv = out / "predictions_unfiltered.csv"
    if not csv.exists():
        work = U.WORK / f"x{GATE}"
        rois = U.build_clips(files, GATE, work)
        rois.to_csv(out / "rois.csv", index=False)
        E.log(f"gate x{GATE}: BirdNET on {len(rois)} unfiltered clips ...")
        df = E.run_birdnet(sorted((work / "unfiltered").glob("*.wav")))
        df["clip_id"] = df["input"].str.replace(".wav", "", regex=False)
        df.drop(columns="input").to_csv(csv, index=False)
        shutil.rmtree(U.WORK, ignore_errors=True)

    rois = pd.read_csv(out / "rois.csv", dtype={"clip_id": str})
    preds = E.to_absolute("silence", pd.read_csv(csv, dtype={"clip_id": str}), rois)
    preds["scientific_name"] = preds["label"].str.split("_").str[0]

    gt = pd.read_csv(E.EVAL / "results" / "ground_truth.csv")
    gt = gt[gt["scientific_name"].notna() & (gt["scientific_name"] != "unknown")]
    allowed = E.location_species(files)

    rows = []
    for name, threshold in (("threshold 0.25", 0.25), ("threshold 0.15", 0.15)):
        sel = E.select(preds, allowed=allowed, threshold=threshold, aggregation=None)
        row = {"gate": GATE, "upload": "unfiltered", "location_filter": True,
               "selection": name, "predictions": len(sel)}
        for label, (tp, fp, fn) in {
            "event_overlap": E.event_metrics(gt, sel, 0.0),
            "species_5min": E.presence_metrics(gt, sel, 300),
            "species_recording": E.presence_metrics(gt, sel, None),
        }.items():
            p, r, f1 = E.prf(tp, fp, fn)
            row.update({f"{label}_precision": p, f"{label}_recall": r, f"{label}_f1": f1})
        rows.append(row)

    others = pd.read_csv(U.OUT / "upload_filter_metrics.csv")
    others = others[others.location_filter & (others.upload == "unfiltered")]
    table = pd.concat([others, pd.DataFrame(rows)], ignore_index=True)
    table = table.sort_values(["selection", "gate"])
    table.to_csv(out / "gate_comparison.csv", index=False)

    minutes = {g: pd.read_csv(U.OUT / f"gate_x{g}" / "rois.csv").roi_duration_s.sum() / 60 / len(files)
               for g in (8, 6, 4, 2)}
    print("ROI audio per hour:", ", ".join(f"x{g} {m:.1f} min" for g, m in minutes.items()))
    cols = ["gate", "selection", "predictions", "species_5min_precision", "species_5min_recall",
            "species_5min_f1", "species_recording_precision", "species_recording_recall", "species_recording_f1"]
    with pd.option_context("display.width", 200, "display.float_format", "{:.3f}".format):
        print(table[cols].to_string(index=False))


if __name__ == "__main__":
    main()
