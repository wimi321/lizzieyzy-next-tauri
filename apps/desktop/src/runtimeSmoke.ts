import {
  appendSgfMove,
  deleteSgfNode,
  editSgfMove,
  isTauriRuntime,
  loadRuntimeSmokeConfig,
  parseSgfSummary,
  parseSgfTree,
  readSgfDocument,
  reorderSgfVariation,
  replaySgfPositionAtNode,
  replaySgfPositions,
  runtimeSmokeReport,
  saveSgfDocument,
  updateSgfNodeComment,
  updateSgfNodeProperties
} from "./api/backend";
import type { MoveVertex, PlayerColor, SgfTreeDto, SgfTreeNodeDto } from "./domain/types";

type RuntimeSmokeStatus = "pass" | "fail";
type RuntimeSmokeCheckName =
  | "runtime_started"
  | "sgf_loaded"
  | "branch_navigation"
  | "comment_edit"
  | "property_edit"
  | "append_move"
  | "edit_move"
  | "delete_node"
  | "variation_reorder"
  | "save_readback_roundtrip"
  | "board_state_verified";
type RuntimeSmokeCheck = {
  name: RuntimeSmokeCheckName;
  status: RuntimeSmokeStatus;
  details?: Record<string, unknown>;
  error?: string;
};
type RuntimeSmokeStep = {
  name: string;
  status: RuntimeSmokeStatus;
  details?: Record<string, unknown>;
  error?: string;
};
type RuntimeSmokeReport = {
  schema: "lizzieyzy.tauri-runtime-ui-smoke.v1";
  name: "ui_tauri_runtime_smoke";
  status: RuntimeSmokeStatus;
  platform: "macos";
  startedAt: string;
  finishedAt: string;
  sgfPath: string | null;
  reportPath: string | null;
  checks: RuntimeSmokeCheck[];
  steps: RuntimeSmokeStep[];
  error?: string;
};
type RuntimeSmokeImportMeta = ImportMeta & { env?: Record<string, string | undefined> };
type EditableMove = { id: string; color: PlayerColor; vertex: MoveVertex; parentId: string | null };
type RuntimeSmokeConfig = { enabled: boolean; sgfPath: string | null; reportPath: string | null };

const schema = "lizzieyzy.tauri-runtime-ui-smoke.v1";
const truthyValues = new Set(["1", "true", "yes", "on"]);

export function isRuntimeSmokeModeEnabled(): boolean {
  const value = runtimeSmokeImportMeta().env?.VITE_LIZZIEYZY_RUNTIME_SMOKE;
  return typeof value === "string" && truthyValues.has(value.trim().toLowerCase());
}

export async function resolveRuntimeSmokeConfig(): Promise<RuntimeSmokeConfig> {
  const envEnabled = isRuntimeSmokeModeEnabled();
  const envSgfPath = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH");
  const envReportPath = runtimeSmokeEnv("VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH");
  if (envEnabled || envSgfPath || envReportPath) {
    return { enabled: envEnabled, sgfPath: envSgfPath, reportPath: envReportPath };
  }
  if (!isTauriRuntime()) return { enabled: false, sgfPath: null, reportPath: null };
  try {
    const config = await loadRuntimeSmokeConfig();
    return {
      enabled: config.enabled,
      sgfPath: normalizeOptionalString(config.sgf_path),
      reportPath: normalizeOptionalString(config.report_path)
    };
  } catch {
    return { enabled: false, sgfPath: null, reportPath: null };
  }
}

export async function runRuntimeSmokeMode(config?: RuntimeSmokeConfig): Promise<RuntimeSmokeReport> {
  const resolvedConfig = config ?? await resolveRuntimeSmokeConfig();
  const sgfPath = resolvedConfig.sgfPath;
  const reportPath = resolvedConfig.reportPath;
  const report: RuntimeSmokeReport = {
    schema,
    name: "ui_tauri_runtime_smoke",
    status: "fail",
    platform: "macos",
    startedAt: new Date().toISOString(),
    finishedAt: "",
    sgfPath,
    reportPath,
    checks: [],
    steps: []
  };

  try {
    if (!sgfPath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_SGF_PATH is required.");
    if (!reportPath) throw new Error("VITE_LIZZIEYZY_RUNTIME_SMOKE_REPORT_PATH is required.");
    if (!resolvedConfig.enabled) throw new Error("Runtime smoke config is not enabled.");

    await check(report, "runtime_started", async () => {
      if (!isTauriRuntime()) throw new Error("Runtime smoke mode must run inside the real Tauri runtime.");
      return {
        tauriInternals: true,
        userAgent: typeof navigator === "undefined" ? null : navigator.userAgent,
        platform: typeof navigator === "undefined" ? null : navigator.platform
      };
    });

    const loaded = await check(report, "sgf_loaded", async () => {
      const document = await readSgfDocument(sgfPath);
      assertNonEmptyString(document.sgfText, "readSgfDocument returned empty SGF text.");
      await verifySgf(report, "source", document.sgfText);
      return { sgfText: document.sgfText, details: { bytes: document.sgfText.length, path: document.path } };
    });
    const source = loaded.sgfText;

    const sourceTree = await step(report, "parse source tree for edit targets", () => parseSgfTree(source));
    const branchNode = findBranchNode(sourceTree);
    await check(report, "branch_navigation", async () => {
      const position = await replaySgfPositionAtNode(source, branchNode.id);
      if (position.move_number < 1) throw new Error("Branch replay did not advance to a move position.");
      return { nodeId: branchNode.id, moveNumber: position.move_number, stones: position.stones.length };
    });

    const updatedComment = `runtime smoke branch ${report.startedAt}`;
    let edited = (await check(report, "comment_edit", async () => {
      const text = await updateSgfNodeComment(source, branchNode.id, updatedComment);
      const tree = await parseSgfTree(text);
      const node = requireNode(tree, branchNode.id, "comment-edited branch node");
      if (node.comment !== updatedComment) throw new Error("Updated branch comment was not preserved in the SGF tree.");
      return { sgfText: text, details: { nodeId: node.id, comment: node.comment } };
    })).sgfText;

    edited = (await check(report, "property_edit", async () => {
      const result = await updateSgfNodeProperties(edited, branchNode.id, [
        { key: "N", values: ["runtime-smoke-branch"] },
        { key: "LB", values: ["aa:A"] }
      ]);
      const tree = await parseSgfTree(result.sgf_text);
      const node = requireNode(tree, branchNode.id, "property-edited branch node");
      assertPropertyValue(node, "N", "runtime-smoke-branch");
      assertPropertyValue(node, "LB", "aa:A");
      return { sgfText: result.sgf_text, details: { nodeId: result.node_id } };
    })).sgfText;

    const treeBeforeAppend = await step(report, "parse tree before append", () => parseSgfTree(edited));
    const root = requireNode(treeBeforeAppend, treeBeforeAppend?.root_id, "append parent root node");
    const appendParent = requireNode(treeBeforeAppend, root.child_ids[0], "append parent first move node");
    const appendColor: PlayerColor = "white";
    const appendVertex = chooseUnusedSiblingVertex(treeBeforeAppend, appendParent.id);
    const appended = await check(report, "append_move", async () => {
      const result = await appendSgfMove(edited, appendParent.id, appendColor, appendVertex);
      const tree = await parseSgfTree(result.sgf_text);
      const node = requireNode(tree, result.new_node_id, "appended move node");
      if (node.color !== appendColor || vertexKey(node.vertex) !== vertexKey(appendVertex)) {
        throw new Error("Appended move was not found at the expected vertex.");
      }
      return { sgfText: result.sgf_text, details: { nodeId: result.new_node_id, vertex: vertexKey(appendVertex) } };
    });
    edited = appended.sgfText;
    const appendedNodeId = String(appended.details?.nodeId ?? "");
    if (!appendedNodeId) throw new Error("append_move did not return an appended node id.");

    const editVertex = chooseDifferentSiblingVertex(await parseSgfTree(edited), appendedNodeId);
    edited = (await check(report, "edit_move", async () => {
      const result = await editSgfMove(edited, appendedNodeId, appendColor, editVertex);
      const tree = await parseSgfTree(result.sgf_text);
      const node = requireNode(tree, appendedNodeId, "edited appended move node");
      if (node.color !== appendColor || vertexKey(node.vertex) !== vertexKey(editVertex)) {
        throw new Error("Edited move was not found at the expected vertex.");
      }
      return {
        sgfText: result.sgf_text,
        details: {
          nodeId: result.node_id,
          targetVertex: vertexKey(editVertex),
          confirmedVertex: vertexKey(node.vertex),
          editVertex: vertexKey(editVertex)
        }
      };
    })).sgfText;

    let movedNodeId = appendedNodeId;
    const reorderTargetIndex = 0;
    const reordered = await check(report, "variation_reorder", async () => {
      const result = await reorderSgfVariation(edited, appendedNodeId, reorderTargetIndex);
      const tree = await parseSgfTree(result.sgf_text);
      const updatedParent = requireNode(tree, result.parent_node_id, "parent node after variation reorder");
      const movedNode = requireNode(tree, result.node_id, "moved variation node");
      const indexAfterMove = updatedParent.child_ids.indexOf(result.node_id);
      if (result.parent_node_id !== appendParent.id) throw new Error("Reordered variation returned an unexpected parent.");
      if (movedNode.parent_id !== result.parent_node_id) throw new Error("Moved variation is not under the returned parent.");
      if (indexAfterMove !== reorderTargetIndex) throw new Error("Moved variation did not land at target sibling index 0.");
      if (movedNode.variation_index !== reorderTargetIndex) throw new Error("Moved variation did not receive variation_index 0.");
      return {
        sgfText: result.sgf_text,
        details: {
          oldNodeId: appendedNodeId,
          movedNodeId: result.node_id,
          parentNodeId: result.parent_node_id,
          targetIndex: reorderTargetIndex,
          indexAfterMove,
          variationIndexAfterMove: movedNode.variation_index,
          siblingCount: updatedParent.child_ids.length,
          siblingIndex: indexAfterMove,
          movedIsMainline: movedNode.is_mainline
        }
      };
    });
    edited = reordered.sgfText;
    movedNodeId = String(reordered.details?.movedNodeId ?? "");
    if (!movedNodeId) throw new Error("variation_reorder did not return a moved node id.");

    edited = (await check(report, "delete_node", async () => {
      const result = await deleteSgfNode(edited, movedNodeId);
      const tree = await parseSgfTree(result.sgf_text);
      const updatedParent = requireNode(tree, result.parent_node_id, "parent node after delete");
      const targetExistsAfterDelete = updatedParent.child_ids
        .map((childId) => requireNode(tree, childId, "sibling after delete"))
        .some((node) => node.color === appendColor && vertexKey(node.vertex) === vertexKey(editVertex));
      if (targetExistsAfterDelete) throw new Error("Deleted move target is still present in the SGF tree.");
      return {
        sgfText: result.sgf_text,
        details: {
          deletedNodeIdBeforeDelete: movedNodeId,
          oldNodeId: appendedNodeId,
          movedNodeId,
          deletedNodeId: movedNodeId,
          deletedTargetVertex: vertexKey(editVertex),
          parentNodeId: result.parent_node_id,
          remainingSiblingCount: updatedParent.child_ids.length,
          targetExistsAfterDelete,
          existsAfterDelete: targetExistsAfterDelete,
          absentAfterDelete: !targetExistsAfterDelete,
          deleteAbsence: !targetExistsAfterDelete
        }
      };
    })).sgfText;

    const readbackResult = await check(report, "save_readback_roundtrip", async () => {
      const saved = await saveSgfDocument(sgfPath, edited, "runtime-smoke.sgf");
      if (!saved?.path) throw new Error("saveSgfDocument did not return a saved path.");
      const document = await readSgfDocument(sgfPath);
      if (saved.sgfText !== edited) throw new Error("Saved SGF text does not match edited text.");
      if (document.sgfText !== edited) throw new Error("Readback SGF does not match saved SGF text.");
      return {
        sgfText: document.sgfText,
        details: {
          path: saved.path,
          savedPath: saved.path,
          bytes: document.sgfText.length,
          saveVerified: saved.sgfText === edited,
          readbackVerified: document.sgfText === edited,
          readbackMatchesSaved: document.sgfText === saved.sgfText,
          savedStatus: "matched_edited_text",
          readbackStatus: "matched_saved_text"
        }
      };
    });
    const readback = readbackResult.sgfText;

    await check(report, "board_state_verified", async () => {
      await verifySgf(report, "readback", readback);
      const tree = await parseSgfTree(readback);
      const node = findBranchNode(tree);
      assertPropertyValue(node, "N", "runtime-smoke-branch");
      assertPropertyValue(node, "LB", "aa:A");
      const position = await replaySgfPositionAtNode(readback, node.id);
      if (position.errors.length > 0) throw new Error(`Readback replay had errors: ${position.errors.join(", ")}`);
      return {
        nodeId: node.id,
        moveNumber: position.move_number,
        stones: position.stones.length,
        invariant: "readback_replay_has_no_errors",
        invariantVerified: true,
        verified: true,
        boardInvariant: "readback_replay_has_no_errors",
        replayErrorsAbsent: true
      };
    });

    report.status = "pass";
    return report;
  } catch (error) {
    report.error = errorMessage(error);
    report.status = "fail";
    return report;
  } finally {
    report.finishedAt = new Date().toISOString();
    if (reportPath) {
      try {
        await runtimeSmokeReport(reportPath, JSON.stringify(report, null, 2));
      } catch (error) {
        report.steps.push({ name: "write runtime smoke report", status: "fail", error: errorMessage(error) });
      }
    }
  }
}

async function check<T>(
  report: RuntimeSmokeReport,
  name: RuntimeSmokeCheckName,
  action: () => Promise<T>
): Promise<T> {
  try {
    const result = await action();
    const details = summarizeResult(result);
    report.checks.push({ name, status: "pass", details });
    return result;
  } catch (error) {
    report.checks.push({ name, status: "fail", error: errorMessage(error) });
    throw error;
  }
}

async function verifySgf(report: RuntimeSmokeReport, label: string, sgfText: string) {
  await step(report, `parse ${label} summary`, async () => {
    const parsed = await parseSgfSummary(sgfText);
    if (parsed.summary.move_count < 1) throw new Error(`${label} SGF must contain at least one move.`);
    return { boardSize: parsed.summary.board_size, moveCount: parsed.summary.move_count };
  });
  await step(report, `replay ${label} positions`, async () => {
    const positions = await replaySgfPositions(sgfText);
    if (positions.length < 2) throw new Error(`${label} replay returned too few positions.`);
    return { positions: positions.length, lastMove: positions.at(-1)?.move_number ?? null };
  });
  await step(report, `parse ${label} tree`, async () => {
    const tree = await parseSgfTree(sgfText);
    if (!tree?.nodes.length) throw new Error(`${label} tree is empty.`);
    return { nodes: tree.nodes.length, rootId: tree.root_id };
  });
}

async function step<T>(report: RuntimeSmokeReport, name: string, action: () => Promise<T>): Promise<T> {
  try {
    const result = await action();
    report.steps.push({ name, status: "pass", details: summarizeResult(result) });
    return result;
  } catch (error) {
    report.steps.push({ name, status: "fail", error: errorMessage(error) });
    throw error;
  }
}

function runtimeSmokeEnv(name: string): string | null {
  const value = runtimeSmokeImportMeta().env?.[name];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function normalizeOptionalString(value: string | null | undefined): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function runtimeSmokeImportMeta(): RuntimeSmokeImportMeta {
  return import.meta as RuntimeSmokeImportMeta;
}

function requireNode(tree: SgfTreeDto | null, nodeId: string | null | undefined, label: string): SgfTreeNodeDto {
  const node = tree?.nodes.find((candidate) => candidate.id === nodeId);
  if (!node) throw new Error(`Could not find ${label}.`);
  return node;
}

function findBranchNode(tree: SgfTreeDto | null): SgfTreeNodeDto {
  const preferred = tree?.nodes.find((node) => node.comment?.includes("second branch") || node.comment?.includes("runtime smoke branch"));
  const fallback = tree?.nodes.find((node) => node.color && !node.is_mainline);
  const node = preferred ?? fallback;
  if (!node) throw new Error("Could not find a branch move node.");
  return node;
}

function chooseUnusedSiblingVertex(tree: SgfTreeDto | null, parentNodeId: string): MoveVertex {
  const used = siblingVertexKeys(tree, parentNodeId);
  const candidates = candidateVertices(readBoardSize(tree));
  return candidates.find((vertex) => !used.has(vertexKey(vertex) ?? "")) ?? "pass";
}

function chooseDifferentSiblingVertex(tree: SgfTreeDto | null, nodeId: string): MoveVertex {
  const node = requireNode(tree, nodeId, "move being edited");
  const used = siblingVertexKeys(tree, node.parent_id ?? "");
  used.delete(vertexKey(node.vertex) ?? "");
  const current = vertexKey(node.vertex);
  const candidates = candidateVertices(readBoardSize(tree));
  const selected = candidates.find((vertex) => vertexKey(vertex) !== current && !used.has(vertexKey(vertex) ?? ""));
  if (!selected) throw new Error("Could not find a distinct edit vertex.");
  return selected;
}

function candidateVertices(boardSize: number): MoveVertex[] {
  const high = Math.max(boardSize - 1, 0);
  const mid = Math.floor(high / 2);
  return [
    { point: { x: 0, y: 0 } },
    { point: { x: 1, y: 0 } },
    { point: { x: 0, y: 1 } },
    { point: { x: high, y: high } },
    { point: { x: mid, y: mid } },
    "pass"
  ];
}

function siblingVertexKeys(tree: SgfTreeDto | null, parentNodeId: string): Set<string> {
  return new Set(
    tree?.nodes
      .filter((node) => node.parent_id === parentNodeId)
      .map((node) => vertexKey(node.vertex))
      .filter((key): key is string => key !== null) ?? []
  );
}

function readBoardSize(tree: SgfTreeDto | null): number {
  const root = tree?.nodes.find((node) => node.id === tree.root_id);
  const rawSize = root?.properties.find((property) => property.key === "SZ")?.values[0];
  const boardSize = rawSize ? Number(rawSize) : 19;
  return Number.isFinite(boardSize) && boardSize > 1 ? Math.floor(boardSize) : 19;
}

function vertexKey(vertex: MoveVertex | null | undefined): string | null {
  if (!vertex) return null;
  if (vertex === "pass") return "pass";
  return `${vertex.point.x},${vertex.point.y}`;
}

function assertPropertyValue(node: SgfTreeNodeDto, key: string, expectedValue: string) {
  const values = node.properties.find((property) => property.key === key)?.values ?? [];
  if (!values.includes(expectedValue)) {
    throw new Error(`${key} property does not include ${expectedValue}.`);
  }
}

function assertNonEmptyString(value: string, message: string) {
  if (!value.trim()) throw new Error(message);
}

function summarizeResult(value: unknown): Record<string, unknown> | undefined {
  if (typeof value === "string") return { bytes: value.length };
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    if ("details" in value && typeof value.details === "object" && value.details !== null) {
      return value.details as Record<string, unknown>;
    }
    if ("root_id" in value && "nodes" in value && Array.isArray((value as SgfTreeDto).nodes)) {
      const tree = value as SgfTreeDto;
      return { rootId: tree.root_id, nodes: tree.nodes.length };
    }
    return value as Record<string, unknown>;
  }
  return undefined;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
