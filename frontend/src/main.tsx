import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { AppRoutes } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { registerServiceWorker } from "./lib/registerSW";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Los datos financieros cambian con cada pago: se refrescan al volver a
      // la ventana y no se mantienen "frescos" mas de un minuto.
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});

registerServiceWorker();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
