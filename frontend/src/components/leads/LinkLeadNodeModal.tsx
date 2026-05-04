import { useState, useCallback, useMemo } from 'react';

import { Modal } from '@/components/common/Modal';
import { Button } from '@/components/common/Button';
import { CreatableSelect, type SelectOption } from '@/components/common/CreatableSelect';
import { useNodes, useCreateNode } from '@/hooks/useNodes';
import { usePeople, useCreatePerson } from '@/hooks/usePeople';
import { useLinkLeadNode, useAddLeadContact } from '@/hooks/useLeads';
import { useToast } from '@/contexts/ToastContext';
import { NodeType, NODE_TYPE_LABELS, LEAD_CONTACT_ROL_LABELS } from '@/types';

const CONTACT_ROLLEN: SelectOption[] = Object.entries(LEAD_CONTACT_ROL_LABELS).map(
  ([value, label]) => ({ value, label }),
);

interface Props {
  leadId: string | null;
  existingContactPersonIds: string[];
  onClose: () => void;
}

export function LinkLeadNodeModal({ leadId, existingContactPersonIds, onClose }: Props) {
  const { data: nodes = [] } = useNodes();
  const { data: people = [] } = usePeople();
  const createNode = useCreateNode();
  const createPerson = useCreatePerson();
  const linkNode = useLinkLeadNode();
  const addContact = useAddLeadContact();
  const { showError } = useToast();

  const [nodeId, setNodeId] = useState('');
  const [personId, setPersonId] = useState('');
  const [rol, setRol] = useState('contactpersoon');

  const nodeOptions: SelectOption[] = useMemo(
    () =>
      nodes.map((n) => ({
        value: n.id,
        label: n.title,
        description: NODE_TYPE_LABELS[n.node_type as NodeType] ?? n.node_type?.replace(/_/g, ' '),
      })),
    [nodes],
  );

  const personOptions: SelectOption[] = useMemo(
    () =>
      people
        .filter((p) => p.is_active)
        .map((p) => ({
          value: p.id,
          label: p.naam,
          description: p.functie ?? undefined,
        })),
    [people],
  );

  const handleCreateNode = useCallback(
    async (text: string): Promise<string | null> => {
      const node = await createNode.mutateAsync({ title: text, node_type: NodeType.NOTITIE });
      return node.id;
    },
    [createNode],
  );

  const handleCreatePerson = useCallback(
    async (name: string): Promise<string | null> => {
      const result = await createPerson.mutateAsync({ naam: name, force: true });
      return result?.id ?? null;
    },
    [createPerson],
  );

  const resetAndClose = useCallback(() => {
    setNodeId('');
    setPersonId('');
    setRol('contactpersoon');
    onClose();
  }, [onClose]);

  const handleSubmit = useCallback(async () => {
    if (!leadId || !nodeId) return;
    try {
      await linkNode.mutateAsync({ leadId, nodeId });
      if (personId && !existingContactPersonIds.includes(personId)) {
        try {
          await addContact.mutateAsync({ leadId, personId, rol });
        } catch {
          showError('Node gekoppeld, maar contactpersoon kon niet worden toegevoegd');
        }
      }
      resetAndClose();
    } catch {
      // useMutationWithError already shows a toast
    }
  }, [
    leadId,
    nodeId,
    personId,
    rol,
    existingContactPersonIds,
    linkNode,
    addContact,
    resetAndClose,
    showError,
  ]);

  const submitting = linkNode.isPending || addContact.isPending;

  return (
    <Modal
      open={!!leadId}
      onClose={resetAndClose}
      title="Node koppelen"
      size="sm"
      zIndex={60}
      footer={
        <>
          <Button variant="secondary" onClick={resetAndClose}>
            Annuleren
          </Button>
          <Button onClick={handleSubmit} loading={submitting} disabled={!nodeId}>
            Koppelen
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <CreatableSelect
          label="Node"
          value={nodeId}
          onChange={setNodeId}
          options={nodeOptions}
          placeholder="Zoek of maak een node..."
          onCreate={handleCreateNode}
          createLabel="Nieuwe notitie aanmaken"
          required
        />
        <div className="border-t border-border pt-4 space-y-3">
          <p className="text-xs text-text-secondary">
            Optioneel: voeg ook een contactpersoon toe aan deze lead.
          </p>
          <CreatableSelect
            label="Contactpersoon"
            value={personId}
            onChange={setPersonId}
            options={personOptions}
            placeholder="Zoek of maak een persoon..."
            onCreate={handleCreatePerson}
            createLabel="Nieuwe persoon aanmaken"
            onClear={personId ? () => setPersonId('') : undefined}
          />
          {personId && (
            <CreatableSelect
              label="Rol"
              value={rol}
              onChange={setRol}
              options={CONTACT_ROLLEN}
              placeholder="Selecteer een rol..."
              searchable={false}
            />
          )}
        </div>
      </div>
    </Modal>
  );
}
