import { Background, type Edge, Handle, type Node, Position, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

import { EXTRACTION_NODE_BY_DOC_TYPE, EXTRACTION_NODES, type GraphNodeName } from "../api/types";

interface GraphViewProps {
  currentNode: GraphNodeName | null;
  completedNodes: GraphNodeName[];
  /** Once known, dims every extraction branch except the one matching this
   * classified doc_type. */
  docType: string | null;
}

interface NodeData extends Record<string, unknown> {
  label: string;
  active: boolean;
  done: boolean;
  skipped: boolean;
}

function StepNode({ data }: { data: NodeData }) {
  const base =
    "rounded-lg border-2 px-3 py-2 text-sm font-medium shadow-sm min-w-[130px] text-center transition-colors";
  const cls = data.active
    ? `${base} border-brand-500 bg-brand-500 text-white animate-pulse`
    : data.done
      ? `${base} border-brand-300 bg-brand-50 text-brand-800`
      : data.skipped
        ? `${base} border-dashed border-slate-200 bg-slate-50 text-slate-300`
        : `${base} border-slate-300 bg-white text-slate-500`;
  return (
    <div className={cls}>
      <Handle type="target" position={Position.Top} className="!bg-slate-400" />
      {data.label}
      <Handle type="source" position={Position.Bottom} className="!bg-slate-400" />
    </div>
  );
}

const nodeTypes = { step: StepNode };

const EXTRACTION_LABELS: Record<GraphNodeName, string> = {
  ingest: "Ingest",
  classify: "Classify",
  extract_w2: "W-2",
  extract_1099nec: "1099-NEC",
  extract_1099int: "1099-INT",
  extract_1099div: "1099-DIV",
  extract_k1: "K-1",
  extract_bank_statement: "Bank Stmt",
  extract_other: "Other",
  cross_check: "Cross-check",
  review: "Review",
  finalize: "Finalize",
};

const LAYOUT: Record<GraphNodeName, { x: number; y: number }> = {
  ingest: { x: 480, y: 0 },
  classify: { x: 480, y: 100 },
  extract_w2: { x: 0, y: 220 },
  extract_1099nec: { x: 160, y: 220 },
  extract_1099int: { x: 320, y: 220 },
  extract_1099div: { x: 480, y: 220 },
  extract_k1: { x: 640, y: 220 },
  extract_bank_statement: { x: 800, y: 220 },
  extract_other: { x: 960, y: 220 },
  cross_check: { x: 480, y: 340 },
  review: { x: 480, y: 440 },
  finalize: { x: 480, y: 540 },
};

const STEP_NUMBER: Record<GraphNodeName, number> = {
  ingest: 1,
  classify: 2,
  extract_w2: 3,
  extract_1099nec: 3,
  extract_1099int: 3,
  extract_1099div: 3,
  extract_k1: 3,
  extract_bank_statement: 3,
  extract_other: 3,
  cross_check: 4,
  review: 5,
  finalize: 6,
};

export function GraphView({ currentNode, completedNodes, docType }: GraphViewProps) {
  const activeExtractionNode = docType ? (EXTRACTION_NODE_BY_DOC_TYPE[docType] ?? null) : null;

  const nodes: Node[] = useMemo(
    () =>
      (Object.keys(LAYOUT) as GraphNodeName[]).map((id) => {
        const isExtraction = EXTRACTION_NODES.includes(id);
        const skipped = isExtraction && activeExtractionNode !== null && id !== activeExtractionNode;
        return {
          id,
          type: "step",
          position: LAYOUT[id],
          data: {
            label: `${STEP_NUMBER[id]}. ${EXTRACTION_LABELS[id]}`,
            active: currentNode === id,
            done: completedNodes.includes(id) && currentNode !== id,
            skipped,
          } satisfies NodeData,
          draggable: false,
        };
      }),
    [currentNode, completedNodes, activeExtractionNode],
  );

  const edgeStyle = (active: boolean) => ({
    stroke: active ? "#19766f" : "#cbd5e1",
    strokeWidth: active ? 2.5 : 1.5,
  });

  const edges: Edge[] = useMemo(() => {
    const list: Edge[] = [
      {
        id: "e-ingest-classify",
        source: "ingest",
        target: "classify",
        style: edgeStyle(completedNodes.includes("classify")),
      },
    ];
    for (const node of EXTRACTION_NODES) {
      const isActiveBranch = activeExtractionNode === null || node === activeExtractionNode;
      const highlighted = completedNodes.includes(node);
      list.push({
        id: `e-classify-${node}`,
        source: "classify",
        target: node,
        style: edgeStyle(highlighted),
        hidden: !isActiveBranch,
      });
      list.push({
        id: `e-${node}-crosscheck`,
        source: node,
        target: "cross_check",
        style: edgeStyle(highlighted),
        hidden: !isActiveBranch,
      });
    }
    list.push({
      id: "e-crosscheck-review",
      source: "cross_check",
      target: "review",
      style: edgeStyle(completedNodes.includes("review")),
    });
    list.push({
      id: "e-review-finalize",
      source: "review",
      target: "finalize",
      style: edgeStyle(completedNodes.includes("finalize")),
    });
    return list;
  }, [completedNodes, activeExtractionNode]);

  return (
    <div className="h-[560px] w-full rounded-xl border border-slate-200 bg-white">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background gap={16} color="#e2e8f0" />
      </ReactFlow>
    </div>
  );
}
