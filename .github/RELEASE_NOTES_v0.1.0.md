# LizzieYzy Next v0.1.0

## English

LizzieYzy Next v0.1.0 is the first public Tauri 2 release candidate for the next-generation LizzieYzy desktop Go review workspace. It ships the Rust + TypeScript architecture baseline, local SGF workflows, KataGo profile wiring, analysis cache support, provider/readboard runtime contracts, and multi-platform CI packaging.

### Highlights

- Tauri 2 desktop app with React, TypeScript, Vite, and Rust command boundaries.
- SGF open, parse, replay, edit, save, and Save As workflows.
- Board, winrate chart, candidate move, PV, ownership, policy, and review mark surfaces.
- KataGo engine profiles with path pickers, asset checks, one-position analysis, full-game batch analysis, progress, and cancellation.
- SQLite-backed analysis cache with local browser fallback for preview mode.
- Yike/Fox provider and readboard sidecar runtime contracts, plus offline validation paths.
- GitHub Actions CI for scaffold validation, frontend build, Rust fmt, clippy, and tests.
- Multi-platform release workflow for macOS, Windows, and Linux CI-built bundles.

### Downloads

Choose the asset for your platform:

- macOS: `.dmg`
- Windows: `.exe` or `.msi`
- Linux: `.AppImage`, `.deb`, or `.rpm`

Checksum files are included as `SHA256SUMS.txt` and `SHA256SUMS-<platform>.txt`.

### Known limitations

- CI-built release assets are unsigned in this repository unless maintainers configure signing and notarization secrets.
- Live Yike/Fox external-network checks and real readboard sidecar device checks require accounts, network access, and sidecar environments that are not available in CI.
- This is the new Tauri mainline baseline, not a guarantee of complete legacy Java/Swing feature parity.

## 中文

LizzieYzy Next v0.1.0 是下一代 LizzieYzy 桌面围棋复盘工作区的首个公开 Tauri 2 发布候选版本。它交付了 Rust + TypeScript 架构基线、本地 SGF 工作流、KataGo 配置链路、分析缓存、棋谱平台/readboard 运行时契约，以及多平台 CI 打包流程。

### 亮点

- Tauri 2 桌面应用，前端使用 React、TypeScript、Vite，后端通过 Rust/Tauri command 承载核心能力。
- SGF 打开、解析、回放、编辑、保存和另存为。
- 棋盘、胜率图、候选点、PV、ownership、policy 和问题手标记界面。
- KataGo 引擎配置、路径选择、资源检查、单点分析、全局分析、进度显示和取消。
- SQLite 分析缓存，并提供浏览器预览模式下的本地 fallback。
- Yike/Fox provider 与 readboard sidecar 的运行时契约和离线验证路径。
- GitHub Actions 覆盖 scaffold 校验、前端构建、Rust fmt、clippy 和测试。
- 面向 macOS、Windows、Linux 的多平台 CI 发布打包流程。

### 下载

请选择对应平台的资产：

- macOS：`.dmg`
- Windows：`.exe` 或 `.msi`
- Linux：`.AppImage`、`.deb` 或 `.rpm`

校验文件包括 `SHA256SUMS.txt` 和 `SHA256SUMS-<platform>.txt`。

### 已知限制

- 除非维护者配置签名和公证 secrets，否则本仓库 CI 生成的发布资产是未签名包。
- 真实 Yike/Fox 外网环境验证和真实 readboard sidecar 设备验证需要账号、网络和 sidecar 环境，CI 无法替代。
- 这是新的 Tauri 主线基线，不等于已经 100% 覆盖旧 Java/Swing 应用的全部细节。
