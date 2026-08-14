import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import "@mateassist/ui/styles/base.css";

import App from "./App.jsx";

// Derived from Vite's `base` rather than hardcoded, so dev (served at /) and
// production (served at /platform_admin/) both work from one source of truth.
// Hardcoding the basename would break `npm run dev`; omitting it would make
// every route resolve one level up in production, so /login would 404 while the
// bundle itself loaded fine (D-147).
const basename = import.meta.env.BASE_URL.replace(/\/$/, "");

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
