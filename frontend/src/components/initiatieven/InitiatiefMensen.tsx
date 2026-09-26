import { useMemo, useState } from 'react';
import { Badge } from '@/components/common/Badge';
import { CreatableSelect } from '@/components/common/CreatableSelect';
import { Select } from '@/components/common/Select';
import { NlddIconButton } from '@/components/nldd/NlddIconButton';
import {
  useAddInitiatiefMember,
  useRemoveInitiatiefMember,
  useUpdateInitiatiefMemberRole,
  useAddInitiatiefEenheid,
  useRemoveInitiatiefEenheid,
  useUpdateInitiatiefEenheidRol,
} from '@/hooks/useInitiatieven';
import { usePeople } from '@/hooks/usePeople';
import { useOrganisatieFlat } from '@/hooks/useOrganisatie';
import { INITIATIEF_ROL_LABELS } from '@/types';
import type { InitiatiefDetail, InitiatiefMember } from '@/types';
import { StakeholderTab } from '@/components/stakeholders/StakeholderTab';
import { SectionHeading } from './SectionHeading';
import { NlddButton } from '@/components/nldd/NlddButton';
import { useCan } from '@/hooks/useCan';
import { useEenheidGrants } from '@/hooks/useEenheidGrants';

const INITIATIEF_ROLS = Object.keys(INITIATIEF_ROL_LABELS);

/**
 * The "Mensen" tab: who works on the initiatief (members and eenheden, which
 * both grant access) and who has a stake in it (stakeholders, which grant
 * nothing). Membership is a grant, decided by the backend's grant authority;
 * stakeholders follow the right to update the initiatief.
 */
export function InitiatiefMensen({ initiatief }: { initiatief: InitiatiefDetail }) {
  const resource = { type: 'initiatief', id: initiatief.id } as const;
  // Adding a member hands out the default rol; making someone eigenaar is
  // a stronger grant, asked separately.
  const { allowed: canManage } = useCan('resource_role:grant', { ...resource, rol: 'contributor' });
  const { allowed: canGrantOwner } = useCan('resource_role:grant', { ...resource, rol: 'eigenaar' });

  return (
    <nldd-container gap="32">
      <Members initiatief={initiatief} canManage={canManage} canGrantOwner={canGrantOwner} />
      <Eenheden initiatief={initiatief} canManage={canManage} />
      <nldd-container gap="8">
        <SectionHeading icon="person" text="Stakeholders" />
        <StakeholderTab scopeType="initiatief" scopeId={initiatief.id} />
      </nldd-container>
    </nldd-container>
  );
}

function Members({
  initiatief,
  canManage,
  canGrantOwner,
}: {
  initiatief: InitiatiefDetail;
  canManage: boolean;
  canGrantOwner: boolean;
}) {
  const addMemberMutation = useAddInitiatiefMember();
  const removeMemberMutation = useRemoveInitiatiefMember();
  const updateRoleMutation = useUpdateInitiatiefMemberRole();
  const { data: allPeople = [] } = usePeople();
  const [addMemberValue, setAddMemberValue] = useState('');

  const eigenaarCount = initiatief.members.filter((m) => m.rol === 'eigenaar').length;

  const availablePeopleOptions = useMemo(() => {
    const memberIds = new Set(initiatief.members.map((m) => m.person_id));
    return allPeople
      .filter((p) => !memberIds.has(p.id) && !p.is_agent)
      .map((p) => ({ value: p.id, label: p.naam }));
  }, [allPeople, initiatief.members]);

  const handleAddMember = async (personId: string) => {
    if (!personId) return;
    await addMemberMutation.mutateAsync({ initiatiefId: initiatief.id, personId });
    setAddMemberValue('');
  };

  const setRole = (personId: string, rol: 'eigenaar' | 'contributor') =>
    updateRoleMutation.mutateAsync({ initiatiefId: initiatief.id, personId, rol });

  return (
    <nldd-container gap="8">
      <SectionHeading icon="users" text={`Leden (${initiatief.members.length})`} />

      {initiatief.members.length > 0 && (
        <nldd-list type="list" variant="box-tinted">
          {initiatief.members.map((member) => (
            <MemberRow
              key={member.person_id}
              initiatiefId={initiatief.id}
              member={member}
              lastEigenaar={member.rol === 'eigenaar' && eigenaarCount === 1}
              canGrantOwner={canGrantOwner}
              onRemove={() => removeMemberMutation.mutate({ initiatiefId: initiatief.id, personId: member.person_id })}
              onSetRole={(rol) => void setRole(member.person_id, rol)}
            />
          ))}
        </nldd-list>
      )}

      {canManage && (
        <nldd-container layout="row" gap="8" vertical-alignment="top">
          <nldd-container width="fit-content" className="row-fill">
            <CreatableSelect
              value={addMemberValue}
              onChange={(val) => {
                setAddMemberValue(val);
                if (val) handleAddMember(val);
              }}
              options={availablePeopleOptions}
              placeholder="Lid toevoegen..."
              emptyMessage="Geen personen gevonden"
            />
          </nldd-container>
          <NlddButton
            variant="secondary"
            size="sm"
            startIcon="person-badge-plus"
            onClick={() => {
              if (addMemberValue) handleAddMember(addMemberValue);
            }}
            disabled={!addMemberValue}
            text="Toevoegen"
          />
        </nldd-container>
      )}
    </nldd-container>
  );
}

/**
 * One member. Changing the rol needs the authority to hand out eigenaar
 * (and never demotes the last one); removing is the backend's revoke
 * decision, which lets you leave yourself and keeps the last eigenaar.
 */
function MemberRow({
  initiatiefId,
  member,
  lastEigenaar,
  canGrantOwner,
  onRemove,
  onSetRole,
}: {
  initiatiefId: string;
  member: InitiatiefMember;
  lastEigenaar: boolean;
  canGrantOwner: boolean;
  onRemove: () => void;
  onSetRole: (rol: 'eigenaar' | 'contributor') => void;
}) {
  const { allowed: canRemove } = useCan('resource_role:revoke', {
    type: 'initiatief',
    id: initiatiefId,
    rol: member.rol,
    targetPersonId: member.person_id,
  });
  const isEigenaar = member.rol === 'eigenaar';
  return (
    <nldd-list-item>
      <nldd-container layout="row" width="full" gap="8" horizontal-alignment="right" vertical-alignment="center">
        <nldd-container layout="row" gap="8" vertical-alignment="center">
          <nldd-text-cell text={member.person_naam} width="fit-content" />
          <Badge color={isEigenaar ? 'paars' : 'coolgray'}>
            {INITIATIEF_ROL_LABELS[member.rol] ?? member.rol}
          </Badge>
        </nldd-container>
        {((canGrantOwner && !lastEigenaar) || canRemove) && (
          <div className="hug">
            {canGrantOwner && !lastEigenaar && (
              <NlddButton
                variant="neutral-transparent"
                size="sm"
                onClick={() => onSetRole(isEigenaar ? 'contributor' : 'eigenaar')}
                text={isEigenaar ? 'Maak bijdrager' : 'Maak eigenaar'}
              />
            )}
            {canRemove && (
              <NlddIconButton
                icon="close"
                accessibleLabel={`${member.person_naam} verwijderen`}
                variant="neutral-transparent"
                size="sm"
                onClick={onRemove}
              />
            )}
          </div>
        )}
      </nldd-container>
    </nldd-list-item>
  );
}

function Eenheden({ initiatief, canManage }: { initiatief: InitiatiefDetail; canManage: boolean }) {
  const addEenheidMutation = useAddInitiatiefEenheid();
  const removeEenheidMutation = useRemoveInitiatiefEenheid();
  const updateEenheidRolMutation = useUpdateInitiatiefEenheidRol();
  const { data: allEenheden = [] } = useOrganisatieFlat();
  const [addEenheidValue, setAddEenheidValue] = useState('');
  const grants = useEenheidGrants('initiatief', initiatief.id, initiatief.eenheden, INITIATIEF_ROLS);

  const availableEenheidOptions = useMemo(() => {
    const linked = new Set(initiatief.eenheden.map((e) => e.eenheid_id));
    return allEenheden
      .filter((e) => !linked.has(e.id))
      .map((e) => ({ value: e.id, label: e.naam }));
  }, [allEenheden, initiatief.eenheden]);

  const handleAddEenheid = async (eenheidId: string) => {
    if (!eenheidId) return;
    await addEenheidMutation.mutateAsync({ initiatiefId: initiatief.id, eenheidId });
    setAddEenheidValue('');
  };

  // Without an eigenaar to add one, an empty list is only noise.
  if (!canManage && initiatief.eenheden.length === 0) return null;

  return (
    <nldd-container gap="8">
      <SectionHeading icon="apartment-building" text={`Organisatie-eenheden (${initiatief.eenheden.length})`} />
      <nldd-text size="xs" color="secondary">
        Iedereen in een gekoppelde eenheid krijgt de rol die hier naast de eenheid staat.
      </nldd-text>

      {initiatief.eenheden.length > 0 && (
        <nldd-list type="list" variant="box-tinted">
          {initiatief.eenheden.map((eenheid, i) => {
            const { canRemove, rols } = grants[i];
            const canChangeRol = rols.length > 1;
            return (
              <nldd-list-item key={eenheid.eenheid_id}>
                <nldd-container layout="row" width="full" gap="8" vertical-alignment="center">
                  {/* The name takes what the role column leaves. With
                      `fit-content` and no floor it shrank to within a word:
                      "RegelRecht" broke as "RegelRec/ht". */}
                  <nldd-text-cell text={eenheid.eenheid_naam} width="full" />
                  {/* A fixed width for the role column. `fit-content` gave it
                      nothing of its own to measure, so it collapsed to zero and
                      drew the select's chevrons and the delete cross on top of
                      each other at the row's edge. */}
                  <nldd-container
                    layout="row"
                    width={canChangeRol || canRemove ? '200px' : '120px'}
                    className="shrink-0"
                    gap="6"
                    vertical-alignment="center"
                    horizontal-alignment="right"
                  >
                    {canChangeRol ? (
                      <nldd-container width="160px">
                        <Select
                          value={eenheid.rol}
                          aria-label="Rol van deze eenheid"
                          onChange={(e) =>
                            updateEenheidRolMutation.mutateAsync({
                              initiatiefId: initiatief.id,
                              eenheidId: eenheid.eenheid_id,
                              rol: e.target.value,
                            })
                          }
                          options={rols.map((value) => ({
                            value,
                            label: INITIATIEF_ROL_LABELS[value] ?? value,
                          }))}
                        />
                      </nldd-container>
                    ) : (
                      <nldd-tag color="neutral" size="sm" text={INITIATIEF_ROL_LABELS[eenheid.rol] ?? eenheid.rol} />
                    )}
                    {canRemove && (
                      <NlddIconButton
                        icon="close"
                        accessibleLabel={`${eenheid.eenheid_naam} verwijderen`}
                        variant="neutral-transparent"
                        size="sm"
                        onClick={() =>
                          removeEenheidMutation.mutateAsync({
                            initiatiefId: initiatief.id,
                            eenheidId: eenheid.eenheid_id,
                          })
                        }
                      />
                    )}
                  </nldd-container>
                </nldd-container>
              </nldd-list-item>
            );
          })}
        </nldd-list>
      )}

      {canManage && (
        <nldd-container layout="row" gap="8" vertical-alignment="top">
          <nldd-container width="fit-content" className="row-fill">
            <CreatableSelect
              value={addEenheidValue}
              onChange={(val) => {
                setAddEenheidValue(val);
                if (val) handleAddEenheid(val);
              }}
              options={availableEenheidOptions}
              placeholder="Eenheid toevoegen..."
              emptyMessage="Geen eenheden gevonden"
            />
          </nldd-container>
          <NlddButton
            variant="secondary"
            size="sm"
            startIcon="apartment-building"
            onClick={() => {
              if (addEenheidValue) handleAddEenheid(addEenheidValue);
            }}
            disabled={!addEenheidValue}
            text="Toevoegen"
          />
        </nldd-container>
      )}
    </nldd-container>
  );
}
