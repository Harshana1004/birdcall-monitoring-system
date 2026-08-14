import {
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import AnalysisResultsPage from "../pages/AnalysisResultsPage";
import AnalysisVisualizationPage from "../pages/AnalysisVisualizationPage";
import ManualAnalysisPage from "../pages/ManualAnalysisPage";


function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <Navigate
            to="/analysis"
            replace
          />
        }
      />

      <Route
        path="/analysis"
        element={
          <ManualAnalysisPage />
        }
      />

      <Route
        path="/analysis/:captureSessionId"
        element={
          <AnalysisResultsPage />
        }
      />

      <Route
        path="/analysis/:captureSessionId/visualization"
        element={
          <AnalysisVisualizationPage />
        }
      />

      <Route
        path="*"
        element={
          <Navigate
            to="/analysis"
            replace
          />
        }
      />
    </Routes>
  );
}


export default AppRoutes;