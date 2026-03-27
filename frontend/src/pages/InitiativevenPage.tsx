import { useState } from 'react';
import { Plus, Lightbulb } from 'lucide-react';
import { Button } from '@/components/common/Button';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState } from '@/components/common/EmptyState';
import { InitiatiefCard } from '@/components/initiatieven/InitiatiefCard';
import { InitiatiefDetailModal } from '@/components/initiatieven/InitiatiefDetailModal';
import { useInitiatieven, useCreateInitiatief } from '@/hooks/useInitiatieven';
import { INITIATIEF_COLORS } from '@/types';
import type { Initiatief, InitiatiefCreate } from '@/types';

export function InitiativevenPage() {
  const [selectedInitiatief, setSelectedInitiatief] = useState<Initiatief | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);

  const { data: initiatieven = [], isLoading } = useInitiatieven();
  const createMutation = useCreateInitiatief();

  const [createForm, setCreateForm] = useState<InitiatiefCreate>({
    naam: '',
    beschrijving: '',
    kleur: INITIATIEF_COLORS[0],
  });

  const handleCreate = async () => {
    if (!createForm.naam.trim()) return;
    const created = await createMutation.mutateAsync(createForm);
    setShowCreateModal(false);
    setCreateForm({ naam: '', beschrijving: '', kleur: INITIATIEF_COLORS[0] });
    setSelectedInitiatief(created);
  };

  const handleCardClick = (initiatief: Initiatief) => {
    setSelectedInitiatief(initiatief);
  };

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <p className="text-sm text-text-secondary">
            Beheer initiatieven en hun leden en teams.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            icon={<Plus className="h-4 w-4" />}
            onClick={() => setShowCreateModal(true)}
          >
            <span className="hidden sm:inline">Initiatief toevoegen</span>
          </Button>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <LoadingSpinner className="py-16" />
      ) : initiatieven.length === 0 ? (
        <EmptyState
          icon={<Lightbulb className="h-16 w-16" />}
          title="Nog geen initiatieven"
          description="Maak een nieuw initiatief aan om te beginnen."
          action={
            <Button
              icon={<Plus className="h-4 w-4" />}
              onClick={() => setShowCreateModal(true)}
            >
              Initiatief toevoegen
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {initiatieven.map((initiatief) => (
            <InitiatiefCard
              key={initiatief.id}
              initiatief={initiatief}
              onClick={handleCardClick}
            />
          ))}
        </div>
      )}

      {/* Create modal */}
      {showCreateModal && (
        <CreateInitiatiefModal
          form={createForm}
          onChange={setCreateForm}
          onSubmit={handleCreate}
          onClose={() => setShowCreateModal(false)}
          isLoading={createMutation.isPending}
        />
      )}

      {/* Detail modal */}
      {selectedInitiatief && (
        <InitiatiefDetailModal
          initiatiefId={selectedInitiatief.id}
          open={!!selectedInitiatief}
          onClose={() => setSelectedInitiatief(null)}
        />
      )}
    </div>
  );
}

// ---------- Create Modal (inline) ----------

import { Modal } from '@/components/common/Modal';

function CreateInitiatiefModal({
  form,
  onChange,
  onSubmit,
  onClose,
  isLoading,
}: {
  form: InitiatiefCreate;
  onChange: (form: InitiatiefCreate) => void;
  onSubmit: () => void;
  onClose: () => void;
  isLoading: boolean;
}) {
  return (
    <Modal
      open
      onClose={onClose}
      title="Nieuw initiatief"
      size="sm"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={isLoading}>
            Annuleren
          </Button>
          <Button
            onClick={onSubmit}
            loading={isLoading}
            disabled={!form.naam.trim()}
          >
            Aanmaken
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-text">
            Naam <span className="text-red-500">*</span>
          </label>
          <input
            type="text"
            value={form.naam}
            onChange={(e) => onChange({ ...form, naam: e.target.value })}
            className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
            placeholder="Naam van het initiatief"
            autoFocus
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-text">
            Beschrijving
          </label>
          <textarea
            value={form.beschrijving || ''}
            onChange={(e) => onChange({ ...form, beschrijving: e.target.value })}
            className="w-full rounded-xl border border-border px-3.5 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 resize-none"
            rows={3}
            placeholder="Korte beschrijving..."
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-sm font-medium text-text">Kleur</label>
          <div className="flex gap-2 flex-wrap">
            {INITIATIEF_COLORS.map((color) => (
              <button
                key={color}
                type="button"
                onClick={() => onChange({ ...form, kleur: color })}
                className={`h-8 w-8 rounded-full border-2 transition-all ${
                  form.kleur === color
                    ? 'border-primary-500 scale-110'
                    : 'border-transparent hover:scale-105'
                }`}
                style={{ backgroundColor: color }}
              />
            ))}
          </div>
        </div>
      </div>
    </Modal>
  );
}
