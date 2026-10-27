import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import SiteLayout from "./components/SiteLayout.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Home from "./pages/Home.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Report from "./pages/Report.jsx";
import ResponderDashboard from "./pages/ResponderDashboard.jsx";
import ResponderIntelligence from "./pages/ResponderIntelligence.jsx";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<SiteLayout />}>
          <Route path="/" element={<Home />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/report" element={<Report />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/responder" element={<ResponderDashboard />} />
          <Route
            path="/responder/reports"
            element={<ResponderDashboard showReports />}
          />
          <Route
            path="/responder/reports/:reportId/intelligence"
            element={<ResponderIntelligence />}
          />
          <Route
            path="/responder/intelligence"
            element={<ResponderIntelligence />}
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
