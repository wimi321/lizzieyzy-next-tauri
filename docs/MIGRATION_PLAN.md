# 从 Java/Swing 维护分支迁移到 Tauri/Rust/TypeScript

## Planner 拆解

| 子任务 | Owner | Owned files / modules | 依赖 | 可并行 | 验收标准 |
|---|---|---|---|---|---|
| 新主线 workspace | Worker-1 | `Cargo.toml`, `crates/**`, `apps/desktop/src-tauri/**` | 无 | 是 | Rust workspace 结构完整；Tauri config 有效 |
| 前端桌面壳 | Worker-2 | `apps/desktop/src/**`, `apps/desktop/package.json`, `vite.config.ts` | 无 | 是 | UI 能展示棋盘、图表、候选点、SGF 输入 |
| SGF/规则核心 | Worker-1 | `crates/go-core`, `crates/sgf` | workspace | 是 | 有最小单测；不依赖 UI/Tauri |
| KataGo 协议与引擎计划 | Worker-1 | `crates/katago-protocol`, `crates/engine-manager` | workspace | 是 | 支持 JSONL query/response DTO 与命令构造 |
| 分析视图与问题手 | Worker-2 | `components/*`, `domain/*` | 前端壳 | 是 | fake analysis 可驱动棋盘和图表 |
| Reviewer 门禁 | Reviewer | 全部新增文件，只审查 | Worker 输出 | 否 | 无 ownership 冲突；无破坏旧分支；结构可迁入 |
| Lead 集成 | Lead | 打包 artifact、总结 | Reviewer 通过 | 否 | 验证脚本通过，输出剩余风险 |

## 并行策略

- Worker-1 独占 Rust/Tauri 后端：`Cargo.toml`, `crates/**`, `apps/desktop/src-tauri/**`。
- Worker-2 独占 TypeScript 前端：`apps/desktop/src/**`, `apps/desktop/package.json`, `apps/desktop/tsconfig.json`, `apps/desktop/vite.config.ts`, `apps/desktop/index.html`。
- Lead 独占 docs/scripts/artifact，不与 Worker 同时修改代码文件。
- Reviewer 不改文件，只审查。

## 迁入步骤

1. 原仓库建新分支 `tauri-next`。
2. 复制本包到仓库根目录。
3. 新增 CI job：`cargo test --workspace`、`npm run build`、`tauri build`。
4. 暂不删除 Java/Maven 旧链路。
5. 将旧 Java 中的 SGF、KataGo、野狐抓谱行为逐步转成 golden tests。
6. 当新主线完成真实 KataGo streaming、SQLite cache、Fox provider、readboard sidecar 后，发布 alpha。

## 本轮未完成

真实 KataGo 进程 streaming、FoxWQ 抓谱、readboard 协议、所有历史设置迁移、生产级签名和安装器矩阵。
