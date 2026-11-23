// FAPI-01. Клиент, Zod-схемы и options TanStack Query из OpenAPI бэкенда.
// Перегенерация: pnpm api:generate; в CI — git diff --exit-code src/shared/api/generated.
import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: process.env.OPENAPI_URL ?? "http://localhost:8000/openapi.json",
  output: "src/shared/api/generated",
  plugins: ["@hey-api/client-fetch", "zod", "@tanstack/react-query"],
});
