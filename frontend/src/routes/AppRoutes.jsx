import {
  Navigate,
  Route,
  Routes,
} from "react-router-dom";

import {
  GuestOnly,
  RequireAdmin,
  RequireAuth,
} from "../auth/RouteGuards";
import AppLayout from "../components/layout/AppLayout";
import AccountPage from "../pages/AccountPage";
import AdminPage from "../pages/AdminPage";
import AnalysisHistoryPage from "../pages/AnalysisHistoryPage";
import AnalysisResultsPage from "../pages/AnalysisResultsPage";
import AnalysisVisualizationPage from "../pages/AnalysisVisualizationPage";
import DashboardPage from "../pages/DashboardPage";
import DetectionsPage from "../pages/DetectionsPage";
import DeviceDetailPage from "../pages/DeviceDetailPage";
import DevicesPage from "../pages/DevicesPage";
import LoginPage from "../pages/LoginPage";
import ManualAnalysisPage from "../pages/ManualAnalysisPage";
import RegisterPage from "../pages/RegisterPage";


function AppRoutes() {
  return (
    <Routes>
      <Route element={<GuestOnly />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<DashboardPage />} />

          <Route path="/devices" element={<DevicesPage />} />
          <Route path="/devices/:deviceId" element={<DeviceDetailPage />} />

          <Route path="/detections" element={<DetectionsPage />} />

          <Route path="/analysis" element={<ManualAnalysisPage />} />
          <Route path="/analysis/history" element={<AnalysisHistoryPage />} />
          <Route path="/analysis/:captureSessionId" element={<AnalysisResultsPage />} />
          <Route
            path="/analysis/:captureSessionId/visualization"
            element={<AnalysisVisualizationPage />}
          />

          <Route path="/account" element={<AccountPage />} />

          <Route element={<RequireAdmin />}>
            <Route path="/admin" element={<AdminPage />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}


export default AppRoutes;
