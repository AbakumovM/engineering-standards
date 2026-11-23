// Шаблон ESLint (flat config) для фронтенда по правилам engineering-standards.
// Имена экспортов плагинов меняются между версиями — сверить с README установленных версий.
import js from "@eslint/js";
import boundaries from "eslint-plugin-boundaries";
import prettier from "eslint-config-prettier/flat";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import { defineConfig, globalIgnores } from "eslint/config";
import tseslint from "typescript-eslint";

export default defineConfig([
  globalIgnores(["dist", "coverage", "src/shared/api/generated", "src/routeTree.gen.ts"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      js.configs.recommended,
      tseslint.configs.strictTypeChecked,          // FTS-02, FTS-03
      tseslint.configs.stylisticTypeChecked,
      reactHooks.configs.flat.recommended,         // FCMP-03 и правила React Compiler
      jsxA11y.flatConfigs.recommended,             // FA11Y-01, FA11Y-03
    ],
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { boundaries },
    settings: {
      "import/resolver": { typescript: { alwaysTryTypes: true } },
      "boundaries/elements": [
        { type: "app", pattern: "src/app" },
        { type: "routes", pattern: "src/routes" },
        { type: "feature", pattern: "src/features/*", capture: ["feature"] },
        { type: "shared", pattern: "src/shared" },
      ],
    },
    rules: {
      // FDEP-01, FDEP-02: app → routes → features → shared
      "boundaries/element-types": ["error", {
        default: "disallow",
        rules: [
          { from: "app", allow: ["app", "routes", "feature", "shared"] },
          { from: "routes", allow: ["routes", "feature", "shared"] },
          { from: "feature", allow: ["feature", "shared"] },   // фича → фича — через index.ts, без циклов (FDEP-04)
          { from: "shared", allow: ["shared"] },
        ],
      }],
      // FDEP-03: чужая фича — только через index.ts
      "boundaries/entry-point": ["error", {
        default: "allow",
        rules: [{ target: ["feature"], disallow: ["**"], allow: ["index.ts"] }],
      }],
      "@typescript-eslint/ban-ts-comment": ["error", { "ts-expect-error": "allow-with-description" }],
      "@typescript-eslint/no-explicit-any": "error",
      "no-console": ["error", { allow: ["warn", "error"] }],            // FOBS-04
      "no-eval": "error",                                               // FSEC-10
      "no-implied-eval": "off",
      "@typescript-eslint/no-implied-eval": "error",
      "no-restricted-imports": ["error", {
        paths: [
          { name: "moment", message: "FPERF-06: Intl или date-fns" },
          { name: "lodash", message: "FPERF-06: lodash-es по функциям или стандартная библиотека" },
          { name: "axios", message: "FAPI-02: запросы — через клиент из shared/api" },
        ],
      }],
      "no-restricted-syntax": ["error",
        { selector: "TSEnumDeclaration", message: "FTS-05: объединение литералов или as const" },
      ],
    },
  },
  {
    files: ["**/*.test.{ts,tsx}", "e2e/**", "src/test/**"],
    rules: { "@typescript-eslint/no-non-null-assertion": "off", "boundaries/element-types": "off" },
  },
  prettier,
]);
