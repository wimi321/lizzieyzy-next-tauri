import { useEffect, useMemo, useState } from "react";
import type { SgfPropertyUpdate } from "../api/backend";
import type { SgfTreeNodeDto } from "../domain/types";

type Props = {
  selectedNode: SgfTreeNodeDto | null;
  disabled?: boolean;
  isSaving?: boolean;
  error?: string | null;
  onSaveAnnotations?: (nodeId: string, updates: SgfPropertyUpdate[]) => void;
};

type AnnotationField = {
  key: string;
  label: string;
  placeholder: string;
};

const annotationFields: AnnotationField[] = [
  { key: "TR", label: "Triangles", placeholder: "dd, pp" },
  { key: "SQ", label: "Squares", placeholder: "dc, qc" },
  { key: "CR", label: "Circles", placeholder: "jj" },
  { key: "MA", label: "Marks", placeholder: "pq" },
  { key: "SL", label: "Selected", placeholder: "cc, qq" },
  { key: "LB", label: "Labels", placeholder: "dd:A, pp:B" },
  { key: "AR", label: "Arrows", placeholder: "dd:pp" },
  { key: "LN", label: "Lines", placeholder: "dc:qc" }
];

export function SgfAnnotationPanel({ selectedNode, disabled = false, isSaving = false, error = null, onSaveAnnotations }: Props) {
  const selectedDraft = useMemo(() => buildAnnotationDraft(selectedNode), [selectedNode]);
  const [draft, setDraft] = useState<Record<string, string[]>>(selectedDraft);
  const [addDraft, setAddDraft] = useState<Record<string, string>>({});
  const updates = useMemo(() => buildAnnotationUpdates(selectedNode, draft), [selectedNode, draft]);

  useEffect(() => {
    setDraft(selectedDraft);
    setAddDraft({});
  }, [selectedDraft, selectedNode?.id]);

  function handleTextChange(key: string, value: string) {
    setDraft((current) => ({ ...current, [key]: parseAnnotationValues(value) }));
  }

  function handleAddValue(key: string) {
    const values = parseAnnotationValues(addDraft[key] ?? "");
    if (values.length === 0) return;
    setDraft((current) => ({ ...current, [key]: mergeAnnotationValues(current[key] ?? [], values) }));
    setAddDraft((current) => ({ ...current, [key]: "" }));
  }

  function handleRemoveValue(key: string, value: string) {
    setDraft((current) => ({ ...current, [key]: (current[key] ?? []).filter((item) => item !== value) }));
  }

  function handleClear(key: string) {
    setDraft((current) => ({ ...current, [key]: [] }));
  }

  function handleSave() {
    if (!selectedNode || updates.length === 0) return;
    onSaveAnnotations?.(selectedNode.id, updates);
  }

  return (
    <section className="sgf-annotation-editor" aria-label="SGF node annotations" data-testid="sgf-annotation-editor">
      <div className="sgf-properties-header">
        <div>
          <h3>Annotations</h3>
          <span>TR SQ CR MA SL LB AR LN markup on the selected node</span>
        </div>
      </div>
      <div className="sgf-property-grid">
        {annotationFields.map((field) => {
          const values = draft[field.key] ?? [];
          const textValue = values.join("\n");
          return (
            <div key={field.key} className="sgf-property-field">
              <span>{field.key} {field.label}</span>
                <textarea
                  data-testid={`sgf-annotation-${field.key.toLowerCase()}-values`}
                  value={textValue}
                onChange={(event) => handleTextChange(field.key, event.target.value)}
                disabled={!selectedNode || disabled || isSaving || !onSaveAnnotations}
                spellCheck={false}
                aria-label={`${field.key} annotation values`}
                placeholder={field.placeholder}
              />
              <span className="sgf-comment-note">
                {values.length > 0 ? values.join(", ") : "No values"}
              </span>
              <div className="sgf-node-actions" aria-label={`${field.key} annotation value controls`}>
                  <input
                    data-testid={`sgf-annotation-${field.key.toLowerCase()}-add-input`}
                    value={addDraft[field.key] ?? ""}
                  onChange={(event) => setAddDraft((current) => ({ ...current, [field.key]: event.target.value }))}
                  disabled={!selectedNode || disabled || isSaving || !onSaveAnnotations}
                  spellCheck={false}
                  aria-label={`Add ${field.key} annotation value`}
                  placeholder={field.placeholder}
                />
                  <button type="button" data-testid={`sgf-annotation-${field.key.toLowerCase()}-add`} onClick={() => handleAddValue(field.key)} disabled={!selectedNode || disabled || isSaving || !onSaveAnnotations}>
                  Add
                </button>
                  <button type="button" data-testid={`sgf-annotation-${field.key.toLowerCase()}-clear`} onClick={() => handleClear(field.key)} disabled={!selectedNode || disabled || isSaving || !onSaveAnnotations || values.length === 0}>
                  Clear
                </button>
              </div>
              {values.length > 0 && (
                <div className="sgf-node-actions" aria-label={`${field.key} existing annotation values`}>
                  {values.map((value) => (
                      <button key={value} type="button" data-testid={`sgf-annotation-${field.key.toLowerCase()}-remove`} onClick={() => handleRemoveValue(field.key, value)} disabled={!selectedNode || disabled || isSaving || !onSaveAnnotations}>
                      Remove {value}
                    </button>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="sgf-properties-note">Values accept comma or line separated SGF coordinates. LB/AR/LN use SGF colon syntax. Empty fields delete that annotation property.</p>
      {error ? <p className="sgf-comment-note" role="alert">{error}</p> : null}
      <button type="button" data-testid="sgf-annotations-save" onClick={handleSave} disabled={!selectedNode || disabled || isSaving || !onSaveAnnotations || updates.length === 0}>
        {isSaving ? "Saving..." : "Save Annotations"}
      </button>
    </section>
  );
}

function buildAnnotationDraft(node: SgfTreeNodeDto | null): Record<string, string[]> {
  const draft: Record<string, string[]> = {};
  for (const field of annotationFields) draft[field.key] = node ? propertyValues(node, field.key) : [];
  return draft;
}

function buildAnnotationUpdates(node: SgfTreeNodeDto | null, draft: Record<string, string[]>): SgfPropertyUpdate[] {
  if (!node) return [];
  return annotationFields.flatMap((field) => {
    const previous = propertyValues(node, field.key);
    const next = draft[field.key] ?? [];
    return areValuesEqual(previous, next) ? [] : [{ key: field.key, values: next }];
  });
}

function propertyValues(node: SgfTreeNodeDto, key: string): string[] {
  return node.properties.find((property) => property.key.toUpperCase() === key)?.values ?? [];
}

function parseAnnotationValues(value: string): string[] {
  return value
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function mergeAnnotationValues(current: string[], added: string[]): string[] {
  return Array.from(new Set([...current, ...added]));
}

function areValuesEqual(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}
