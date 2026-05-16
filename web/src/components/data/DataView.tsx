import { useParams } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';

export function DataView() {
  const { name } = useParams<{ name: string }>();
  const { data, loading } = useApi(() => api.discoveries(name!), [name]);

  if (loading) {
    return <div className="p-8 text-text-muted font-mono text-sm">Loading data...</div>;
  }

  const discoveries = data?.discoveries ?? [];

  if (discoveries.length === 0) {
    return (
      <div className="p-8">
        <div className="text-[10px] uppercase tracking-widest text-cyber-muted mb-4 font-bold">
          // discoveries
        </div>
        <div className="text-text-muted text-sm font-mono">
          No discoveries yet. Run analysis agents to discover memory addresses.
        </div>
        <div className="mt-4 text-text-muted text-xs font-mono">
          <code className="text-cyber bg-cyber-bg px-1.5 py-0.5 rounded">
            rommer launch-agent --project {name} --agent dynamic
          </code>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="text-[10px] uppercase tracking-widest text-cyber-muted mb-4 font-bold">
        // discoveries ({discoveries.length})
      </div>
      <div className="border border-border-dim rounded overflow-hidden">
        <table className="w-full text-sm font-mono">
          <thead>
            <tr className="bg-surface-raised text-text-muted text-[10px] uppercase tracking-wider">
              <th className="text-left px-3 py-2">Label</th>
              <th className="text-left px-3 py-2">Address</th>
              <th className="text-left px-3 py-2">Type</th>
              <th className="text-left px-3 py-2">Tier</th>
              <th className="text-left px-3 py-2">Source</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-dim">
            {discoveries.map((d: Record<string, unknown>, i: number) => (
              <tr key={i} className="hover:bg-surface-overlay">
                <td className="px-3 py-2 text-text-primary">{d.label as string}</td>
                <td className="px-3 py-2 text-cyber">{d.address as string}</td>
                <td className="px-3 py-2 text-text-secondary">{d.data_type as string}</td>
                <td className="px-3 py-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    d.tier === 'golden' ? 'bg-yellow-900/30 text-yellow-400' : 'bg-surface-overlay text-text-muted'
                  }`}>
                    {d.tier as string}
                  </span>
                </td>
                <td className="px-3 py-2 text-text-muted">{d.discovered_by_node as string}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
