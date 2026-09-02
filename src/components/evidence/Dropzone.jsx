import { useCallback, useRef, useState } from 'react';
import { UploadCloud } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { ACCEPTED_EXTENSIONS, FILE_TYPES } from '@/lib/constants';
import { cn } from '@/lib/utils';

const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.map((ext) => `.${ext}`).join(',');

/**
 * Drag-and-drop upload area with a browse fallback.
 * onFiles(FileList | File[]) is called with validated files; rejects are
 * reported through onRejected(names[]).
 */
export function Dropzone({ onFiles, onRejected, disabled = false }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const validate = useCallback(
    (fileList) => {
      const accepted = [];
      const rejected = [];
      Array.from(fileList).forEach((file) => {
        const match = file.name.toLowerCase().match(/\.([a-z0-9]+)$/);
        const ext = match ? (match[1] === 'jpeg' ? 'jpg' : match[1]) : '';
        if (ACCEPTED_EXTENSIONS.includes(ext)) accepted.push(file);
        else rejected.push(file.name);
      });
      if (rejected.length) onRejected?.(rejected);
      if (accepted.length) onFiles(accepted);
    },
    [onFiles, onRejected]
  );

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Upload evidence files"
      onClick={() => !disabled && inputRef.current?.click()}
      onKeyDown={(e) => {
        if (!disabled && (e.key === 'Enter' || e.key === ' ')) inputRef.current?.click();
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!disabled) validate(e.dataTransfer.files);
      }}
      className={cn(
        'flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors',
        dragging ? 'border-teal-500 bg-teal-50/70' : 'border-slate-300 bg-slate-50/60 hover:border-teal-400 hover:bg-teal-50/40',
        disabled && 'pointer-events-none opacity-60'
      )}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT_ATTR}
        className="hidden"
        onChange={(e) => {
          if (e.target.files) validate(e.target.files);
          e.target.value = '';
        }}
      />
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-white shadow-card">
        <UploadCloud className={cn('h-5 w-5', dragging ? 'text-teal-600' : 'text-navy-400')} aria-hidden />
      </span>
      <p className="mt-3 text-sm font-medium text-navy-700">Drop evidence files here</p>
      <p className="mt-0.5 text-xs text-navy-400">or</p>
      <Button
        variant="outline"
        size="sm"
        className="mt-2"
        onClick={(e) => {
          e.stopPropagation();
          inputRef.current?.click();
        }}
        disabled={disabled}
      >
        Browse Files
      </Button>
      <p className="mt-3 text-[11px] text-navy-300">
        {Object.values(FILE_TYPES)
          .map((t) => t.label)
          .join(' · ')}
      </p>
    </div>
  );
}
