import { NodeType } from '@/types';

const KCBR_BASE_URL = 'https://www.kcbr.nl/beleid-en-regelgeving-ontwikkelen/beleidskompas';

export interface BeleidskompasStep {
  id: string;
  number: number;
  question: string;
  description: string;
  nodeTypes: NodeType[];
  kcbrUrl: string;
}

export const KCBR_MAIN_URL = KCBR_BASE_URL;

export const KCBR_STAKEHOLDERS_URL = `${KCBR_BASE_URL}/wie-zijn-belanghebbenden-en-waarom`;

// NOTE: step definitions must stay in sync with
// backend/bouwmeester/repositories/corpus_node.py (kcbr_steps)
export const BELEIDSKOMPAS_STEPS: BeleidskompasStep[] = [
  {
    id: 'probleem',
    number: 1,
    question: 'Wat is het probleem?',
    description: 'Definieer het maatschappelijk probleem dat aanleiding geeft tot beleid.',
    nodeTypes: [NodeType.PROBLEEM],
    kcbrUrl: `${KCBR_BASE_URL}/1-wat-het-probleem`,
  },
  {
    id: 'doel',
    number: 2,
    question: 'Wat is het beoogde doel?',
    description: 'Formuleer de beleidsdoelen die je wilt bereiken.',
    nodeTypes: [NodeType.DOEL],
    kcbrUrl: `${KCBR_BASE_URL}/2-wat-het-beoogde-doel`,
  },
  {
    id: 'beleidsoptie',
    number: 3,
    question: 'Wat zijn opties om het doel te realiseren?',
    description: 'Verken welke beleidsopties er zijn om het probleem aan te pakken.',
    nodeTypes: [NodeType.BELEIDSOPTIE],
    kcbrUrl: `${KCBR_BASE_URL}/3-wat-zijn-opties-om-het-doel-te-realiseren`,
  },
  {
    id: 'effect',
    number: 4,
    question: 'Wat zijn de gevolgen van deze opties?',
    description: 'Beschrijf de verwachte (en onverwachte) effecten van het beleid.',
    nodeTypes: [NodeType.EFFECT],
    kcbrUrl: `${KCBR_BASE_URL}/4-wat-zijn-de-gevolgen-van-deze-opties`,
  },
  {
    id: 'voorkeursoptie',
    number: 5,
    question: 'Wat is de voorkeursoptie?',
    description: 'Werk de gekozen optie uit in beleidskader, instrumenten en maatregelen.',
    nodeTypes: [NodeType.BELEIDSKADER, NodeType.INSTRUMENT, NodeType.MAATREGEL],
    kcbrUrl: `${KCBR_BASE_URL}/5-wat-de-voorkeursoptie`,
  },
];
