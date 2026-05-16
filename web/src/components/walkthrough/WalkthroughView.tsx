import { useParams } from 'react-router-dom';
import { useApi } from '../../hooks/useApi';
import { api } from '../../api/client';

export function WalkthroughView() {
  const { name } = useParams<{ name: string }>();
  const { data, loading } = useApi(() => api.sections(name!), [name]);

  if (loading) {
    return <div className="p-8 text-text-muted font-mono text-sm">Loading sections...</div>;
  }

  const sections = data?.sections ?? [];

  if (sections.length === 0) {
    return (
      <div className="p-8">
        <div className="text-[10px] uppercase tracking-widest text-cyber-muted mb-4 font-bold">
          // walkthrough sections
        </div>
        <div className="text-text-muted text-sm font-mono">
          No sections found. Run build-graph to parse the walkthrough.
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 h-full overflow-y-auto">
      <div className="text-[10px] uppercase tracking-widest text-cyber-muted mb-4 font-bold">
        // walkthrough sections ({sections.length})
      </div>
      <div className="space-y-2">
        {sections.map((section: Record<string, unknown>) => (
          <div
            key={section.section_id as string}
            className="border border-border-dim rounded p-3 bg-surface-raised hover:border-cyber-muted transition-colors"
          >
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-mono text-text-primary">{section.title as string}</div>
                <div className="text-xs text-text-muted mt-0.5">{section.section_id as string}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[10px] px-1.5 py-0.5 bg-surface-overlay text-text-secondary rounded uppercase">
                  {section.type as string}
                </span>
                {section.line_start != null && (
                  <span className="text-[10px] text-text-muted font-mono">
                    L{section.line_start as number}-{section.line_end as number}
                  </span>
                )}
              </div>
            </div>
            {section.description && (
              <div className="text-xs text-text-secondary mt-1.5">{section.description as string}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
