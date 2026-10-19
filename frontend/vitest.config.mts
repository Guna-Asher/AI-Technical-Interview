import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";

// `npm test` runs the unit and component tests (jsdom, no network).
// `npm run test:integration` runs only the *.integration.test.ts files against the live backend.
const integration = process.env.INTEGRATION === "1";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: {
    environment: integration ? "node" : "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    include: integration ? ["src/**/*.integration.test.ts"] : ["src/**/*.test.{ts,tsx}"],
    exclude: integration ? configDefaults.exclude : [...configDefaults.exclude, "src/**/*.integration.test.ts"],
  },
});
