import { useCallback, useState, type DragEvent, type ChangeEvent } from 'react';
import { Upload, FileText, X } from 'lucide-react';

interface FileUploadProps {
  accept?: string;
  onFileSelect: (file: File) => void;
  disabled?: boolean;
  label?: string;
}

export function FileUpload({
  accept = '.csv',
  onFileSelect,
  disabled = false,
  label = 'Sleep een bestand hierheen of klik om te uploaden',
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const handleDragOver = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      if (!disabled) setIsDragging(true);
    },
    [disabled],
  );

  const handleDragLeave = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setIsDragging(false);
      if (disabled) return;

      const file = e.dataTransfer.files[0];
      if (file) {
        setSelectedFile(file);
        onFileSelect(file);
      }
    },
    [disabled, onFileSelect],
  );

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        setSelectedFile(file);
        onFileSelect(file);
      }
    },
    [onFileSelect],
  );

  const handleClear = useCallback(() => {
    setSelectedFile(null);
  }, []);

  return (
    <div className="space-y-2">
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`
          relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-8 transition-colors
          ${isDragging ? 'border-primary-500 bg-primary-50' : 'border-border hover:border-border-hover'}
          ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}
        `}
      >
        <input
          type="file"
          accept={accept}
          onChange={handleChange}
          disabled={disabled}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
        />
        <Upload className="h-8 w-8 text-text-secondary" />
        <div className="text-center">
          <p className="text-sm font-medium text-text">{label}</p>
          <p className="mt-1 text-xs text-text-secondary">
            Ondersteunde formaten: {accept}
          </p>
        </div>
      </div>

      {selectedFile && (
        <div className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-2">
          <div className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-text-secondary" />
            <span className="text-sm text-text">{selectedFile.name}</span>
            <span className="text-xs text-text-secondary">
              ({(selectedFile.size / 1024).toFixed(1)} KB)
            </span>
          </div>
          <button
            onClick={handleClear}
            className="rounded p-1 text-text-secondary hover:bg-gray-200 hover:text-text transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}
