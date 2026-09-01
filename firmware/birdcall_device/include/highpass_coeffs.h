#pragma once

// Precomputed second-order-section (SOS) coefficients for a
// 4th-order Butterworth high-pass filter, cutoff = 1000 Hz,
// sample rate = 16000 Hz.

constexpr int HIGHPASS_SECTION_COUNT = 2;

constexpr float HIGHPASS_SOS[HIGHPASS_SECTION_COUNT][6] = {
    {0.5963023654f, -1.1926047307f, 0.5963023654f, 1.0000000000f,
     -1.3651172372f, 0.4775922501f},
    {1.0000000000f, -2.0000000000f, 1.0000000000f, 1.0000000000f,
     -1.6117270965f, 0.7445208382f},
};