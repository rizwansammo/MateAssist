import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

// The design system, imported once at the entry point. Contains the Tailwind
// layers, the HemiHead @font-face and the global zero-radius rule (D-100).
//
// Path mirrors the on-disk layout so it resolves identically whether Vite goes
// through the workspace alias (dev, source consumption) or the package exports
// map. Keeping those two in sync is why the subpath is spelled out.
import "@mateassist/ui/styles/base.css";

import App from "./App.jsx";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
