# Changelog

## [0.1.0] - 2026-05-01

### English

Initial public Tauri 2 release candidate for the LizzieYzy Next desktop mainline.

Added:

- Tauri 2 + Rust + React/TypeScript desktop workspace.
- SGF import, open, parse, replay, edit, serialize, save, and Save As flows.
- KataGo engine profile setup, asset checks, one-position analysis, full-game analysis, progress events, and cancellation.
- Board, winrate, candidate move, PV, ownership, policy, and review mark UI surfaces.
- SQLite-backed analysis cache with browser-preview fallback behavior.
- Yike/Fox provider and readboard sidecar runtime contracts with offline validation.
- Multi-platform release workflow for macOS, Windows, and Linux CI-built assets.
- Bilingual release notes in English and Chinese.

Fixed before release:

- Invalid SGF parsing now clears stale review data instead of showing old candidate/review marks.
- Cache status no longer reports frame count as impossible move count such as `21/20 moves`.
- Provider and readboard warnings are visible in the UI instead of hidden behind counts or hover-only text.
- English UI no longer contains the previous Chinese-only full-game analysis tooltip.

Verified:

- Scaffold validation.
- Release asset preflight.
- Production release workflow contract validation.
- Frontend production build.
- Rust formatting, clippy, and workspace tests.
- Local macOS Tauri bundle build.

Known limits:

- CI release assets are unsigned unless repository signing/notarization secrets are configured.
- Live Yike/Fox external-service checks and real readboard sidecar hardware checks require maintainer environments.
- This release establishes the new Tauri mainline baseline; it is not a blanket claim of full Java/Swing legacy parity.

### 中文

LizzieYzy Next 桌面主线的首个公开 Tauri 2 发布候选版本。

新增：

- Tauri 2 + Rust + React/TypeScript 桌面工作区。
- SGF 导入、打开、解析、回放、编辑、序列化、保存和另存为。
- KataGo 引擎配置、资源检查、单点分析、全局分析、进度事件和取消。
- 棋盘、胜率图、候选点、PV、ownership、policy 和问题手标记界面。
- SQLite 分析缓存，并支持浏览器预览 fallback。
- Yike/Fox provider 和 readboard sidecar 运行时契约与离线验证。
- 面向 macOS、Windows、Linux 的多平台 CI 发布 workflow。
- 中英双语 release notes。

发布前修复：

- 无效 SGF 解析失败后会清空旧复盘数据，不再继续显示上一局候选点和问题手。
- 缓存状态不再把 frame 数错误显示为 `21/20 moves` 这类不可能的手数。
- Provider 和 readboard warning 会直接显示在界面中，不再只显示数量或依赖 hover。
- 英文界面中移除了原先中文-only 的全局分析 tooltip。

已验证：

- scaffold 校验。
- release asset preflight。
- production release workflow 契约校验。
- 前端生产构建。
- Rust format、clippy 和 workspace tests。
- 本机 macOS Tauri bundle 构建。

已知限制：

- 除非仓库配置签名/公证 secrets，否则 CI release 资产是未签名包。
- 真实 Yike/Fox 外部服务验证和真实 readboard sidecar 设备验证需要维护者环境。
- 本版本建立新的 Tauri 主线基线，不等于对 Java/Swing 旧主线全部细节作 100% 等价承诺。
