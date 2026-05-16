import { useState, useEffect, useCallback } from 'react';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  message: string;
}

let _addToast: ((msg: Omit<ToastMessage, 'id'>) => void) | null = null;

export function toast(type: ToastMessage['type'], message: string) {
  _addToast?.({ type, message });
}

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = useCallback((msg: Omit<ToastMessage, 'id'>) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { ...msg, id }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  useEffect(() => {
    _addToast = addToast;
    return () => { _addToast = null; };
  }, [addToast]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`px-4 py-3 rounded border font-mono text-sm max-w-sm shadow-lg ${
            t.type === 'success' ? 'bg-surface-raised border-cyber text-cyber' :
            t.type === 'error' ? 'bg-surface-raised border-red-800 text-red-400' :
            'bg-surface-raised border-border text-text-primary'
          }`}
        >
          {t.message}
        </div>
      ))}
    </div>
  );
}
