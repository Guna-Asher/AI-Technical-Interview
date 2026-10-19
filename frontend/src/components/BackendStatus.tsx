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
    checking: "Checking backend…",
    connected: "Backend connected (database OK)",
    unreachable: "Backend unreachable",
  }[status];

  const dot = {
    checking: "bg-slate-400",
    connected: "bg-green-500",
    unreachable: "bg-red-500",
  }[status];

  return (
    <div className="flex items-center gap-2 text-sm" role="status">
      <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
      {label}
    </div>
  );
}
