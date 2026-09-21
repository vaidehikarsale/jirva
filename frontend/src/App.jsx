import { Routes, Route } from "react-router-dom";
import Sidebar from "./components/Sidebar";
import Dashboard from "./pages/Dashboard";
import RaiseTicket from "./pages/RaiseTicket";
import TicketResult from "./pages/TicketResult";
import TicketsList from "./pages/TicketsList";
import KnowledgeBase from "./pages/KnowledgeBase";
import Evaluation from "./pages/Evaluation";
import SystemLogs from "./pages/SystemLogs";

export default function App() {
  return (
    <div style={{ display: "flex", height: "100vh" }}>
      <Sidebar />
      <main style={{ flex: 1, overflow: "auto", padding: 24 }}>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/raise" element={<RaiseTicket />} />
          <Route path="/tickets" element={<TicketsList />} />
          <Route path="/ticket/:id" element={<TicketResult />} />
          <Route path="/knowledge-base" element={<KnowledgeBase />} />
          <Route path="/evaluation" element={<Evaluation />} />
          <Route path="/system-logs" element={<SystemLogs />} />
        </Routes>
      </main>
    </div>
  );
}
