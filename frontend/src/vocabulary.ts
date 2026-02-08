/**
 * Vocabulary mapping for dual-audience support.
 *
 * Bouwmeester serves two audiences:
 * - "beleid" (policy makers): Dutch beleidstheorie/Beleidskompas terminology
 * - "architectuur" (architects): ArchiMate Motivation Extension terminology
 *
 * Internal node_type values remain canonical. Only display labels change.
 */

export type VocabularyId = 'beleid' | 'architectuur';

export const VOCABULARY_LABELS: Record<VocabularyId, string> = {
  beleid: 'Beleid',
  architectuur: 'Architectuur',
};

export const NODE_TYPE_VOCABULARY: Record<string, { beleid: string; architectuur: string }> = {
  dossier:         { beleid: 'Dossier',          architectuur: 'Dossier' },
  doel:            { beleid: 'Doel',              architectuur: 'Goal' },
  instrument:      { beleid: 'Instrument',        architectuur: 'Capability' },
  beleidskader:    { beleid: 'Beleidskader',      architectuur: 'Architectuurprincipe' },
  maatregel:       { beleid: 'Maatregel',         architectuur: 'Course of Action' },
  politieke_input: { beleid: 'Politieke Input',   architectuur: 'Driver' },
  probleem:        { beleid: 'Probleem',          architectuur: 'Driver' },
  effect:          { beleid: 'Effect',            architectuur: 'Outcome' },
  beleidsoptie:    { beleid: 'Beleidsoptie',      architectuur: 'Course of Action' },
  notitie:         { beleid: 'Notitie',           architectuur: 'Notitie' },
  overig:          { beleid: 'Overig',            architectuur: 'Overig' },
};

export const EDGE_TYPE_VOCABULARY: Record<string, { beleid: string; architectuur: string }> = {
  draagt_bij_aan:   { beleid: 'Draagt bij aan',   architectuur: 'Influence' },
  implementeert:    { beleid: 'Implementeert',    architectuur: 'Realization' },
  vloeit_voort_uit: { beleid: 'Vloeit voort uit', architectuur: 'Association' },
  conflicteert_met: { beleid: 'Conflicteert met', architectuur: 'Conflict' },
  verwijst_naar:    { beleid: 'Verwijst naar',    architectuur: 'Association' },
  vereist:          { beleid: 'Vereist',           architectuur: 'Serving' },
  evalueert:        { beleid: 'Evalueert',         architectuur: 'Assessment' },
  vervangt:         { beleid: 'Vervangt',          architectuur: 'Succession' },
  onderdeel_van:    { beleid: 'Onderdeel van',     architectuur: 'Composition' },
  leidt_tot:        { beleid: 'Leidt tot',         architectuur: 'Triggering' },
  adresseert:       { beleid: 'Adresseert',        architectuur: 'Influence' },
  meet:             { beleid: 'Meet',              architectuur: 'Association' },
};
