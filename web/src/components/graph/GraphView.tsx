import { useParams } from 'react-router-dom';
import { useState } from 'react';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';

interface GraphNode {
  node_id: string;
  name: string;
  title: string;
  description: string;
  section_ref: string;
  status: string;
  tags: string[];
  order_index: number;
}

export function GraphView() {
  const { name } = useParams<{ name: string }>();
  const { data, loading } = useApi(() => api.graphNodes(name!), [name]);
  const [selected, setSelected] = useState<GraphNode | null>(null);

  if (loading) {
    return <div className="p-8 text-text-muted font-mono text-sm">Loading graph...</div>;
  }

  const nodes: GraphNode[] = data?.nodes ?? [];

  return (
    <div className="flex h-full">
      {/* Node list */}
      <div className="w-96 border-r border-border-dim overflow-y-auto h-full">
        <div className="p-4 border-b border-border-dim sticky top-0 bg-surface-raised z-10">
          <div className="text-[10px] uppercase tracking-widest text-cyber-muted font-bold">
            // graph nodes ({nodes.length})
          </div>
        </div>
        <div className="divide-y divide-border-dim">
          {nodes.map((node) => (
            <button
              key={node.node_id}
              onClick={() => setSelected(node)}
              className={`w-full text-left px-4 py-3 transition-colors ${
                selected?.node_id === node.node_id
                  ? 'bg-cyber-bg border-r-2 border-cyber'
                  : 'hover:bg-surface-overlay'
              }`}
            >
              <div className="text-sm font-mono text-text-primary truncate">{node.title}</div>
              <div className="text-xs text-text-muted mt-0.5 truncate">{node.node_id}</div>
              {node.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1.5">
                  {node.tags.slice(0, 3).map((tag) => (
                    <span key={tag} className="text-[10px] px-1.5 py-0.5 bg-cyber-bg text-cyber-dim rounded">
                      {tag}
                    </span>
                  ))}
                  {node.tags.length > 3 && (
                    <span className="text-[10px] text-text-muted">+{node.tags.length - 3}</span>
                  )}
                </div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Node detail */}
      <div className="flex-1 overflow-y-auto h-full p-6">
        {selected ? (
          <NodeDetail node={selected} />
        ) : (
          <div className="text-text-muted font-mono text-sm mt-20 text-center">
            Select a node to view details
          </div>
        )}
      </div>
    </div>
  );
}

function NodeDetail({ node }: { node: GraphNode }) {
  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <div className="text-[10px] uppercase tracking-widest text-cyber-muted mb-1 font-bold">
          // {node.node_id}
        </div>
        <h2 className="text-cyber text-lg font-mono font-bold">{node.title}</h2>
        {node.section_ref && (
          <div className="text-text-muted text-xs mt-1 font-mono">{node.section_ref}</div>
        )}
      </div>

      <div className="space-y-4">
        <DetailSection label="Description">
          <p className="text-text-primary text-sm leading-relaxed">{node.description}</p>
        </DetailSection>

        {node.tags.length > 0 && (
          <DetailSection label="Tags">
            <div className="flex flex-wrap gap-1.5">
              {node.tags.map((tag) => (
                <span key={tag} className="text-xs px-2 py-1 bg-cyber-bg text-cyber-dim rounded font-mono">
                  {tag}
                </span>
              ))}
            </div>
          </DetailSection>
        )}

        <DetailSection label="Status">
          <span className={`text-sm font-mono ${
            node.status === 'completed' ? 'text-cyber' :
            node.status === 'in_progress' ? 'text-yellow-400' :
            'text-text-muted'
          }`}>
            {node.status}
          </span>
        </DetailSection>
      </div>
    </div>
  );
}

function DetailSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border border-border-dim rounded p-3 bg-surface-raised">
      <div className="text-[10px] uppercase tracking-widest text-text-muted mb-2 font-bold">{label}</div>
      {children}
    </div>
  );
}
