"use client";

import { useEffect, useState } from "react";

type Status = "checking" | "connected" | "unreachable";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function BackendStatus() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/health`)
      .then((response) => setStatus(response.ok ? "connected" : "unreachable"))
      .catch(() => setStatus("unreachable"));
  }, []);

  const label = {
    checking: "Checking the service…",
    connected: "Service connected",
    unreachable: "The service is unreachable. Check that the backend is running.",
  }[status];

  const dot = { checking: "bg-edge", connected: "bg-moss", unreachable: "bg-brick" }[status];
  const text = status === "unreachable" ? "font-medium text-brick" : "text-graphite";

  return (
    <div className={`flex items-center gap-2 text-sm ${text}`} role="status">
      <span aria-hidden="true" className={`size-2 rounded-full ${dot}`} />
      {label}
    </div>
  );
}
