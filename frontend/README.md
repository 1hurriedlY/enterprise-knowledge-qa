# 前端开发说明

这是企业知识库智能客服系统的 Vue 3 前端骨架，使用 Vite、TypeScript 与 Element Plus。

## 本地启动

```bash
npm install
npm run dev
```

浏览器访问 `http://localhost:5173`。开发服务器会将 `/api` 和 `/health` 请求代理到后端 `http://localhost:8000`。

前端仅保存用户在浏览器内输入的 API Key；不会包含模型服务密钥，也不会读取项目根目录的 `.env`。
