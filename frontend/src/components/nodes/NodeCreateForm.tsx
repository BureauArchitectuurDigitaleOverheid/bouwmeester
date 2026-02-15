import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload } from 'lucide-react';
import { Modal } from '@/components/common/Modal';
import { Input } from '@/components/common/Input';
import { Select } from '@/components/common/Select';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { FormModalFooter } from '@/components/common/FormModalFooter';
import { RichTextFormField } from '@/components/common/RichTextFormField';
import { PendingTagsList } from './PendingTagsList';
import { TagSuggestions } from './TagSuggestions';
import { useQueryClient } from '@tanstack/react-query';
import { useCreateNode } from '@/hooks/useNodes';
import { useCreatableNodeTypeOptions } from '@/hooks/useNodeTypeOptions';
import { queryKeys } from '@/hooks/queryKeys';
import { NodeType, NodeStatus, NODE_STATUS_LABELS, BRON_TYPE_LABELS } from '@/types';
import { updateNodeBronDetail, uploadBijlage } from '@/api/nodes';
import { createEdge } from '@/api/edges';
import { EDGE_TYPE_ONDERDEEL_VAN } from './beleidskompas/constants';
import { addTagToNode } from '@/api/tags';
import { useToast } from '@/contexts/ToastContext';

interface NodeCreateFormProps {
  open: boolean;
  onClose: () => void;
  defaultNodeType?: NodeType;
  linkToDossierId?: string;
}

export function NodeCreateForm({ open, onClose, defaultNodeType, linkToDossierId }: NodeCreateFormProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const nodeTypeOptions = useCreatableNodeTypeOptions();
  const [title, setTitle] = useState('');
  const [nodeType, setNodeType] = useState<string>(defaultNodeType ?? NodeType.DOSSIER);
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState(NodeStatus.ACTIEF);
  const createNode = useCreateNode();
  const { showError } = useToast();

  // Bron-specific state
  const [bronType, setBronType] = useState('rapport');
  const [bronAuteur, setBronAuteur] = useState('');
  const [bronPublicatieDatum, setBronPublicatieDatum] = useState('');
  const [bronUrl, setBronUrl] = useState('');
  const [bijlageFile, setBijlageFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Tags suggested by LLM, to be applied after node creation
  const [pendingTags, setPendingTags] = useState<{ name: string; isNew: boolean }[]>([]);

  const isBron = nodeType === NodeType.BRON;

  const resetForm = () => {
    setTitle('');
    setNodeType(defaultNodeType ?? NodeType.DOSSIER);
    setDescription('');
    setStatus(NodeStatus.ACTIEF);
    setBronType('rapport');
    setBronAuteur('');
    setBronPublicatieDatum('');
    setBronUrl('');
    setBijlageFile(null);
    setPendingTags([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    setIsSubmitting(true);
    try {
      // 1. Create the node
      const node = await createNode.mutateAsync({
        title: title.trim(),
        node_type: nodeType as NodeType,
        description: description.trim() || undefined,
        status: status.trim() || undefined,
      });

      // 2. If bron, update bron detail fields
      if (isBron && (bronType !== 'rapport' || bronAuteur || bronPublicatieDatum || bronUrl)) {
        await updateNodeBronDetail(node.id, {
          type: bronType,
          auteur: bronAuteur || null,
          publicatie_datum: bronPublicatieDatum || null,
          url: bronUrl || null,
        });
      }

      // 3. If file was selected, upload it
      if (isBron && bijlageFile) {
        await uploadBijlage(node.id, bijlageFile);
      }

      // 4. If linkToDossierId is set, create an onderdeel_van edge
      if (linkToDossierId) {
        try {
          await createEdge({
            from_node_id: node.id,
            to_node_id: linkToDossierId,
            edge_type_id: EDGE_TYPE_ONDERDEEL_VAN,
          });
          await queryClient.invalidateQueries({ queryKey: queryKeys.nodes.graph(linkToDossierId, 2) });
          await queryClient.invalidateQueries({ queryKey: queryKeys.nodes.neighbors(linkToDossierId) });
          await queryClient.invalidateQueries({ queryKey: queryKeys.edges.all });
        } catch {
          // Non-critical: edge creation may fail if already linked
        }
      }

      // 5. Apply suggested tags
      for (const tag of pendingTags) {
        try {
          await addTagToNode(node.id, { tag_name: tag.name });
        } catch {
          // Non-critical: tag may already exist or fail silently
        }
      }

      resetForm();
      onClose();
      if (!linkToDossierId) {
        navigate(`/nodes/${node.id}`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Onbekende fout';
      showError(`Aanmaken mislukt: ${msg}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Nieuwe node aanmaken"
      footer={
        <FormModalFooter
          onCancel={onClose}
          onSubmit={handleSubmit}
          submitLabel="Aanmaken"
          isLoading={createNode.isPending || isSubmitting}
          disabled={!title.trim()}
        />
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Titel"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Voer een titel in..."
          required
          autoFocus
        />

        <CreatableSelect
          label="Type"
          value={nodeType}
          onChange={setNodeType}
          options={nodeTypeOptions}
        />

        <RichTextFormField label="Beschrijving" value={description} onChange={setDescription} rows={4} />

        <TagSuggestions
          title={title}
          description={description}
          nodeType={nodeType}
          onAcceptTag={(tagName, isNew) => {
            setPendingTags((prev) => {
              if (prev.some((t) => t.name === tagName)) return prev;
              return [...prev, { name: tagName, isNew }];
            });
          }}
        />

        <PendingTagsList
          tags={pendingTags}
          onRemove={(name) => setPendingTags((prev) => prev.filter((t) => t.name !== name))}
        />

        <Select
          label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value as NodeStatus)}
          options={Object.entries(NODE_STATUS_LABELS).map(([value, label]) => ({ value, label }))}
        />

        {isBron && (
          <>
            <div className="border-t border-border pt-4">
              <p className="text-sm font-medium text-text mb-3">Bron details</p>
            </div>

            <Select
              label="Bron type"
              value={bronType}
              onChange={(e) => setBronType(e.target.value)}
              options={Object.entries(BRON_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
            />

            <Input
              label="Auteur"
              value={bronAuteur}
              onChange={(e) => setBronAuteur(e.target.value)}
              placeholder="Naam van de auteur..."
            />

            <Input
              label="Publicatiedatum"
              type="date"
              value={bronPublicatieDatum}
              onChange={(e) => setBronPublicatieDatum(e.target.value)}
            />

            <Input
              label="URL"
              type="url"
              value={bronUrl}
              onChange={(e) => setBronUrl(e.target.value)}
              placeholder="https://..."
            />

            <div className="space-y-1.5">
              <label className="block text-sm font-medium text-text">
                Bijlage
              </label>
              <div className="relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-border hover:border-border-hover p-4 transition-colors cursor-pointer">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.doc,.docx,.odt,.txt,.png,.jpg,.jpeg"
                  onChange={(e) => setBijlageFile(e.target.files?.[0] ?? null)}
                  className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
                />
                <Upload className="h-5 w-5 text-text-secondary" />
                <p className="text-sm text-text-secondary">
                  {bijlageFile ? bijlageFile.name : 'Klik om een bestand te selecteren'}
                </p>
                <p className="text-xs text-text-secondary">
                  PDF, Word, ODT, TXT, PNG, JPEG (max. 20 MB)
                </p>
              </div>
            </div>
          </>
        )}
      </form>
    </Modal>
  );
}
