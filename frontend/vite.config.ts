import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 백엔드(FastAPI :8000)로 /api 를 프록시한다 — 브라우저는 같은 출처로만 호출하므로 CORS 불필요.
// fs.allow: 공용 계약(shared/types)과 데모 입력(mocks/chats)을 리포 루트에서 가져온다.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
    fs: { allow: [".."] },
  },
});
