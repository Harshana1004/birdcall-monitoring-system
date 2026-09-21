import pandas as pd

# Path to the annotations file
ANNOTATIONS_FILE = "evaluation_ea/annotations.csv"

# Load annotations
df = pd.read_csv(ANNOTATIONS_FILE)

# Convert frequency columns to numeric
df["Low Freq (Hz)"] = pd.to_numeric(df["Low Freq (Hz)"], errors="coerce")
df["High Freq (Hz)"] = pd.to_numeric(df["High Freq (Hz)"], errors="coerce")

# Remove rows where either frequency is missing
freq_df = df.dropna(subset=["Low Freq (Hz)", "High Freq (Hz)"]).copy()

total = len(freq_df)

# Frequency-range categories
low_below_1k = freq_df["Low Freq (Hz)"] < 1000
high_below_1k = freq_df["High Freq (Hz)"] < 1000

entirely_below_1k = high_below_1k
crosses_1k = (
    (freq_df["Low Freq (Hz)"] < 1000)
    & (freq_df["High Freq (Hz)"] >= 1000)
)
entirely_above_1k = freq_df["Low Freq (Hz)"] >= 1000

print("=" * 60)
print("ANNOTATION FREQUENCY ANALYSIS")
print("=" * 60)

print(f"\nTotal annotations with valid frequency values: {total}")

print("\nFrequency range relative to 1 kHz high-pass cutoff:")
print("-" * 60)

categories = [
    ("Low Freq < 1000 Hz", low_below_1k),
    ("High Freq < 1000 Hz (entire range below cutoff)", entirely_below_1k),
    ("Range crosses 1000 Hz", crosses_1k),
    ("Low Freq >= 1000 Hz (entire range above cutoff)", entirely_above_1k),
]

for name, mask in categories:
    count = mask.sum()
    percentage = (count / total * 100) if total else 0
    print(f"{name:55s}: {count:6d} ({percentage:6.2f}%)")

# Show some examples of annotations entirely below 1 kHz
below = freq_df[entirely_below_1k]

print("\n" + "=" * 60)
print("EXAMPLES: ANNOTATIONS ENTIRELY BELOW 1 kHz")
print("=" * 60)

if len(below) > 0:
    print(
        below[
            [
                "Filename",
                "Start Time (s)",
                "End Time (s)",
                "Low Freq (Hz)",
                "High Freq (Hz)",
                "Species eBird Code",
            ]
        ].head(20).to_string(index=False)
    )
else:
    print("No annotations have High Freq below 1000 Hz.")

# Show some examples that cross the 1 kHz cutoff
crossing = freq_df[crosses_1k]

print("\n" + "=" * 60)
print("EXAMPLES: ANNOTATIONS CROSSING 1 kHz")
print("=" * 60)

if len(crossing) > 0:
    print(
        crossing[
            [
                "Filename",
                "Start Time (s)",
                "End Time (s)",
                "Low Freq (Hz)",
                "High Freq (Hz)",
                "Species eBird Code",
            ]
        ].head(20).to_string(index=False)
    )
else:
    print("No annotations cross the 1 kHz cutoff.")

print("\n" + "=" * 60)