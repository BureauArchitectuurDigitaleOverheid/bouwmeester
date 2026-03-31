import { useEffect, useRef, useState, useCallback } from 'react';

interface UseGlobalFileDropOptions {
  onFiles: (files: File[]) => void;
  /** Called when a drag with "Files" type was dropped but dataTransfer.files was empty.
   *  This happens with New Outlook and some Outlook Mac configurations. */
  onEmptyFileDrop?: () => void;
  enabled?: boolean;
}

export function useGlobalFileDrop({ onFiles, onEmptyFileDrop, enabled = true }: UseGlobalFileDropOptions) {
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);
  const hadFilesType = useRef(false);
  const onFilesRef = useRef(onFiles);
  onFilesRef.current = onFiles;
  const onEmptyFileDropRef = useRef(onEmptyFileDrop);
  onEmptyFileDropRef.current = onEmptyFileDrop;

  const handleDragEnter = useCallback((e: DragEvent) => {
    e.preventDefault();
    dragCounter.current++;
    if (e.dataTransfer?.types.includes('Files')) {
      hadFilesType.current = true;
      setIsDragging(true);
    }
  }, []);

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    // Prevent Outlook from deleting the original email after drop.
    // Without this, Chrome defaults to "move" which Outlook interprets as
    // "move the email to Deleted Items".
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = 'copy';
    }
  }, []);

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    dragCounter.current = Math.max(0, dragCounter.current - 1);
    if (dragCounter.current === 0) {
      setIsDragging(false);
      hadFilesType.current = false;
    }
  }, []);

  const handleDrop = useCallback((e: DragEvent) => {
    e.preventDefault();
    const wasFilesDrag = hadFilesType.current;
    dragCounter.current = 0;
    hadFilesType.current = false;
    setIsDragging(false);

    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
      onFilesRef.current(Array.from(files));
    } else if (wasFilesDrag) {
      // The drag advertised "Files" but delivered nothing.
      // This happens with New Outlook (Windows/Mac) and Outlook Mac on Chrome/Firefox.
      onEmptyFileDropRef.current?.();
    }
  }, []);

  const handlePaste = useCallback((e: ClipboardEvent) => {
    // Don't intercept paste in input fields
    const el = document.activeElement;
    if (
      el instanceof HTMLInputElement ||
      el instanceof HTMLTextAreaElement ||
      (el as HTMLElement)?.isContentEditable
    ) {
      return;
    }

    const items = e.clipboardData?.items;
    if (!items) return;

    const files: File[] = [];
    for (const item of Array.from(items)) {
      if (item.kind === 'file') {
        const file = item.getAsFile();
        if (file) files.push(file);
      }
    }

    if (files.length > 0) {
      e.preventDefault();
      onFilesRef.current(files);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setIsDragging(false);
      dragCounter.current = 0;
      return;
    }

    document.addEventListener('dragenter', handleDragEnter);
    document.addEventListener('dragover', handleDragOver);
    document.addEventListener('dragleave', handleDragLeave);
    document.addEventListener('drop', handleDrop);
    document.addEventListener('paste', handlePaste);

    return () => {
      document.removeEventListener('dragenter', handleDragEnter);
      document.removeEventListener('dragover', handleDragOver);
      document.removeEventListener('dragleave', handleDragLeave);
      document.removeEventListener('drop', handleDrop);
      document.removeEventListener('paste', handlePaste);
    };
  }, [enabled, handleDragEnter, handleDragOver, handleDragLeave, handleDrop, handlePaste]);

  return { isDragging };
}
