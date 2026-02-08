import { createContext, useContext, useState, useMemo, useCallback } from 'react';
import type { ReactNode } from 'react';
import {
  type VocabularyId,
  NODE_TYPE_VOCABULARY,
  EDGE_TYPE_VOCABULARY,
} from '@/vocabulary';

const STORAGE_KEY = 'vocabulary-id';

interface VocabularyContextValue {
  vocabularyId: VocabularyId;
  setVocabularyId: (id: VocabularyId) => void;
  nodeLabel: (nodeType: string) => string;
  nodeAltLabel: (nodeType: string) => string;
  edgeLabel: (edgeType: string) => string;
  edgeAltLabel: (edgeType: string) => string;
}

const VocabularyContext = createContext<VocabularyContextValue>({
  vocabularyId: 'beleid',
  setVocabularyId: () => {},
  nodeLabel: (t) => t,
  nodeAltLabel: (t) => t,
  edgeLabel: (t) => t,
  edgeAltLabel: (t) => t,
});

export function VocabularyProvider({ children }: { children: ReactNode }) {
  const [vocabularyId, setVocabularyIdState] = useState<VocabularyId>(
    () => (localStorage.getItem(STORAGE_KEY) as VocabularyId) || 'beleid',
  );

  const setVocabularyId = useCallback((id: VocabularyId) => {
    setVocabularyIdState(id);
    localStorage.setItem(STORAGE_KEY, id);
  }, []);

  const altId: VocabularyId = vocabularyId === 'beleid' ? 'architectuur' : 'beleid';

  const nodeLabel = useCallback(
    (nodeType: string) =>
      NODE_TYPE_VOCABULARY[nodeType]?.[vocabularyId] ?? nodeType,
    [vocabularyId],
  );

  const nodeAltLabel = useCallback(
    (nodeType: string) =>
      NODE_TYPE_VOCABULARY[nodeType]?.[altId] ?? nodeType,
    [altId],
  );

  const edgeLabel = useCallback(
    (edgeType: string) =>
      EDGE_TYPE_VOCABULARY[edgeType]?.[vocabularyId] ?? edgeType,
    [vocabularyId],
  );

  const edgeAltLabel = useCallback(
    (edgeType: string) =>
      EDGE_TYPE_VOCABULARY[edgeType]?.[altId] ?? edgeType,
    [altId],
  );

  const value = useMemo(
    () => ({
      vocabularyId,
      setVocabularyId,
      nodeLabel,
      nodeAltLabel,
      edgeLabel,
      edgeAltLabel,
    }),
    [vocabularyId, setVocabularyId, nodeLabel, nodeAltLabel, edgeLabel, edgeAltLabel],
  );

  return (
    <VocabularyContext.Provider value={value}>
      {children}
    </VocabularyContext.Provider>
  );
}

export function useVocabulary() {
  return useContext(VocabularyContext);
}
