/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Plugin } from "vite";

/** 本機 `npm run dev` 也能呼叫 api/ 的 Functions（部署到 Vercel 時由 Vercel 執行，這段不會用到）。

/api/<name> 對應 api/<name>.ts 裡與 HTTP 方法同名的函式（GET、POST），環境變數讀 .env.local
（包含沒有 VITE_ 前綴、只給伺服器端的 GH_REPO、GH_DISPATCH_TOKEN）。
*/
function localApi(): Plugin {
  return {
    name: "local-api",
    configureServer(server) {
      Object.assign(process.env, loadEnv(server.config.mode, server.config.root, ""));
      server.middlewares.use("/api", async (req, res, next) => {
        const name = (req.url ?? "").split("?")[0].replace(/^\/+/, "");
        if (!/^[\w-]+$/.test(name)) return next();
        try {
          const mod = await server.ssrLoadModule(`/api/${name}.ts`);
          const handler = mod[req.method ?? "GET"] as ((r: Request) => Promise<Response>) | undefined;
          if (!handler) {
            res.statusCode = 405;
            return res.end();
          }
          const resp = await handler(new Request(`http://localhost/api/${name}`, { method: req.method }));
          res.statusCode = resp.status;
          resp.headers.forEach((v, k) => res.setHeader(k, v));
          res.end(Buffer.from(await resp.arrayBuffer()));
        } catch (e) {
          next(e);
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), localApi()],
  test: { include: ["tests/**/*.test.{ts,tsx}"], setupFiles: ["tests/setup.ts"] },
});
