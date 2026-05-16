import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/client';

type Status = 'idle' | 'uploading' | 'classifying' | 'picking_walkthrough' | 'building_schema' | 'done' | 'error';

interface Walkthrough {
  filename: string;
  size: number;
}

export function UploadView() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [platform, setPlatform] = useState('gba');
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [walkthroughs, setWalkthroughs] = useState<Walkthrough[]>([]);
  const [schemaProgress, setSchemaProgress] = useState('');

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped && dropped.name.endsWith('.zip')) {
      setFile(dropped);
      if (!name) {
        setName(dropped.name.replace('.zip', '').replace(/[^a-z0-9-]/gi, '-').toLowerCase());
      }
    }
  }, [name]);

  const handleSubmit = async () => {
    if (!file || !name) return;
    setStatus('classifying');
    setError(null);

    try {
      const result = await api.initProject(name, platform, file);
      if ('error' in result) {
        setError(result.error as string);
        setStatus('error');
        return;
      }

      const wts = (result as { walkthroughs?: Walkthrough[] }).walkthroughs || [];
      if (wts.length > 1) {
        setWalkthroughs(wts);
        setStatus('picking_walkthrough');
      } else {
        // Auto-select single walkthrough and start pipeline
        await startPipeline(wts[0]?.filename || null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      setStatus('error');
    }
  };

  const startPipeline = async (walkthrough: string | null) => {
    setStatus('building_schema');
    setSchemaProgress('Running Pass 1: Structure Detection...');

    try {
      const result = await api.startPipeline(name, walkthrough);
      if ('error' in result) {
        setError(result.error as string);
        setStatus('error');
        return;
      }
      setStatus('done');
      setTimeout(() => navigate(`/project/${name}/jobs`), 1000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Pipeline failed');
      setStatus('error');
    }
  };

  // Walkthrough picker
  if (status === 'picking_walkthrough') {
    return (
      <div className="h-full flex items-center justify-center bg-surface">
        <div className="w-full max-w-md px-8">
          <h2 className="text-cyber text-lg font-mono font-bold mb-2 text-center">Select Primary Walkthrough</h2>
          <p className="text-text-muted text-sm text-center mb-6">
            Multiple walkthroughs detected. Pick the main one for graph generation.
          </p>
          <div className="space-y-2">
            {walkthroughs.map((wt) => (
              <button
                key={wt.filename}
                onClick={() => startPipeline(wt.filename)}
                className="w-full text-left px-4 py-3 border border-border rounded bg-surface-raised hover:border-cyber transition-colors"
              >
                <div className="text-sm font-mono text-text-primary">{wt.filename}</div>
                <div className="text-xs text-text-muted">{(wt.size / 1024).toFixed(0)} KB</div>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  // Building schema (passes 1-3)
  if (status === 'building_schema') {
    return (
      <div className="h-full flex items-center justify-center bg-surface">
        <div className="text-center">
          <div className="mb-6">
            <div className="inline-block w-12 h-12 border-2 border-cyber border-t-transparent rounded-full animate-spin" />
          </div>
          <div className="text-cyber text-lg font-mono mb-2">Building schema...</div>
          <div className="text-text-muted text-sm">{schemaProgress}</div>
          <div className="text-text-muted text-xs mt-2">This takes 2-3 minutes</div>
        </div>
      </div>
    );
  }

  if (status === 'classifying') {
    return (
      <div className="h-full flex items-center justify-center bg-surface">
        <div className="text-center">
          <div className="mb-6">
            <div className="inline-block w-12 h-12 border-2 border-cyber border-t-transparent rounded-full animate-spin" />
          </div>
          <div className="text-cyber text-lg font-mono mb-2">Classifying files...</div>
          <div className="text-text-muted text-sm">
            AI agent is analyzing your resources and organizing them
          </div>
        </div>
      </div>
    );
  }

  if (status === 'done') {
    return (
      <div className="h-full flex items-center justify-center bg-surface">
        <div className="text-center">
          <div className="text-cyber text-4xl mb-4">&#10003;</div>
          <div className="text-cyber text-lg font-mono">Project ready</div>
          <div className="text-text-muted text-sm mt-2">Background jobs started. Redirecting...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex items-center justify-center bg-surface">
      <div className="w-full max-w-xl px-8">
        <div className="text-center mb-10">
          <h1 className="text-cyber text-2xl font-mono font-bold mb-2">New Project</h1>
          <p className="text-text-muted text-sm">
            Upload a ZIP containing your game resources (ROM, walkthroughs, maps, codes, saves)
          </p>
        </div>

        {/* Drop zone */}
        <div
          className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors mb-6 ${
            dragOver ? 'border-cyber bg-cyber-bg'
              : file ? 'border-cyber-muted bg-cyber-bg/50'
              : 'border-border hover:border-cyber-muted'
          }`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => {
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = '.zip';
            input.onchange = (e) => {
              const f = (e.target as HTMLInputElement).files?.[0];
              if (f) {
                setFile(f);
                if (!name) setName(f.name.replace('.zip', '').replace(/[^a-z0-9-]/gi, '-').toLowerCase());
              }
            };
            input.click();
          }}
        >
          {file ? (
            <div>
              <div className="text-cyber font-mono text-sm mb-1">{file.name}</div>
              <div className="text-text-muted text-xs">{(file.size / 1024 / 1024).toFixed(1)} MB</div>
            </div>
          ) : (
            <div>
              <div className="text-text-muted text-sm mb-1">Drop ZIP here or click to browse</div>
              <div className="text-text-muted text-xs">.zip files only</div>
            </div>
          )}
        </div>

        {/* Project name */}
        <div className="mb-4">
          <label className="block text-[10px] uppercase tracking-widest text-text-muted mb-1 font-bold">
            Project Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value.replace(/[^a-z0-9-]/gi, '-').toLowerCase())}
            placeholder="my-game-project"
            className="w-full bg-surface-raised border border-border text-text-primary text-sm px-3 py-2 rounded font-mono focus:outline-none focus:border-cyber"
          />
        </div>

        {/* Platform */}
        <div className="mb-6">
          <label className="block text-[10px] uppercase tracking-widest text-text-muted mb-1 font-bold">
            Platform
          </label>
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value)}
            className="w-full bg-surface-raised border border-border text-text-primary text-sm px-3 py-2 rounded font-mono focus:outline-none focus:border-cyber"
          >
            <option value="gba">Game Boy Advance</option>
            <option value="gb">Game Boy</option>
            <option value="nes">NES</option>
            <option value="snes">SNES</option>
          </select>
        </div>

        {error && (
          <div className="mb-4 p-3 border border-red-800 bg-red-900/20 rounded text-red-400 text-sm font-mono">
            {error}
          </div>
        )}

        <button
          onClick={handleSubmit}
          disabled={!file || !name || status === 'uploading'}
          className="w-full py-3 bg-cyber/10 border border-cyber text-cyber font-mono text-sm rounded hover:bg-cyber/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Create Project
        </button>
      </div>
    </div>
  );
}
