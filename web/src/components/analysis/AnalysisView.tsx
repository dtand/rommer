import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';

interface FuncAnalysis {
  id: number;
  address: string;
  original_name: string;
  name: string;
  system: string;
  description: string;
  confidence: number;
  completeness: number;
  level: number;
  notes: string;
  code?: string;
  filename?: string;
}

interface AnalysisStats {
  total_functions: number;
  analyzed: number;
  percent: number;
  by_system: { system: string; cnt: number; avg_conf: number }[];
  by_level: { level: number; cnt: number }[];
}

export function AnalysisView() {
  const { name } = useParams<{ name: string }>();
  const { data: stats } = useApi(() => api.analysisStats(name!), [name]);
  const [selectedAddr, setSelectedAddr] = useState<string | null>(null);
  const [filterSystem, setFilterSystem] = useState<string | undefined>();
  const [filterLevel, setFilterLevel] = useState<number | undefined>();
  const [search, setSearch] = useState('');

  const { data: funcsData, loading } = useApi(
    () => api.analysisFunctions(name!, { system: filterSystem, level: filterLevel, search: search || undefined, limit: 100 }),
    [name, filterSystem, filterLevel, search],
  );
  const { data: detail } = useApi(
    () => selectedAddr ? api.analysisFunction(name!, selectedAddr) : Promise.resolve(null),
    [name, selectedAddr],
  );

  const s = (stats as AnalysisStats) || { total_functions: 0, analyzed: 0, percent: 0, by_system: [], by_level: [] };
  const funcs: FuncAnalysis[] = (funcsData as { functions: FuncAnalysis[] })?.functions ?? [];
  const selected = detail as FuncAnalysis | null;

  return (
    <div className="flex h-full">
      {/* Left: function list */}
      <div className="w-96 border-r border-border-dim overflow-y-auto h-full shrink-0">
        {/* Stats header */}
        <div className="p-4 border-b border-border-dim sticky top-0 bg-surface-raised z-10">
          <div className="text-[10px] uppercase tracking-widest text-cyber-muted font-bold mb-2">
            // analysis ({s.analyzed} / {s.total_functions} — {s.percent}%)
          </div>
          <div className="h-1.5 bg-surface-overlay rounded-full overflow-hidden mb-3">
            <div className="h-full bg-cyber transition-all" style={{ width: `${s.percent}%` }} />
          </div>

          {/* Search */}
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search name or address..."
            className="w-full bg-surface border border-border text-text-primary text-xs px-2 py-1.5 rounded font-mono focus:outline-none focus:border-cyber mb-2"
          />

          {/* Filters */}
          <div className="flex gap-1 flex-wrap">
            <FilterChip label="All" active={!filterSystem && filterLevel === undefined} onClick={() => { setFilterSystem(undefined); setFilterLevel(undefined); }} />
            {s.by_system.slice(0, 6).map((sys) => (
              <FilterChip
                key={sys.system}
                label={`${sys.system} (${sys.cnt})`}
                active={filterSystem === sys.system}
                onClick={() => setFilterSystem(filterSystem === sys.system ? undefined : sys.system)}
              />
            ))}
          </div>
        </div>

        {/* Function list */}
        {loading ? (
          <div className="p-4 text-text-muted text-sm font-mono">Loading...</div>
        ) : funcs.length === 0 ? (
          <div className="p-4 text-text-muted text-sm font-mono text-center mt-4">
            {s.analyzed === 0 ? 'No functions analyzed yet. Run: rommer static-analyze' : 'No matching functions.'}
          </div>
        ) : (
          <div className="divide-y divide-border-dim">
            {funcs.map((f) => (
              <button
                key={f.address}
                onClick={() => setSelectedAddr(f.address)}
                className={`w-full text-left px-4 py-2.5 transition-colors ${
                  selectedAddr === f.address ? 'bg-cyber-bg border-r-2 border-cyber' : 'hover:bg-surface-overlay'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-mono text-text-primary truncate">
                    {f.name || f.original_name || f.address}
                  </span>
                  <ConfidenceDot confidence={f.confidence} />
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-[10px] text-text-muted font-mono">{f.address}</span>
                  {f.system && (
                    <span className="text-[10px] px-1 py-0 bg-cyber-bg text-cyber-dim rounded">{f.system}</span>
                  )}
                  <span className="text-[10px] text-text-muted">L{f.level ?? '?'}</span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Center: function detail */}
      <div className="flex-1 overflow-y-auto h-full">
        {selected ? (
          <FunctionDetail func={selected} />
        ) : (
          <div className="flex items-center justify-center h-full text-text-muted font-mono text-sm">
            Select a function to view analysis
          </div>
        )}
      </div>

      {/* Right: summary */}
      <div className="w-64 border-l border-border-dim overflow-y-auto h-full shrink-0 p-4">
        <div className="text-[10px] uppercase tracking-widest text-cyber-muted font-bold mb-3">// systems</div>
        {s.by_system.map((sys) => (
          <div key={sys.system} className="mb-2">
            <div className="flex justify-between text-xs font-mono">
              <span className="text-text-primary">{sys.system}</span>
              <span className="text-text-muted">{sys.cnt}</span>
            </div>
            <div className="h-1 bg-surface-overlay rounded-full mt-0.5">
              <div className="h-full bg-cyber-dim rounded-full" style={{ width: `${Math.min(100, sys.cnt / Math.max(s.analyzed, 1) * 100)}%` }} />
            </div>
          </div>
        ))}

        <div className="text-[10px] uppercase tracking-widest text-cyber-muted font-bold mb-3 mt-6">// levels</div>
        {s.by_level.map((lv) => (
          <div key={lv.level} className="flex justify-between text-xs font-mono mb-1">
            <span className="text-text-muted">Level {lv.level}</span>
            <span className="text-text-primary">{lv.cnt}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function FunctionDetail({ func }: { func: FuncAnalysis }) {
  return (
    <div className="p-6">
      <div className="mb-4">
        <div className="text-[10px] uppercase tracking-widest text-cyber-muted mb-1 font-bold">
          // {func.address}
        </div>
        <h2 className="text-cyber text-lg font-mono font-bold">{func.name || func.original_name}</h2>
        <div className="flex items-center gap-3 mt-1">
          {func.system && <span className="text-xs px-2 py-0.5 bg-cyber-bg text-cyber-dim rounded font-mono">{func.system}</span>}
          <span className="text-xs text-text-muted font-mono">Level {func.level ?? '?'}</span>
          <span className="text-xs text-text-muted font-mono">Conf: {(func.confidence * 100).toFixed(0)}%</span>
          <span className="text-xs text-text-muted font-mono">Comp: {(func.completeness * 100).toFixed(0)}%</span>
        </div>
      </div>

      {func.description && (
        <div className="border border-border-dim rounded p-3 bg-surface-raised mb-3">
          <div className="text-[10px] uppercase tracking-widest text-text-muted mb-1 font-bold">Description</div>
          <p className="text-text-primary text-sm">{func.description}</p>
        </div>
      )}

      {func.notes && (
        <div className="border border-border-dim rounded p-3 bg-surface-raised mb-3">
          <div className="text-[10px] uppercase tracking-widest text-text-muted mb-1 font-bold">Notes</div>
          <p className="text-text-secondary text-sm">{func.notes}</p>
        </div>
      )}

      {func.code && (
        <div className="border border-border-dim rounded bg-surface-raised mb-3">
          <div className="px-3 py-2 border-b border-border-dim">
            <span className="text-[10px] uppercase tracking-widest text-text-muted font-bold">
              {func.filename || 'code'}
            </span>
          </div>
          <pre className="p-3 text-xs font-mono text-text-primary overflow-x-auto max-h-96 overflow-y-auto">
            {func.code}
          </pre>
        </div>
      )}
    </div>
  );
}

function ConfidenceDot({ confidence }: { confidence: number }) {
  const color = confidence >= 0.8 ? 'bg-cyber' : confidence >= 0.5 ? 'bg-yellow-400' : confidence > 0 ? 'bg-orange-400' : 'bg-text-muted';
  return <span className={`inline-block w-2 h-2 rounded-full ${color}`} />;
}

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`text-[10px] px-1.5 py-0.5 rounded font-mono transition-colors ${
        active ? 'bg-cyber-bg text-cyber border border-cyber' : 'border border-border text-text-muted hover:text-cyber'
      }`}
    >
      {label}
    </button>
  );
}
