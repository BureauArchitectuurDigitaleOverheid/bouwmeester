import { useState } from 'react';
import { Merge, Check } from 'lucide-react';
import { useDuplicatePersons, useMergePersons } from '@/hooks/usePeople';
import type { DuplicateGroupMember } from '@/api/people';

function MemberLabel({ member }: { member: DuplicateGroupMember }) {
  return (
    <span>
      {member.naam}
      {!member.is_active && (
        <span className="ml-1 text-xs text-red-500 font-medium">(inactief)</span>
      )}
      {member.email && <span className="text-text-secondary ml-1">({member.email})</span>}
      {member.functie && (
        <span className="text-text-secondary ml-1">- {member.functie}</span>
      )}
    </span>
  );
}

function DuplicateGroupRow({
  members,
  onMerged,
}: {
  members: DuplicateGroupMember[];
  onMerged: () => void;
}) {
  const [targetId, setTargetId] = useState<string>(members[0].id);
  const [confirming, setConfirming] = useState(false);
  const merge = useMergePersons();

  const handleMerge = async () => {
    const sourceIds = members.filter((m) => m.id !== targetId).map((m) => m.id);
    await merge.mutateAsync({ sourceIds, targetId });
    setConfirming(false);
    onMerged();
  };

  const sourceCount = members.length - 1;
  const targetNaam = members.find((m) => m.id === targetId)?.naam ?? '';

  return (
    <div className="border border-border rounded-lg p-4 space-y-3">
      <p className="text-sm font-medium text-text">
        {members.length} personen met naam &ldquo;{members[0].naam}&rdquo;
      </p>
      <div className="space-y-1">
        {members.map((m) => (
          <label
            key={m.id}
            className={`flex items-center gap-2 text-sm px-2 py-1.5 rounded cursor-pointer ${
              targetId === m.id
                ? 'bg-primary-50 border border-primary-200'
                : 'hover:bg-gray-50'
            }`}
          >
            <input
              type="radio"
              name={`target-${members[0].naam}`}
              value={m.id}
              checked={targetId === m.id}
              onChange={() => setTargetId(m.id)}
              className="accent-primary-600"
            />
            <MemberLabel member={m} />
            {targetId === m.id && (
              <span className="ml-auto text-xs text-primary-600 font-medium">behouden</span>
            )}
          </label>
        ))}
      </div>

      {confirming ? (
        <div className="rounded-md border border-amber-300 bg-amber-50 p-3 space-y-2">
          <p className="text-sm text-amber-800">
            {sourceCount} {sourceCount === 1 ? 'persoon wordt' : 'personen worden'} samengevoegd
            in &ldquo;{targetNaam}&rdquo;. Alle referenties worden overgeheveld en de{' '}
            {sourceCount === 1 ? 'bronpersoon wordt' : 'bronpersonen worden'} permanent
            verwijderd. Dit kan niet ongedaan worden.
          </p>
          <div className="flex gap-2">
            <button
              onClick={handleMerge}
              disabled={merge.isPending}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
            >
              <Merge className="h-3.5 w-3.5" />
              {merge.isPending ? 'Samenvoegen...' : 'Ja, samenvoegen'}
            </button>
            <button
              onClick={() => setConfirming(false)}
              disabled={merge.isPending}
              className="px-3 py-1.5 text-sm font-medium rounded-lg border border-gray-300 hover:bg-gray-50 disabled:opacity-50 transition-colors"
            >
              Annuleren
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setConfirming(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg bg-primary-600 text-white hover:bg-primary-700 transition-colors"
        >
          <Merge className="h-3.5 w-3.5" />
          Samenvoegen
        </button>
      )}
    </div>
  );
}

export function DuplicateManager() {
  const { data: groups, isLoading, refetch } = useDuplicatePersons();

  if (isLoading) {
    return <div className="text-sm text-text-secondary py-8 text-center">Laden...</div>;
  }

  if (!groups || groups.length === 0) {
    return (
      <div className="text-center py-12 text-text-secondary">
        <Check className="h-8 w-8 mx-auto mb-2 text-green-500" />
        <p className="text-sm">Geen duplicaten gevonden.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-text-secondary">
        {groups.length} groep{groups.length !== 1 ? 'en' : ''} met mogelijke duplicaten.
        Selecteer per groep welke persoon je wilt behouden. De overige worden samengevoegd
        (alle referenties worden overgeheveld).
      </p>
      {groups.map((group) => (
        <DuplicateGroupRow
          key={group.members.map((m) => m.id).join('-')}
          members={group.members}
          onMerged={() => refetch()}
        />
      ))}
    </div>
  );
}
