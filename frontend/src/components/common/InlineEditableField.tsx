import { useState, useRef, useEffect, useCallback, type ReactNode } from 'react';
import { Pencil, Check, X, Loader2 } from 'lucide-react';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import type { SelectOption } from '@/components/common/CreatableSelect';
import { RichTextFormField } from '@/components/common/RichTextFormField';

interface InlineEditableFieldProps {
  type: 'text' | 'date' | 'select' | 'richtext';
  value: string | null;
  onSave: (newValue: string | null) => Promise<void>;
  displayValue?: ReactNode;
  placeholder?: string;
  options?: SelectOption[];
  onCreate?: (name: string) => Promise<string | null>;
  createLabel?: string;
  clearable?: boolean;
  label?: string;
  rows?: number;
}

export function InlineEditableField({
  type,
  value,
  onSave,
  displayValue,
  placeholder = 'Klik om te bewerken...',
  options,
  onCreate,
  createLabel,
  clearable,
  label,
  rows = 3,
}: InlineEditableFieldProps) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(value ?? '');
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const selectWrapperRef = useRef<HTMLDivElement>(null);
  const editValueRef = useRef(editValue);

  useEffect(() => {
    editValueRef.current = editValue;
  }, [editValue]);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const startEdit = useCallback(() => {
    setEditValue(value ?? '');
    setEditing(true);
  }, [value]);

  const save = useCallback(async (newValue: string) => {
    const trimmed = newValue.trim();
    const saveValue = trimmed || null;
    if (saveValue === (value ?? null)) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await onSave(saveValue);
    } finally {
      setSaving(false);
      setEditing(false);
    }
  }, [value, onSave]);

  const cancel = useCallback(() => {
    setEditing(false);
    setEditValue(value ?? '');
  }, [value]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && type !== 'richtext') {
      e.preventDefault();
      save(editValue);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancel();
    }
  }, [editValue, save, cancel, type]);

  // Click outside for richtext — use ref to avoid stale closure over editValue
  useEffect(() => {
    if (!editing || type !== 'richtext') return;
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        save(editValueRef.current);
      }
    };
    // Slight delay to avoid immediate close on the click that opened editing
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 100);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [editing, type, save]);

  // Click outside for select — cancel without saving
  useEffect(() => {
    if (!editing || type !== 'select') return;
    const handleClickOutside = (e: MouseEvent) => {
      if (selectWrapperRef.current && !selectWrapperRef.current.contains(e.target as Node)) {
        cancel();
      }
    };
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 100);
    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [editing, type, cancel]);

  if (!editing) {
    return (
      <div>
        {label && (
          <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
            {label}
          </h4>
        )}
        <button
          type="button"
          onClick={startEdit}
          className="group w-full text-left rounded-lg px-2 py-1 -mx-2 -my-1 hover:bg-gray-50 transition-colors cursor-pointer"
        >
          <span className="inline-flex items-center gap-1.5">
            {displayValue ?? (
              <span className={value ? 'text-text' : 'text-text-secondary italic text-sm'}>
                {value || placeholder}
              </span>
            )}
            <Pencil className="h-3 w-3 text-text-secondary opacity-0 group-hover:opacity-100 transition-opacity" />
            {saving && <Loader2 className="h-3 w-3 text-text-secondary animate-spin" />}
          </span>
        </button>
      </div>
    );
  }

  if (type === 'select') {
    return (
      <div ref={selectWrapperRef}>
        {label && (
          <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
            {label}
          </h4>
        )}
        <CreatableSelect
          value={editValue}
          onChange={async (v) => {
            setEditValue(v);
            setSaving(true);
            try {
              await onSave(v || null);
            } finally {
              setSaving(false);
              setEditing(false);
            }
          }}
          options={options ?? []}
          placeholder={placeholder}
          onCreate={onCreate}
          createLabel={createLabel}
          onClear={clearable ? async () => {
            setSaving(true);
            try {
              await onSave(null);
            } finally {
              setSaving(false);
              setEditing(false);
            }
          } : undefined}
        />
      </div>
    );
  }

  if (type === 'richtext') {
    return (
      <div ref={wrapperRef}>
        {label && (
          <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
            {label}
          </h4>
        )}
        <RichTextFormField
          value={editValue}
          onChange={setEditValue}
          rows={rows}
          placeholder={placeholder}
        />
        <div className="flex items-center gap-1 mt-1">
          <button
            type="button"
            onClick={() => save(editValue)}
            className="p-1 rounded text-green-600 hover:bg-green-50"
          >
            <Check className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={cancel}
            className="p-1 rounded text-text-secondary hover:bg-gray-100"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    );
  }

  // text and date
  return (
    <div>
      {label && (
        <h4 className="text-xs font-semibold text-text-secondary uppercase tracking-wider mb-1">
          {label}
        </h4>
      )}
      <input
        ref={inputRef}
        type={type === 'date' ? 'date' : 'text'}
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onBlur={() => save(editValue)}
        onKeyDown={handleKeyDown}
        className="w-full rounded-lg border border-primary-300 px-2 py-1 text-sm focus:outline-none focus:border-primary-400 bg-white"
        placeholder={placeholder}
      />
    </div>
  );
}
