import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';

interface Discovery {
  id: number;
  label: string;
  address: string;
  data_type: string;
  tier: string;
  confidence: string;
  discovered_by_node: string | null;
  source: string | null;
  notes: string | null;
}

export function DataView() {
  const { name } = useParams<{ name: string }>();
  const [filterTier, setFilterTier] = useState<string | undefined>(undefined);
  const { data, loading } = useApi(() => api.discoveries(name!, filterTier), [name, filterTier]);
  const [localTiers, setLocalTiers] = useState<Record<number, string>>({});

  if (loading) {
    return <div className="p-8 text-text-muted font-mono text-sm">Loading discoveries...</div>;
  }

  const discoveries: Discovery[] = (data?.discoveries as Discovery[]) ?? [];

  // Apply local tier overrides (optimistic UI)
  const displayDiscoveries = discoveries.map(d => ({
    ...d,
    tier: localTiers[d.id] || d.tier,
  }));

  const goldenCount = displayDiscoveries.filter(d => d.tier === 'golden').length;
  const scratchCount = displayDiscoveries.filter(d => d.tier === 'scratch').length;

  const toggleTier = async (d: Discovery) => {
    const newTier = d.tier === 'golden' ? 'scratch' : 'golden';
    setLocalTiers(prev => ({ ...prev, [d.id]: newTier }));
    await api.updateDiscoveryTier(name!, d.id, newTier);
  };

  if (discoveries.length === 0 && !filterTier) {
    return (
      <div className="p-8">
        <div className="text-[10px] uppercase tracking-widest text-cyber-muted mb-4 font-bold">
          // discoveries
        </div>
        <div className="text-text-muted text-sm font-mono">
          No discoveries yet. Run knowledge analysis or dynamic agents to discover memory addresses.
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      {/* Header with filters */}
      <div className="flex items-center justify-between mb-4">
        <div className="text-[10px] uppercase tracking-widest text-cyber-muted font-bold">
          // discoveries ({discoveries.length})
        </div>
        <div className="flex gap-1">
          <FilterButton label="All" active={!filterTier} onClick={() => setFilterTier(undefined)} />
          <FilterButton label={`Golden (${goldenCount})`} active={filterTier === 'golden'} onClick={() => setFilterTier('golden')} />
          <FilterButton label={`Scratch (${scratchCount})`} active={filterTier === 'scratch'} onClick={() => setFilterTier('scratch')} />
        </div>
      </div>

      {/* Table */}
      <div className="border border-border-dim rounded overflow-hidden">
        <table className="w-full text-sm font-mono">
          <thead>
            <tr className="bg-surface-raised text-text-muted text-[10px] uppercase tracking-wider">
              <th className="text-left px-3 py-2 w-8">Tier</th>
              <th className="text-left px-3 py-2">Label</th>
              <th className="text-left px-3 py-2">Address</th>
              <th className="text-left px-3 py-2">Type</th>
              <th className="text-left px-3 py-2">Source</th>
              <th className="text-left px-3 py-2">Notes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border-dim">
            {displayDiscoveries.map((d) => (
              <tr key={d.id} className="hover:bg-surface-overlay group">
                <td className="px-3 py-2">
                  <button
                    onClick={() => toggleTier(d)}
                    className="cursor-pointer"
                    title={`Click to ${d.tier === 'golden' ? 'demote to scratch' : 'promote to golden'}`}
                  >
                    {d.tier === 'golden' ? (
                      <span className="text-yellow-400 text-sm">&#9733;</span>
                    ) : (
                      <span className="text-text-muted text-sm group-hover:text-yellow-400/50">&#9734;</span>
                    )}
                  </button>
                </td>
                <td className="px-3 py-2 text-text-primary">{d.label}</td>
                <td className="px-3 py-2 text-cyber">{d.address}</td>
                <td className="px-3 py-2 text-text-secondary">{d.data_type}</td>
                <td className="px-3 py-2 text-text-muted text-xs">{d.source || d.discovered_by_node || ''}</td>
                <td className="px-3 py-2 text-text-muted text-xs max-w-xs truncate">{d.notes || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function FilterButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`text-[10px] px-2 py-1 rounded font-mono transition-colors ${
        active
          ? 'bg-cyber-bg text-cyber border border-cyber'
          : 'border border-border text-text-secondary hover:border-cyber hover:text-cyber'
      }`}
    >
      {label}
    </button>
  );
}
