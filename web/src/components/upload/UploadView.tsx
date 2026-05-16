import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../../api/client';

export function UploadView() {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [platform, setPlatform] = useState('gba');
  const [status, setStatus] = useState<'idle' | 'uploading' | 'classifying' | 'done' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

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

    setStatus('uploading');
    setError(null);

    try {
      setStatus('classifying');
      const result = await api.initProject(name, platform, file);
      setStatus('done');
      // Navigate to the project page after a brief delay
      setTimeout(() => navigate(`/project/${result.name}`), 800);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      setStatus('error');
    }
  };

  if (status === 'classifying') {
    return (
      <div className="h-full flex items-center justify-center bg-surface">
        <div className="text-center">
          <div className="mb-6">
            <div className="inline-block w-12 h-12 border-2 border-cyber border-t-transparent rounded-full animate-spin" />
          </div>
          <div className="text-cyber text-lg font-mono mb-2">Classifying files...</div>
          <div className="text-text-muted text-sm">
            AI agent is analyzing your resources and organizing them into the project structure
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
          <div className="text-cyber text-lg font-mono">Project created</div>
          <div className="text-text-muted text-sm mt-2">Redirecting...</div>
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
            dragOver
              ? 'border-cyber bg-cyber-bg'
              : file
              ? 'border-cyber-muted bg-cyber-bg/50'
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

        {/* Error */}
        {error && (
          <div className="mb-4 p-3 border border-red-800 bg-red-900/20 rounded text-red-400 text-sm font-mono">
            {error}
          </div>
        )}

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={!file || !name || status === 'uploading'}
          className="w-full py-3 bg-cyber/10 border border-cyber text-cyber font-mono text-sm rounded hover:bg-cyber/20 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          {status === 'uploading' ? 'Uploading...' : 'Create Project'}
        </button>
      </div>
    </div>
  );
}
