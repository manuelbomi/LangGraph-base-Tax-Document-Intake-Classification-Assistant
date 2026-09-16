import { NavLink, Route, Routes } from "react-router-dom";

import { DocumentDetailPage } from "./pages/DocumentDetailPage";
import { OrganizerPage } from "./pages/OrganizerPage";
import { UploadPage } from "./pages/UploadPage";

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        `rounded-md px-3 py-1.5 text-sm font-medium ${
          isActive ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div>
            <h1 className="text-base font-semibold text-slate-900">
              Tax Document Intake &amp; Classification Assistant
            </h1>
            <p className="text-xs text-slate-400">Built with LangGraph</p>
          </div>
          <nav className="flex gap-1">
            <NavItem to="/">Upload &amp; Process</NavItem>
            <NavItem to="/organizer">Client Organizer</NavItem>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/organizer" element={<OrganizerPage />} />
          <Route path="/documents/:id" element={<DocumentDetailPage />} />
        </Routes>
      </main>
    </div>
  );
}
