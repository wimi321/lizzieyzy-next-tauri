import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { vertexLabel } from "../domain/board";
import type { MoveVertex, PlayerColor, SgfTreeDto, SgfTreeNodeDto } from "../domain/types";

type Props = {
  tree: SgfTreeDto | null;
  selectedNodeId: string | null;
  currentMove: number;
  onSelectNode: (nodeId: string) => void;
  onSaveComment: (nodeId: string, comment: string) => void;
  onDeleteNode?: (nodeId: string) => void;
  canDelete?: boolean;
  commentDraft?: string;
  onCommentDraftChange?: (comment: string) => void;
  commentReadOnly?: boolean;
  isCommentSaving?: boolean;
  isNodeDeleting?: boolean;
  commentActionLabel?: string;
  commentNote?: string;
  isLoading?: boolean;
  parseError?: string | null;
  boardSize?: number;
};

type TreeRow = {
  node: SgfTreeNodeDto;
  depth: number;
  isOrphan: boolean;
};

type DepthStyle = CSSProperties & { "--sgf-depth": number };

export function SgfTreePanel({
  tree,
  selectedNodeId,
  currentMove,
  onSelectNode,
  onSaveComment,
  onDeleteNode,
  canDelete = true,
  commentDraft,
  onCommentDraftChange,
  commentReadOnly = false,
  isCommentSaving = false,
  isNodeDeleting = false,
  commentActionLabel = "Save Comment",
  commentNote,
  isLoading = false,
  parseError = null,
  boardSize = 19
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
  const canDeleteSelectedNode = Boolean(canDelete && selectedNode && !isSelectedRoot && !isLoading && !isNodeDeleting && onDeleteNode);

  useEffect(() => {
    setLocalDraft(selectedComment);
  }, [selectedComment, selectedNodeId]);

  const handleDraftChange = (value: string) => {
    setLocalDraft(value);
    onCommentDraftChange?.(value);
  };

  const handleSaveComment = () => {
    if (!selectedNode) return;
    onSaveComment(selectedNode.id, draftValue);
  };

  const handleDeleteNode = () => {
    if (!canDeleteSelectedNode || !selectedNode || !onDeleteNode) return;
    onDeleteNode(selectedNode.id);
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
          <button type="button" className="sgf-delete-node-button" onClick={handleDeleteNode} disabled={!canDeleteSelectedNode}>
            {isNodeDeleting ? "Deleting..." : "Delete Node"}
          </button>
        </div>
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
    </aside>
  );
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
