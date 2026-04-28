# LizzieYzy Next 新主线架构

## 目标

把现有 Java/Swing 维护分支演进为全新的本地复盘平台：

```text
Tauri 2 shell
  -> Rust domain/backend workspace
  -> TypeScript React UI
  -> KataGo analysis JSONL first
  -> SQLite analysis cache
  -> Fox/readboard as providers/sidecars
```

## 分层

```text
apps/desktop/src                 UI：棋盘、胜率图、候选点、工作流
apps/desktop/src-tauri           Tauri command gateway
crates/app-model                 DTO 和跨层类型
crates/go-core                   围棋规则纯核心
crates/sgf                       SGF/GIB 导入导出
crates/katago-protocol           KataGo analysis JSONL 协议
crates/engine-manager            引擎、sidecar、资源生命周期
crates/analysis-core             分析归一化、问题手分类
crates/storage                   SQLite schema/migration/cache
```

## 核心原则

1. 旧 Java 代码只作为行为规格，不作为新架构骨架。
2. UI 不直接读 KataGo raw JSON；所有结果先归一化为 `AnalysisFrameDto`。
3. 所有阻塞 I/O、进程、下载、文件和 sidecar 管理都放 Rust 后端。
4. 棋盘渲染输入必须是纯数据 `GameDto + AnalysisFrameDto`。
5. 发布包体验是一等需求：KataGo、权重、readboard 都以 asset/provider 管理。

## 第一阶段验收

- 新主线能单独启动 Tauri/Vite UI。
- Rust 命令能返回 health、解析 SGF、生成 fake analysis。
- `go-core`、`sgf`、`katago-protocol`、`analysis-core` 具备独立测试。
- 不修改旧 Java/Swing 文件。

## 第二阶段迁移方向

- 把 fake analysis 替换为真实 KataGo analysis JSONL streaming。
- 接入 SQLite 写入和断点续跑。
- 把野狐抓谱作为 `GameSourceProvider` 实现。
- 把 readboard_java/native readboard 作为 sidecar 实现。
- 建立旧 Java 行为 golden tests：SGF、GTP、抓谱、发布包资源。
