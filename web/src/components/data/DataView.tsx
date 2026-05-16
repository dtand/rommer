import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';

interface FieldDef {
  offset: number;
  name: string;
  type: string;
  notes?: string;
  values?: Record<string, string>;
}

interface EntryDef {
  index: number;
  label: string;
}

interface Metadata {
  kind?: string;
  stride?: number;
  count?: number;
  fields?: FieldDef[];
  entries?: EntryDef[];
  bits?: { position: number; name: string }[];
  values?: Record<string, string>;
  [key: string]: unknown;
}

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
  metadata: Metadata | null;
}

export function DataView() {
  const { name } = useParams<{ name: string }>();
  const [filterTier, setFilterTier] = useState<string | undefined>(undefined);
  const { data, loading } = useApi(() => api.discoveries(name!, filterTier), [name, filterTier]);
  const [localTiers, setLocalTiers] = useState<Record<number, string>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);

  if (loading) {
    return <div className="p-8 text-text-muted font-mono text-sm">Loading discoveries...</div>;
  }

  const discoveries: Discovery[] = (data?.discoveries as Discovery[]) ?? [];
  const displayDiscoveries = discoveries.map(d => ({
    ...d,
    tier: localTiers[d.id] || d.tier,
  }));

  const goldenCount = displayDiscoveries.filter(d => d.tier === 'golden').length;
  const scratchCount = displayDiscoveries.filter(d => d.tier === 'scratch').length;
  const selected = displayDiscoveries.find(d => d.id === selectedId) || null;

  const toggleTier = async (e: React.MouseEvent, d: Discovery) => {
    e.stopPropagation();
    const newTier = d.tier === 'golden' ? 'scratch' : 'golden';
    setLocalTiers(prev => ({ ...prev, [d.id]: newTier }));
    await api.updateDiscoveryTier(name!, d.id, newTier);
  };

  if (discoveries.length === 0 && !filterTier) {
    return (
      <div className="p-8">
        <div className="text-[10px] uppercase tracking-widest text-cyber-muted mb-4 font-bold">// discoveries</div>
        <div className="text-text-muted text-sm font-mono">
          No discoveries yet. Run knowledge analysis or dynamic agents.
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* Discovery list */}
      <div className="w-[480px] border-r border-border-dim overflow-y-auto h-full shrink-0">
        <div className="p-4 border-b border-border-dim sticky top-0 bg-surface-raised z-10">
          <div className="flex items-center justify-between">
            <div className="text-[10px] uppercase tracking-widest text-cyber-muted font-bold">
              // discoveries ({discoveries.length})
            </div>
            <div className="flex gap-1">
              <FilterButton label="All" active={!filterTier} onClick={() => setFilterTier(undefined)} />
              <FilterButton label={`${goldenCount} ★`} active={filterTier === 'golden'} onClick={() => setFilterTier('golden')} />
              <FilterButton label={`${scratchCount} ☆`} active={filterTier === 'scratch'} onClick={() => setFilterTier('scratch')} />
            </div>
          </div>
        </div>

        <div className="divide-y divide-border-dim">
          {displayDiscoveries.map((d) => (
            <button
              key={d.id}
              onClick={() => setSelectedId(d.id)}
              className={`w-full text-left px-4 py-2.5 transition-colors ${
                selectedId === d.id
                  ? 'bg-cyber-bg border-r-2 border-cyber'
                  : 'hover:bg-surface-overlay'
              }`}
            >
              <div className="flex items-center gap-2">
                <button
                  onClick={(e) => toggleTier(e, d)}
                  className="shrink-0"
                  title={d.tier === 'golden' ? 'Demote to scratch' : 'Promote to golden'}
                >
                  {d.tier === 'golden' ? (
                    <span className="text-yellow-400 text-xs">&#9733;</span>
                  ) : (
                    <span className="text-text-muted text-xs hover:text-yellow-400/50">&#9734;</span>
                  )}
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-mono text-text-primary truncate">{d.label}</span>
                    <span className="text-cyber text-xs font-mono shrink-0 ml-2">{d.address}</span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[10px] text-text-muted font-mono">{d.data_type}</span>
                    {d.metadata && (
                      <span className="text-[10px] px-1 py-0 bg-cyber-bg text-cyber-dim rounded">
                        {d.metadata.kind || 'struct'}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-1 overflow-y-auto h-full">
        {selected ? (
          <DiscoveryDetail discovery={selected} />
        ) : (
          <div className="flex items-center justify-center h-full text-text-muted font-mono text-sm">
            Select a discovery to view details
          </div>
        )}
      </div>
    </div>
  );
}

function DiscoveryDetail({ discovery: d }: { discovery: Discovery }) {
  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <span className={d.tier === 'golden' ? 'text-yellow-400' : 'text-text-muted'}>
            {d.tier === 'golden' ? '★' : '☆'}
          </span>
          <span className="text-[10px] uppercase tracking-widest text-cyber-muted font-bold">
            // {d.tier}
          </span>
        </div>
        <h2 className="text-cyber text-lg font-mono font-bold">{d.label}</h2>
        <div className="text-text-muted text-xs font-mono mt-1">
          {d.address} &middot; {d.data_type} &middot; {d.confidence}
        </div>
      </div>

      {/* Notes */}
      {d.notes && (
        <Section label="Notes">
          <p className="text-text-primary text-sm">{d.notes}</p>
        </Section>
      )}

      {/* Source */}
      <Section label="Source">
        <span className="text-text-secondary text-sm font-mono">{d.source || d.discovered_by_node || 'unknown'}</span>
      </Section>

      {/* Metadata — struct/array details */}
      {d.metadata && <MetadataView metadata={d.metadata} baseAddress={d.address} />}

      {/* Raw metadata fallback */}
      {d.metadata && !d.metadata.fields && !d.metadata.entries && !d.metadata.bits && !d.metadata.values && (
        <Section label="Raw Metadata">
          <pre className="text-xs text-text-secondary overflow-x-auto">{JSON.stringify(d.metadata, null, 2)}</pre>
        </Section>
      )}
    </div>
  );
}

function MetadataView({ metadata: m, baseAddress }: { metadata: Metadata; baseAddress: string }) {
  const baseAddr = parseInt(baseAddress, 16);

  return (
    <>
      {/* Kind + dimensions */}
      {(m.kind || m.stride || m.count) && (
        <Section label="Structure">
          <div className="grid grid-cols-3 gap-4 text-sm font-mono">
            {m.kind && <Field label="Kind" value={m.kind} />}
            {m.stride && <Field label="Stride" value={`${m.stride} bytes (0x${m.stride.toString(16)})`} />}
            {m.count && <Field label="Count" value={String(m.count)} />}
          </div>
        </Section>
      )}

      {/* Fields table */}
      {m.fields && m.fields.length > 0 && (
        <Section label={`Fields (${m.fields.length})`}>
          <div className="border border-border-dim rounded overflow-hidden">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="bg-surface-overlay text-text-muted text-[10px] uppercase">
                  <th className="text-left px-2 py-1.5">Offset</th>
                  <th className="text-left px-2 py-1.5">Address</th>
                  <th className="text-left px-2 py-1.5">Name</th>
                  <th className="text-left px-2 py-1.5">Type</th>
                  <th className="text-left px-2 py-1.5">Notes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-dim">
                {m.fields.map((f, i) => (
                  <tr key={i} className="hover:bg-surface-overlay">
                    <td className="px-2 py-1.5 text-text-muted">+0x{f.offset.toString(16).toUpperCase()}</td>
                    <td className="px-2 py-1.5 text-cyber">
                      {isNaN(baseAddr) ? '?' : `0x${(baseAddr + f.offset).toString(16).padStart(8, '0').toUpperCase()}`}
                    </td>
                    <td className="px-2 py-1.5 text-text-primary">{f.name}</td>
                    <td className="px-2 py-1.5 text-text-secondary">{f.type}</td>
                    <td className="px-2 py-1.5 text-text-muted">
                      {f.notes || ''}
                      {f.values && (
                        <span className="ml-1 text-cyber-dim">
                          {Object.entries(f.values).map(([k, v]) => `${k}=${v}`).join(', ')}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {/* Array entries */}
      {m.entries && m.entries.length > 0 && (
        <Section label={`Entries (${m.entries.length})`}>
          <div className="border border-border-dim rounded overflow-hidden max-h-64 overflow-y-auto">
            <table className="w-full text-xs font-mono">
              <thead className="sticky top-0">
                <tr className="bg-surface-overlay text-text-muted text-[10px] uppercase">
                  <th className="text-left px-2 py-1.5">Index</th>
                  <th className="text-left px-2 py-1.5">Address</th>
                  <th className="text-left px-2 py-1.5">Label</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-dim">
                {m.entries.map((e, i) => (
                  <tr key={i} className="hover:bg-surface-overlay">
                    <td className="px-2 py-1.5 text-text-muted">[{e.index}]</td>
                    <td className="px-2 py-1.5 text-cyber">
                      {!isNaN(baseAddr) && m.stride
                        ? `0x${(baseAddr + e.index * m.stride).toString(16).padStart(8, '0').toUpperCase()}`
                        : '?'}
                    </td>
                    <td className="px-2 py-1.5 text-text-primary">{e.label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {/* Enum values */}
      {m.values && !m.fields && (
        <Section label="Values">
          <div className="grid grid-cols-2 gap-1 text-xs font-mono">
            {Object.entries(m.values).map(([k, v]) => (
              <div key={k}>
                <span className="text-cyber">{k}</span>
                <span className="text-text-muted"> = </span>
                <span className="text-text-primary">{v}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Bitfield */}
      {m.bits && (
        <Section label="Bits">
          <div className="space-y-1 text-xs font-mono">
            {m.bits.map((b, i) => (
              <div key={i}>
                <span className="text-cyber">bit {b.position}</span>
                <span className="text-text-muted"> = </span>
                <span className="text-text-primary">{b.name}</span>
              </div>
            ))}
          </div>
        </Section>
      )}
    </>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="border border-border-dim rounded p-3 bg-surface-raised mb-3">
      <div className="text-[10px] uppercase tracking-widest text-text-muted mb-2 font-bold">{label}</div>
      {children}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-text-muted">{label}: </span>
      <span className="text-text-primary">{value}</span>
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
