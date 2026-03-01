import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["lib/**/*.test.ts"],
    environment: "node",
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      reportsDirectory: "./coverage",
      include: ["lib/**/*.ts"],
      exclude: ["lib/**/*.test.ts"],
      thresholds: {
        lines: 90,
        statements: 90,
        functions: 90,
        branches: 85
      }
    }
  }
});
