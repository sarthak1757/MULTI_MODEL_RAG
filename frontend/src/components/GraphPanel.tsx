import { GitBranch, Network, RefreshCw } from "lucide-react";
import type { GraphNode, SourceGraphResponse } from "../types/api";

interface Props {
  graph: SourceGraphResponse | null;
  loading: boolean;
  onRefresh: () => void;
}

const labels: GraphNode["label"][] = ["Event", "Observation", "Entity"];

function nodeCount(graph: SourceGraphResponse["graph"], label: GraphNode["label"]): number {
  return graph?.nodes.filter((node) => node.label === label).length ?? 0;
}

function statusCopy(graph: SourceGraphResponse | null, loading: boolean): string {
  if (loading) return "Reading graph projection…";
  if (!graph) return "Select a ready source to inspect its graph.";
  if (graph.status === "ready") return "Projection ready";
  if (graph.status === "not_synced") return "Neo4j is connected; process this source to project it.";
  if (graph.status === "skipped") return "SQLite-only mode. Configure Neo4j to enable graph traversal.";
  return graph.error ?? "Neo4j could not be reached.";
}

export default function GraphPanel({ graph, loading, onRefresh }: Props) {
  const sourceGraph = graph?.graph;
  const relationships = sourceGraph?.relationships ?? [];

  return (
    <section className="panel graphPanel">
      <div className="graphPanelHeader">
        <div>
          <span className="eyebrow">GraphRAG</span>
          <h2><Network size={16} /> Evidence graph</h2>
        </div>
        <button className="iconOnlyButton" aria-label="Refresh evidence graph" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={15} className={loading ? "spin" : undefined} />
        </button>
      </div>
      <p className={`graphStatus ${graph?.status ?? "idle"}`}>{statusCopy(graph, loading)}</p>
      {sourceGraph && (
        <>
          <div className="graphCounts" aria-label="Graph node counts">
            {labels.map((label) => <div key={label}><strong>{nodeCount(sourceGraph, label)}</strong><span>{label}s</span></div>)}
          </div>
          <div className="graphPathHeader"><GitBranch size={13} /> Relationship paths <span>{relationships.length}</span></div>
          {relationships.length ? (
            <ul className="graphPaths">
              {relationships.slice(0, 5).map((relationship) => (
                <li key={relationship.id}>
                  <code>{relationship.relation}</code>
                  <span>{relationship.source_node_id.slice(0, 8)} → {relationship.target_node_id.slice(0, 8)}</span>
                </li>
              ))}
            </ul>
          ) : <p className="muted graphEmpty">No relationships were projected for this source.</p>}
        </>
      )}
    </section>
  );
}
