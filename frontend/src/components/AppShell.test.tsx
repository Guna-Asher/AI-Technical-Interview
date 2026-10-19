import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";
import nextConfig from "../../next.config";
import { APP_NAME } from "@/lib/brand";
import AppShell from "./AppShell";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

beforeEach(() => {
  vi.stubGlobal("fetch", () => Promise.resolve(new Response(JSON.stringify({ status: "ok", database: "ok" }), { status: 200 })));
});

describe("page frame", () => {
  it("provides header, main and footer landmarks and a wordmark link home", async () => {
    render(
      <AppShell>
        <p>page content</p>
      </AppShell>,
    );

    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveTextContent("page content");
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: APP_NAME })).toHaveAttribute("href", "/");
    expect(await screen.findByText("Service connected")).toBeInTheDocument();
  });

  it("states plainly when the service cannot be reached", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new TypeError("Failed to fetch")));
    render(<AppShell>content</AppShell>);

    expect(await screen.findByText(/The service is unreachable/)).toBeInTheDocument();
  });
});

describe("identity", () => {
  it("shows no framework branding in the rendered entry page", () => {
    const { container } = render(
      <AppShell>
        <Home />
      </AppShell>,
    );

    expect(container.innerHTML).not.toMatch(/next\.js|nextjs|vercel/i);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Practise the interview you are about to have.");
  });

  it("offers a free-text role, with no preset roles anywhere on the entry page", () => {
    const { container } = render(<Home />);

    expect(container.querySelector("select, datalist, option")).toBeNull();
    expect(screen.getByLabelText("Job role")).toHaveAttribute("type", "text");
  });

  it("turns off the framework's dev badge and powered-by header", () => {
    expect(nextConfig.devIndicators).toBe(false);
    expect(nextConfig.poweredByHeader).toBe(false);
  });
});
