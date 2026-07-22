import { defineConfig } from "kubb"
import { pluginTs } from "@kubb/plugin-ts"
import { pluginZod } from "@kubb/plugin-zod"

export default defineConfig({
  input: { path: "../backend/openapi.json" },
  output: { path: "./src/gen", clean: true },
  plugins: [
    pluginTs({ output: { path: "types" } }),   // 型
    pluginZod({ output: { path: "zod" } }),     // 実行時検証（typed は付けない）
  ],
})
