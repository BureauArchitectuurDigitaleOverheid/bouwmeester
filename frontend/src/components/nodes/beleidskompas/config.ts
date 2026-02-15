import { NodeType } from '@/types';

export interface BeleidskompasStep {
  id: string;
  label: string;
  description: string;
  nodeType: NodeType;
}

/** Dutch plural forms for node type labels used in the Beleidskompas panel. */
export const NODE_TYPE_LABELS_PLURAL: Partial<Record<NodeType, string>> = {
  [NodeType.PROBLEEM]: 'problemen',
  [NodeType.DOEL]: 'doelen',
  [NodeType.BELEIDSOPTIE]: 'beleidsopties',
  [NodeType.BELEIDSKADER]: 'beleidskaders',
  [NodeType.INSTRUMENT]: 'instrumenten',
  [NodeType.MAATREGEL]: 'maatregelen',
  [NodeType.EFFECT]: 'effecten',
};

export const BELEIDSKOMPAS_STEPS: BeleidskompasStep[] = [
  {
    id: 'probleem',
    label: 'Probleem geformuleerd',
    description: 'Definieer het maatschappelijk probleem dat aanleiding geeft tot beleid.',
    nodeType: NodeType.PROBLEEM,
  },
  {
    id: 'doel',
    label: 'Doel gedefinieerd',
    description: 'Formuleer de beleidsdoelen die je wilt bereiken.',
    nodeType: NodeType.DOEL,
  },
  {
    id: 'beleidsoptie',
    label: 'Beleidsopties verkend',
    description: 'Verken welke beleidsopties er zijn om het probleem aan te pakken.',
    nodeType: NodeType.BELEIDSOPTIE,
  },
  {
    id: 'beleidskader',
    label: 'Beleidskader vastgesteld',
    description: 'Stel het beleidskader vast waarbinnen het beleid wordt vormgegeven.',
    nodeType: NodeType.BELEIDSKADER,
  },
  {
    id: 'instrument',
    label: 'Instrumenten gekozen',
    description: 'Kies de beleidsinstrumenten die worden ingezet.',
    nodeType: NodeType.INSTRUMENT,
  },
  {
    id: 'maatregel',
    label: 'Maatregelen gedefinieerd',
    description: 'Definieer concrete maatregelen die worden genomen.',
    nodeType: NodeType.MAATREGEL,
  },
  {
    id: 'effect',
    label: 'Effecten beschreven',
    description: 'Beschrijf de verwachte (en onverwachte) effecten van het beleid.',
    nodeType: NodeType.EFFECT,
  },
];
