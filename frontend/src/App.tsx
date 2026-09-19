import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";

import { DemoTour } from "./demo/DemoTour";
import { ThemeProvider } from "./layout/ThemeProvider";
import { AppRoutes } from "./routes";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <AppRoutes />
          <DemoTour />
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
