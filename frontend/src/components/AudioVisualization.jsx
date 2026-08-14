import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";


function AudioVisualization({
  visualization,
}) {
  if (!visualization) {
    return null;
  }


  const waveformData =
    visualization.waveform_times.map(
      (time, index) => ({
        time,
        amplitude:
          visualization
            .waveform_values[index],
      })
    );


  const energyData =
    visualization.energy_times.map(
      (time, index) => ({
        time,
        energy:
          visualization
            .energy_values[index],
      })
    );


  return (
    <section className="visualization-section">
      <div className="visualization-header">
        <div>
          <h2>
            Audio Processing
          </h2>

          <p>
            Detected acoustic regions are
            highlighted on the normalized
            waveform and short-time energy
            signal.
          </p>
        </div>
      </div>


      {/* ==============================================
          Waveform
          ============================================== */}

      <div className="chart-container">
        <div className="chart-heading">
          <h3>
            Normalized Audio Waveform
          </h3>

          <span>
            Amplitude vs. time
          </span>
        </div>

        <div className="chart">
          <ResponsiveContainer
            width="100%"
            height={280}
          >
            <AreaChart
              data={waveformData}
              margin={{
                top: 10,
                right: 20,
                left: 0,
                bottom: 10,
              }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
              />

              <XAxis
                dataKey="time"
                type="number"
                domain={[
                  "dataMin",
                  "dataMax",
                ]}
                tickFormatter={(value) =>
                  `${value.toFixed(0)}s`
                }
              />

              <YAxis
                domain={[
                  -1,
                  1,
                ]}
              />

              <Tooltip
                formatter={(value) => [
                  Number(value).toFixed(4),
                  "Amplitude",
                ]}
                labelFormatter={(value) =>
                  `${Number(value).toFixed(
                    2
                  )} s`
                }
              />


              {/* Highlight every detected ROI */}

              {visualization.rois.map(
                (roi) => (
                  <ReferenceArea
                    key={
                      roi.recording_id
                    }
                    x1={
                      roi.start_time_seconds
                    }
                    x2={
                      roi.end_time_seconds
                    }
                    fillOpacity={0.18}
                  />
                )
              )}


              <Area
                type="monotone"
                dataKey="amplitude"
                stroke="currentColor"
                fill="currentColor"
                fillOpacity={0.12}
                isAnimationActive={
                  false
                }
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>


      {/* ==============================================
          Short-Time Energy
          ============================================== */}

      <div className="chart-container">
        <div className="chart-heading">
          <h3>
            Short-Time Energy
          </h3>

          <span>
            Adaptive ROI detection
          </span>
        </div>

        <div className="chart">
          <ResponsiveContainer
            width="100%"
            height={280}
          >
            <LineChart
              data={energyData}
              margin={{
                top: 10,
                right: 20,
                left: 10,
                bottom: 10,
              }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
              />

              <XAxis
                dataKey="time"
                type="number"
                domain={[
                  "dataMin",
                  "dataMax",
                ]}
                tickFormatter={(value) =>
                  `${value.toFixed(0)}s`
                }
              />

              <YAxis />

              <Tooltip
                formatter={(value) => [
                  Number(value).toFixed(6),
                  "Energy",
                ]}
                labelFormatter={(value) =>
                  `${Number(value).toFixed(
                    2
                  )} s`
                }
              />


              {/* Energy threshold */}

              <ReferenceLine
                y={
                  visualization
                    .energy_threshold
                }
                strokeDasharray="6 4"
                label={{
                  value:
                    "Energy threshold",
                  position: "insideTopRight",
                }}
              />


              {/* Detected ROIs */}

              {visualization.rois.map(
                (roi) => (
                  <ReferenceArea
                    key={
                      roi.recording_id
                    }
                    x1={
                      roi.start_time_seconds
                    }
                    x2={
                      roi.end_time_seconds
                    }
                    fillOpacity={0.12}
                  />
                )
              )}


              <Line
                type="monotone"
                dataKey="energy"
                dot={false}
                isAnimationActive={
                  false
                }
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>


      {/* ==============================================
          Explanation
          ============================================== */}

      <div className="processing-explanation">
        <div>
          <strong>
            ROI threshold
          </strong>

          <span>
            {visualization
              .energy_threshold
              .toFixed(6)}
          </span>
        </div>

        <div>
          <strong>
            Acoustic regions
          </strong>

          <span>
            {
              visualization
                .rois.length
            }
          </span>
        </div>
      </div>
    </section>
  );
}


export default AudioVisualization;