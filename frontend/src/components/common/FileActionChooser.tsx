import { FileText, Users, BookOpen } from 'lucide-react';
import { Modal } from './Modal';
import { Button } from './Button';
import { useGlobalFileDropContext } from '@/contexts/GlobalFileDropContext';

export function FileActionChooser() {
  const { chooserFiles, showChooser, setShowChooser, chooseAction, discardChooserFiles } =
    useGlobalFileDropContext();

  if (!showChooser || chooserFiles.length === 0) return null;

  const handleClose = () => {
    setShowChooser(false);
    discardChooserFiles();
  };

  return (
    <Modal open={showChooser} onClose={handleClose} title="Bestand ontvangen" size="sm">
      <div className="space-y-4">
        <div className="flex items-center gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm text-text-secondary">
          <FileText className="h-4 w-4 shrink-0" />
          <span className="truncate">
            {chooserFiles.length === 1
              ? chooserFiles[0].name
              : `${chooserFiles.length} bestanden`}
          </span>
        </div>

        <p className="text-sm text-text-secondary">Wat wil je met dit bestand doen?</p>

        <div className="space-y-2">
          <button
            onClick={() => chooseAction('lead')}
            className="w-full flex items-center gap-3 rounded-lg border border-border px-4 py-3 text-left hover:bg-gray-50 transition-colors"
          >
            <div className="rounded-lg bg-blue-50 p-2">
              <Users className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-text">Nieuwe lead aanmaken</p>
              <p className="text-xs text-text-secondary">Analyseer met VLAM en maak een lead aan</p>
            </div>
          </button>

          <button
            onClick={() => chooseAction('bron')}
            className="w-full flex items-center gap-3 rounded-lg border border-border px-4 py-3 text-left hover:bg-gray-50 transition-colors"
          >
            <div className="rounded-lg bg-emerald-50 p-2">
              <BookOpen className="h-5 w-5 text-emerald-600" />
            </div>
            <div>
              <p className="text-sm font-medium text-text">Bron toevoegen aan corpus</p>
              <p className="text-xs text-text-secondary">Voeg toe als bronbestand</p>
            </div>
          </button>
        </div>

        <div className="flex justify-end pt-2">
          <Button variant="ghost" onClick={handleClose}>
            Annuleren
          </Button>
        </div>
      </div>
    </Modal>
  );
}
