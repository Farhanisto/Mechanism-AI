import { useEffect, useState } from "react";

import { LandingPage } from "./landing/LandingPage";
import { WorkspaceApp } from "./WorkspaceApp";

type Route = "landing" | "workspace";

function currentRoute(): Route {
  return window.location.hash.startsWith("#/app") ? "workspace" : "landing";
}

export function App() {
  const [route, setRoute] = useState<Route>(currentRoute);

  useEffect(() => {
    const onHashChange = () => {
      const next = currentRoute();
      setRoute(next);
      if (next === "workspace" || window.location.hash === "#/") {
        try {
          window.scrollTo({ top: 0, behavior: "auto" });
        } catch {
          window.scrollTo(0, 0);
        }
      }
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return route === "workspace" ? <WorkspaceApp /> : <LandingPage />;
}
