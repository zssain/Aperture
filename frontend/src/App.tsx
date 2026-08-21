import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { setUnauthorizedHandler } from "./lib/api";
import { queryClient } from "./lib/queryClient";
import { SESSION_QUERY_KEY } from "./features/auth/useSession";
import { AppRoutes } from "./routes";

export default function App() {
  const navigate = useNavigate();

  useEffect(() => {
    // A 401 mid-session clears the cached session and redirects to sign-in,
    // preserving the return URL so the user lands back where they were.
    setUnauthorizedHandler((returnTo) => {
      queryClient.setQueryData(SESSION_QUERY_KEY, null);
      navigate("/signin", { replace: true, state: { returnTo } });
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate]);

  return <AppRoutes />;
}
