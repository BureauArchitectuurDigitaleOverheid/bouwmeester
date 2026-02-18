import { useState } from 'react';
import { Check, Plus, Sparkles } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';

interface AutoTagDialogProps {
  open: boolean;
  onClose: () => void;
  matchedTags: string[];
  suggestedNewTags: string[];
  onAccept: (tags: { name: string; isNew: boolean }[]) => void;
  onSkip: () => void;
}

export function AutoTagDialog({
  open,
  onClose,
  matchedTags,
  suggestedNewTags,
  onAccept,
  onSkip,
}: AutoTagDialogProps) {
  const [selected, setSelected] = useState<Set<string>>(
    new Set([...matchedTags, ...suggestedNewTags]),
  );

  const toggleTag = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const handleAcceptAll = () => {
    const newTagSet = new Set(suggestedNewTags);
    const tags = [...selected].map((name) => ({
      name,
      isNew: newTagSet.has(name),
    }));
    onAccept(tags);
    onClose();
  };

  const handleSkip = () => {
    onSkip();
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={handleSkip}
      title="Tag-suggesties"
      footer={
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={handleSkip}>
            Overslaan
          </Button>
          <Button
            onClick={handleAcceptAll}
            disabled={selected.size === 0}
            icon={<Sparkles className="h-3.5 w-3.5" />}
          >
            Toevoegen ({selected.size})
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-text-secondary">
          Deze node heeft weinig tags. Wil je de volgende suggesties toevoegen?
        </p>

        {matchedTags.length > 0 && (
          <div>
            <p className="text-xs font-medium text-text-secondary mb-1.5">Bestaande tags</p>
            <div className="flex flex-wrap gap-1.5">
              {matchedTags.map((tag) => (
                <TagChip
                  key={tag}
                  name={tag}
                  selected={selected.has(tag)}
                  onToggle={() => toggleTag(tag)}
                />
              ))}
            </div>
          </div>
        )}

        {suggestedNewTags.length > 0 && (
          <div>
            <p className="text-xs font-medium text-text-secondary mb-1.5">Nieuwe tags</p>
            <div className="flex flex-wrap gap-1.5">
              {suggestedNewTags.map((tag) => (
                <TagChip
                  key={tag}
                  name={tag}
                  isNew
                  selected={selected.has(tag)}
                  onToggle={() => toggleTag(tag)}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

function TagChip({
  name,
  isNew = false,
  selected,
  onToggle,
}: {
  name: string;
  isNew?: boolean;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors ${
        selected
          ? 'bg-primary-100 text-primary-700 ring-1 ring-primary-300'
          : 'bg-slate-100 text-slate-500 hover:bg-slate-200'
      }`}
    >
      {selected ? (
        <Check className="h-3 w-3" />
      ) : isNew ? (
        <Plus className="h-3 w-3" />
      ) : (
        <Check className="h-3 w-3 opacity-30" />
      )}
      {name}
    </button>
  );
}
