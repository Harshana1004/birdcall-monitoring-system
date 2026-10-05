#pragma once

#include "config.h"

// Precomputed second-order-section (SOS) coefficients for a
// 4th-order Butterworth high-pass filter, cutoff = 1000 Hz, for each
// supported SAMPLE_RATE_HZ. Generated with
//   scipy.signal.butter(4, 1000 / (fs / 2), btype="highpass", output="sos")
// a0 (column 3) is always 1.

constexpr int HIGHPASS_SECTION_COUNT = 2;

constexpr float HIGHPASS_SOS_16K[HIGHPASS_SECTION_COUNT][6] = {
    {0.5963023654f, -1.1926047307f, 0.5963023654f, 1.0000000000f,
     -1.3651172372f, 0.4775922501f},
    {1.0000000000f, -2.0000000000f, 1.0000000000f, 1.0000000000f,
     -1.6117270965f, 0.7445208382f},
};

constexpr float HIGHPASS_SOS_24K[HIGHPASS_SECTION_COUNT][6] = {
    {0.7094894751f, -1.4189789503f, 0.7094894751f, 1.0000000000f,
     -1.5590543011f, 0.6140517819f},
    {1.0000000000f, -2.0000000000f, 1.0000000000f, 1.0000000000f,
     -1.7577536095f, 0.8197604429f},
};

constexpr float HIGHPASS_SOS_32K[HIGHPASS_SECTION_COUNT][6] = {
    {0.7733467892f, -1.5466935783f, 0.7733467892f, 1.0000000000f,
     -1.6620099596f, 0.6945706597f},
    {1.0000000000f, -2.0000000000f, 1.0000000000f, 1.0000000000f,
     -1.8252977819f, 0.8610574795f},
};

static_assert(SAMPLE_RATE_HZ == 16000 || SAMPLE_RATE_HZ == 24000 ||
                  SAMPLE_RATE_HZ == 32000,
              "No high-pass coefficients for this SAMPLE_RATE_HZ: add a "
              "table above.");

constexpr const float (&HIGHPASS_SOS)[HIGHPASS_SECTION_COUNT][6] =
    SAMPLE_RATE_HZ == 16000   ? HIGHPASS_SOS_16K
    : SAMPLE_RATE_HZ == 24000 ? HIGHPASS_SOS_24K
                              : HIGHPASS_SOS_32K;
