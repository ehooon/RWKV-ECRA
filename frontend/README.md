# RWKV-ECRA React Frontend

React + Vite 独立前端，不修改 `api.py` 或既有后端流程。

## 启动

先安装依赖：

```bash
cd RWKV-ECRA
npm install --prefix frontend
```

启动本地数据/API 解耦层：

```bash
python frontend/server.py --host 127.0.0.1 --port 8787
```

另开一个终端启动 React：

```bash
npm run dev --prefix frontend
```

打开：

```text
http://127.0.0.1:5177
```

## 数据读取

- 优先扫描 `data/output/tasks.jsonl` 和每个任务目录。
- 自动识别任务目录中的 `*.jsonl` 结构化溯源报告和 `*.md` 排版报告。
- 兼容当前样例：`data/output/最终研报_03_结构化溯源数据.jsonl` 和 `data/output/最终研报_02_深度排版溯源版.md`。
- 不读取 `logs`，也不读取或修改 `data/debug_slm`。

## 后端 API

新建任务通过 `frontend/server.py` 代理到：

```text
http://127.0.0.1:8080/api/v1/analyze
```

如果后端 API 不在默认地址，可以设置：

```bash
$env:RWKV_ECRA_API_BASE="http://127.0.0.1:8080"
python frontend/server.py --host 127.0.0.1 --port 8787
```

如果 Python 数据层端口不是 `8787`，可以设置 Vite 代理目标：

```bash
$env:RWKV_ECRA_FRONTEND_API="http://127.0.0.1:8787"
npm run dev --prefix frontend
```
