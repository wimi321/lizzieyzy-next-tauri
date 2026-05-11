import { useEffect, useMemo, useState, type CSSProperties } from "react";
import type { SgfPropertyUpdate } from "../api/backend";
import { vertexLabel } from "../domain/board";
import type { MoveVertex, PlayerColor, SgfTreeDto, SgfTreeNodeDto } from "../domain/types";

type Props = {
  tree: SgfTreeDto | null;
  selectedNodeId: string | null;
  currentMove: number;
  onSelectNode: (nodeId: string) => void;
  onSaveComment: (nodeId: string, comment: string) => void;
  onSaveProperties?: (nodeId: string, updates: SgfPropertyUpdate[]) => void;
  onDeleteNode?: (nodeId: string) => void;
  onReorderNode?: (nodeId: string, targetIndex: number) => void;
  canDelete?: boolean;
  canReorder?: boolean;
  commentDraft?: string;
  onCommentDraftChange?: (comment: string) => void;
  commentReadOnly?: boolean;
  isCommentSaving?: boolean;
  isPropertySaving?: boolean;
  isNodeDeleting?: boolean;
  isNodeReordering?: boolean;
  commentActionLabel?: string;
  commentNote?: string;
  isLoading?: boolean;
  parseError?: string | null;
  boardSize?: number;
  moveEditMode?: MoveEditMode;
  canEditSelectedMove?: boolean;
  onMoveEditModeChange?: (mode: MoveEditMode) => void;
  onEditSelectedMovePass?: () => void;
  isMoveEditing?: boolean;
};

type MoveEditMode = "append" | "edit";

type TreeRow = {
  node: SgfTreeNodeDto;
  depth: number;
  isOrphan: boolean;
};

type DepthStyle = CSSProperties & { "--sgf-depth": number };

const activeModeButtonStyle: CSSProperties = {
  borderColor: "#fb923c",
  background: "#fff7ed",
  color: "#7c2d12"
};

export function SgfTreePanel({
  tree,
  selectedNodeId,
  currentMove,
  onSelectNode,
  onSaveComment,
  onSaveProperties,
  onDeleteNode,
  onReorderNode,
  canDelete = true,
  canReorder = true,
  commentDraft,
  onCommentDraftChange,
  commentReadOnly = false,
  isCommentSaving = false,
  isPropertySaving = false,
  isNodeDeleting = false,
  isNodeReordering = false,
  commentActionLabel = "Save Comment",
  commentNote,
  isLoading = false,
  parseError = null,
  boardSize = 19,
  moveEditMode = "append",
  canEditSelectedMove = false,
  onMoveEditModeChange,
  onEditSelectedMovePass,
  isMoveEditing = false
}: Props) {
  const rows = useMemo(() => buildTreeRows(tree), [tree]);
  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return tree?.nodes.find((node) => node.id === selectedNodeId) ?? null;
  }, [selectedNodeId, tree]);
  const selectedComment = selectedNode?.comment ?? "";
  const [localDraft, setLocalDraft] = useState(selectedComment);
  const draftValue = commentDraft ?? localDraft;
  const isSelectedRoot = Boolean(selectedNode && tree?.root_id === selectedNode.id);
  const propertyFields = useMemo(() => getPropertyFields(isSelectedRoot), [isSelectedRoot]);
  const selectedPropertyDraft = useMemo(() => buildPropertyDraft(selectedNode, propertyFields), [selectedNode, propertyFields]);
  const [propertyDraft, setPropertyDraft] = useState<Record<string, string>>(selectedPropertyDraft);
  const propertyUpdates = useMemo(
    () => buildPropertyUpdates(selectedNode, propertyFields, propertyDraft),
    [selectedNode, propertyFields, propertyDraft]
  );
  const canDeleteSelectedNode = Boolean(canDelete && selectedNode && !isSelectedRoot && !isLoading && !isNodeDeleting && onDeleteNode);
  const siblingState = useMemo(() => getSiblingState(tree, selectedNode), [tree, selectedNode]);
  const canMoveSelectedNodeUp = Boolean(canReorder && onReorderNode && !isLoading && !isNodeReordering && siblingState.canMoveUp);
  const canMoveSelectedNodeDown = Boolean(canReorder && onReorderNode && !isLoading && !isNodeReordering && siblingState.canMoveDown);
  const moveEditState = getMoveEditState({ selectedNode, canEditSelectedMove });
  const canChangeMoveEditMode = Boolean(!isLoading && !isMoveEditing && onMoveEditModeChange);
  const canUseEditMode = Boolean(canChangeMoveEditMode && canEditSelectedMove);
  const canPassSelectedMove = Boolean(!isLoading && !isMoveEditing && moveEditMode === "edit" && canEditSelectedMove && onEditSelectedMovePass);

  useEffect(() => {
    setLocalDraft(selectedComment);
  }, [selectedComment, selectedNodeId]);

  useEffect(() => {
    setPropertyDraft(selectedPropertyDraft);
  }, [selectedPropertyDraft, selectedNodeId]);

  const handleDraftChange = (value: string) => {
    setLocalDraft(value);
    onCommentDraftChange?.(value);
  };

  const handlePropertyDraftChange = (key: string, value: string) => {
    setPropertyDraft((current) => ({ ...current, [key]: value }));
  };

  const handleSaveComment = () => {
    if (!selectedNode) return;
    onSaveComment(selectedNode.id, draftValue);
  };

  const handleSaveProperties = () => {
    if (!selectedNode || !onSaveProperties || propertyUpdates.length === 0) return;
    onSaveProperties(selectedNode.id, propertyUpdates);
  };

  const handleDeleteNode = () => {
    if (!canDeleteSelectedNode || !selectedNode || !onDeleteNode) return;
    onDeleteNode(selectedNode.id);
  };

  const handleMoveSelectedNode = (direction: -1 | 1) => {
    if ((direction < 0 && !canMoveSelectedNodeUp) || (direction > 0 && !canMoveSelectedNodeDown)) return;
    if (!selectedNode || !onReorderNode || siblingState.index < 0) return;
    const targetIndex = siblingState.index + direction;
    if (targetIndex < 0 || targetIndex >= siblingState.count) return;
    onReorderNode(selectedNode.id, targetIndex);
  };

  const handleMoveEditModeChange = (mode: MoveEditMode) => {
    if (!canChangeMoveEditMode) return;
    if (mode === "edit" && !canEditSelectedMove) return;
    onMoveEditModeChange?.(mode);
  };

  const handleEditSelectedMovePass = () => {
    if (!canPassSelectedMove) return;
    onEditSelectedMovePass?.();
  };

  const status = getPanelStatus({ tree, isLoading, parseError });

  return (
    <aside className="sgf-tree-panel" aria-label="SGF tree and comments">
      <header className="sgf-tree-header">
        <div>
          <h2>SGF Tree</h2>
          <span>{status ? status.label : `${rows.length.toLocaleString()} nodes`}</span>
        </div>
        {selectedNode ? <strong title={selectedNode.id}>{formatNodeMove(selectedNode, boardSize)}</strong> : <strong>No node</strong>}
      </header>

      {status ? <div className={`sgf-tree-state ${status.kind}`} role={status.kind === "sgf-tree-error" ? "alert" : "status"}>
        <strong>{status.title}</strong>
        <span>{status.message}</span>
      </div> : <ol className="sgf-tree-list">
        {rows.map(({ node, depth, isOrphan }) => {
          const isSelected = node.id === selectedNodeId;
          const isCurrentMove = node.move_number === currentMove;
          const style: DepthStyle = { "--sgf-depth": Math.min(depth, 12) };
          return (
            <li key={node.id} className={node.is_mainline ? "sgf-tree-mainline" : "sgf-tree-variation"} style={style}>
              <button
                type="button"
                className={`sgf-tree-node${isSelected ? " is-selected" : ""}${isCurrentMove ? " is-current-move" : ""}`}
                aria-current={isSelected ? "true" : undefined}
                onClick={() => onSelectNode(node.id)}
              >
                <span className="sgf-tree-rail" aria-hidden="true" />
                <span className={`sgf-tree-stone ${node.color ?? "root"}`} aria-hidden="true">{colorInitial(node.color)}</span>
                <span className="sgf-tree-move">{formatNodeMove(node, boardSize)}</span>
                <span className="sgf-tree-summary">{formatSummary(node, isOrphan)}</span>
                <span className="sgf-tree-flags" aria-hidden="true">
                  {node.is_mainline ? <span title="Mainline">M</span> : <span title={`Variation ${node.variation_index + 1}`}>V{node.variation_index + 1}</span>}
                  {isCurrentMove ? <span title="Current move">Now</span> : null}
                </span>
              </button>
            </li>
          );
        })}
      </ol>}

      <section className="sgf-comment-editor" aria-label="Node comment">
        <div className="sgf-comment-header">
          <div>
            <h3>Comment</h3>
            <span>{selectedNode ? formatNodeMove(selectedNode, boardSize) : "Select a node"}</span>
          </div>
          <div className="sgf-node-actions" aria-label="Selected node actions">
            <button
              type="button"
              className="sgf-reorder-node-button"
              onClick={() => handleMoveSelectedNode(-1)}
              disabled={!canMoveSelectedNodeUp}
              title={siblingState.help}
            >
              Move Up
            </button>
            <button
              type="button"
              className="sgf-reorder-node-button"
              onClick={() => handleMoveSelectedNode(1)}
              disabled={!canMoveSelectedNodeDown}
              title={siblingState.help}
            >
              Move Down
            </button>
            <button type="button" className="sgf-delete-node-button" onClick={handleDeleteNode} disabled={!canDeleteSelectedNode}>
              {isNodeDeleting ? "Deleting..." : "Delete Node"}
            </button>
          </div>
        </div>
        <div
          aria-label="Move edit mode"
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) auto",
            gap: 8,
            alignItems: "center",
            minWidth: 0,
            padding: "7px 8px",
            border: "1px solid #d2d8e0",
            borderRadius: 4,
            background: "#eef2f6"
          }}
        >
          <div style={{ minWidth: 0 }}>
            <h3 style={{ margin: 0, fontSize: 12 }}>Move mode</h3>
            <p className="sgf-comment-note" title={moveEditState.help}>{moveEditState.label}</p>
          </div>
          <div className="sgf-node-actions" style={{ flexWrap: "wrap", justifyContent: "flex-end" }}>
            <button
              type="button"
              className="sgf-reorder-node-button"
              onClick={() => handleMoveEditModeChange("append")}
              disabled={!canChangeMoveEditMode}
              aria-pressed={moveEditMode === "append"}
              title={canChangeMoveEditMode ? "Append mode" : "Move mode is unavailable."}
              style={moveEditMode === "append" ? activeModeButtonStyle : undefined}
            >
              Append
            </button>
            <button
              type="button"
              className="sgf-reorder-node-button"
              onClick={() => handleMoveEditModeChange("edit")}
              disabled={!canUseEditMode}
              aria-pressed={moveEditMode === "edit"}
              title={canEditSelectedMove ? "Edit selected move" : moveEditState.help}
              style={moveEditMode === "edit" ? activeModeButtonStyle : undefined}
            >
              Edit selected
            </button>
            <button
              type="button"
              className="sgf-reorder-node-button"
              onClick={handleEditSelectedMovePass}
              disabled={!canPassSelectedMove}
              title={canPassSelectedMove ? "Change selected move to pass" : "Available in Edit selected mode."}
            >
              {isMoveEditing ? "Saving..." : "Pass"}
            </button>
          </div>
        </div>
        <p className="sgf-variation-order-note">{siblingState.label}</p>
        <textarea
          value={draftValue}
          onChange={(event) => handleDraftChange(event.target.value)}
          disabled={!selectedNode || isLoading || commentReadOnly}
          spellCheck={false}
          aria-label="Selected SGF node comment"
          placeholder={selectedNode ? "No comment for this node." : "Select a node to edit its comment."}
        />
        {commentNote ? <p className="sgf-comment-note">{commentNote}</p> : null}
        <button type="button" onClick={handleSaveComment} disabled={!selectedNode || isLoading || commentReadOnly || isCommentSaving || draftValue === selectedComment}>
          {isCommentSaving ? "Saving..." : commentActionLabel}
        </button>
      </section>

      <section className="sgf-properties-editor" aria-label="SGF node properties">
        <div className="sgf-properties-header">
          <div>
            <h3>Node details</h3>
            <span>SGF properties for the selected node</span>
          </div>
        </div>
        <div className="sgf-property-grid">
          {propertyFields.map((field) => {
            const value = propertyDraft[field.key] ?? "";
            return (
              <label key={field.key} className="sgf-property-field">
                <span>{field.label}</span>
                {field.multiline ? (
                  <textarea
                    value={value}
                    onChange={(event) => handlePropertyDraftChange(field.key, event.target.value)}
                    disabled={!selectedNode || isLoading || isPropertySaving || !onSaveProperties}
                    spellCheck={false}
                    aria-label={`${field.key} SGF property values`}
                    placeholder={field.placeholder}
                  />
                ) : (
                  <input
                    value={value}
                    onChange={(event) => handlePropertyDraftChange(field.key, event.target.value)}
                    disabled={!selectedNode || isLoading || isPropertySaving || !onSaveProperties}
                    spellCheck={false}
                    aria-label={`${field.key} SGF property value`}
                    placeholder={field.placeholder}
                  />
                )}
              </label>
            );
          })}
        </div>
        <p className="sgf-properties-note">Markup fields accept comma or line separated SGF values. Empty fields delete that property.</p>
        <button
          type="button"
          onClick={handleSaveProperties}
          disabled={!selectedNode || isLoading || isPropertySaving || !onSaveProperties || propertyUpdates.length === 0}
        >
          {isPropertySaving ? "Saving..." : "Save Properties"}
        </button>
      </section>
    </aside>
  );
}

type PropertyField = {
  key: string;
  label: string;
  placeholder: string;
  multiline?: boolean;
  multiValue?: boolean;
};

const nodePropertyFields: PropertyField[] = [
  { key: "N", label: "N node name", placeholder: "Fuseki choice" },
  { key: "TR", label: "TR triangles", placeholder: "dd, pp", multiline: true, multiValue: true },
  { key: "SQ", label: "SQ squares", placeholder: "dc, qc", multiline: true, multiValue: true },
  { key: "CR", label: "CR circles", placeholder: "jj", multiline: true, multiValue: true },
  { key: "MA", label: "MA marks", placeholder: "pq", multiline: true, multiValue: true },
  { key: "LB", label: "LB labels", placeholder: "dd:A, pp:B", multiline: true, multiValue: true }
];

const rootPropertyFields: PropertyField[] = [
  { key: "PB", label: "PB black", placeholder: "Black player" },
  { key: "PW", label: "PW white", placeholder: "White player" },
  { key: "KM", label: "KM komi", placeholder: "7.5" },
  { key: "RE", label: "RE result", placeholder: "B+R" }
];

function getPropertyFields(isRoot: boolean): PropertyField[] {
  return isRoot ? [...rootPropertyFields, ...nodePropertyFields] : nodePropertyFields;
}

function getSiblingState(tree: SgfTreeDto | null, node: SgfTreeNodeDto | null) {
  const disabled = { index: -1, count: 0, canMoveUp: false, canMoveDown: false };
  if (!tree || !node) {
    return { ...disabled, label: "Select a sibling variation to reorder. Variation 1 is the mainline.", help: "Select a node with siblings to reorder variations." };
  }
  if (tree.root_id === node.id || node.parent_id === null || node.parent_id === undefined) {
    return { ...disabled, label: "Root has no sibling variations. Variation 1 is the mainline.", help: "Root cannot be reordered." };
  }
  const parent = tree.nodes.find((candidate) => candidate.id === node.parent_id) ?? null;
  const siblingIds = parent?.child_ids ?? [];
  const index = siblingIds.indexOf(node.id);
  if (!parent || index < 0) {
    return { ...disabled, label: "Sibling order is unavailable for this node.", help: "The selected node is missing from its parent's child list." };
  }
  if (siblingIds.length < 2) {
    return { ...disabled, index, count: siblingIds.length, label: "Only one sibling at this branch. Variation 1 is the mainline.", help: "At least two siblings are required to reorder." };
  }
  const positionLabel = `Variation ${index + 1} of ${siblingIds.length}`;
  return {
    index,
    count: siblingIds.length,
    canMoveUp: index > 0,
    canMoveDown: index < siblingIds.length - 1,
    label: `${positionLabel}. Variation 1 is the mainline.`,
    help: `${positionLabel}. Move among siblings; position 1 becomes the mainline.`
  };
}

function getMoveEditState({ selectedNode, canEditSelectedMove }: { selectedNode: SgfTreeNodeDto | null; canEditSelectedMove: boolean }) {
  if (!selectedNode) return { label: "Select a node", help: "Select a move node to enable Edit selected." };
  if (canEditSelectedMove) return { label: "Selected move can be edited", help: "Board clicks replace the selected move in Edit selected mode." };
  if (!selectedNode.color || !selectedNode.vertex) return { label: "Selected node has no move", help: "Only move nodes can use Edit selected." };
  return { label: "Selected move is locked", help: "This selected move cannot be edited here." };
}

function buildPropertyDraft(node: SgfTreeNodeDto | null, fields: PropertyField[]): Record<string, string> {
  const draft: Record<string, string> = {};
  for (const field of fields) {
    if (!node) {
      draft[field.key] = "";
      continue;
    }
    const values = propertyValues(node, field.key);
    draft[field.key] = field.multiValue ? values.join("\n") : values[0] ?? "";
  }
  return draft;
}

function buildPropertyUpdates(node: SgfTreeNodeDto | null, fields: PropertyField[], draft: Record<string, string>): SgfPropertyUpdate[] {
  if (!node) return [];
  return fields.flatMap((field) => {
    const previous = normalizeComparablePropertyValues(propertyValues(node, field.key), field);
    const next = parsePropertyValues(draft[field.key] ?? "", field);
    return arePropertyValuesEqual(previous, next) ? [] : [{ key: field.key, values: next }];
  });
}

function propertyValues(node: SgfTreeNodeDto, key: string): string[] {
  return node.properties.find((property) => property.key.toUpperCase() === key)?.values ?? [];
}

function parsePropertyValues(value: string, field: PropertyField): string[] {
  if (!field.multiValue) {
    const trimmed = value.trim();
    return trimmed ? [trimmed] : [];
  }
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function normalizeComparablePropertyValues(values: string[], field: PropertyField): string[] {
  return field.multiValue ? values : values.slice(0, 1);
}

function arePropertyValuesEqual(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function buildTreeRows(tree: SgfTreeDto | null): TreeRow[] {
  if (!tree) return [];
  const nodesById = new Map(tree.nodes.map((node) => [node.id, node]));
  const rows: TreeRow[] = [];
  const visited = new Set<string>();

  const visit = (nodeId: string, fallbackDepth: number, isOrphan = false) => {
    if (visited.has(nodeId)) return;
    const node = nodesById.get(nodeId);
    if (!node) return;
    visited.add(nodeId);
    rows.push({ node, depth: Number.isFinite(node.depth) ? node.depth : fallbackDepth, isOrphan });
    for (const childId of node.child_ids) visit(childId, fallbackDepth + 1);
  };

  visit(tree.root_id, 0);

  for (const node of tree.nodes) {
    if (!visited.has(node.id)) visit(node.id, node.depth, true);
  }

  return rows;
}

function getPanelStatus({ tree, isLoading, parseError }: { tree: SgfTreeDto | null; isLoading: boolean; parseError: string | null }) {
  if (isLoading) return { kind: "sgf-tree-loading", title: "Loading", label: "Loading", message: "Reading SGF tree..." };
  if (parseError) return { kind: "sgf-tree-error", title: "Parse error", label: "Error", message: parseError };
  if (!tree) return { kind: "sgf-tree-empty", title: "No tree", label: "Empty", message: "Parse or open an SGF to show the game tree." };
  if (tree.nodes.length === 0) return { kind: "sgf-tree-empty", title: "Empty tree", label: "Empty", message: "The parsed SGF tree has no nodes." };
  return null;
}

function formatNodeMove(node: SgfTreeNodeDto, boardSize: number): string {
  if (!node.vertex || !node.color) return node.move_number ? `Move ${node.move_number}` : "Root";
  return `${node.move_number ?? "-"} ${colorLabel(node.color)} ${formatVertex(node.vertex, boardSize)}`;
}

function formatSummary(node: SgfTreeNodeDto, isOrphan: boolean): string {
  const parts = [node.name?.trim(), node.comment?.trim()].filter((value): value is string => Boolean(value));
  const summary = parts.length > 0 ? parts.join(" - ") : node.properties.length > 0 ? `${node.properties.length} properties` : "No note";
  return `${isOrphan ? "Detached - " : ""}${truncate(summary, 96)}`;
}

function formatVertex(vertex: MoveVertex, boardSize: number): string {
  return vertexLabel(vertex, boardSize).toUpperCase();
}

function colorLabel(color: PlayerColor): string {
  return color === "black" ? "B" : "W";
}

function colorInitial(color?: PlayerColor | null): string {
  if (color === "black") return "B";
  if (color === "white") return "W";
  return "";
}

function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1)}...`;
}
