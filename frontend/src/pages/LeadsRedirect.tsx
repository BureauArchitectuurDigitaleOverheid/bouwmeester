import { Navigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { getLead } from '@/api/leads';
import { useInitiatieven } from '@/hooks/useInitiatieven';
import { INITIATIEVEN_PATH, initiatiefPath } from '@/utils/initiatiefRoutes';

function withView(path: string, view: string | null): string {
  return view ? `${path}?view=${encodeURIComponent(view)}` : path;
}

/**
 * `/leads` was the leads page until the initiatief got its own page. Old
 * links, bookmarks and search results land here and go on to leads:
 *
 * - `?initiatief=X` to that initiatief's leads, in the same view;
 * - `?lead=Y` to the leads of Y's initiatief, with Y opened;
 * - anything else to the leads of the first initiatief, which is where the
 *   old page opened too; the overview only when there is no initiatief.
 */
export function LeadsRedirect() {
  const [searchParams] = useSearchParams();
  const initiatiefId = searchParams.get('initiatief');
  const leadId = searchParams.get('lead');
  const view = searchParams.get('view');

  const needList = !initiatiefId && !leadId;
  const { data: initiatieven, isLoading: listLoading } = useInitiatieven();
  const {
    data: lead,
    isLoading: leadLoading,
    isError: leadError,
  } = useQuery({
    queryKey: ['leads', 'redirect', leadId],
    queryFn: () => getLead(leadId!),
    enabled: !!leadId && !initiatiefId,
    retry: false,
  });

  if (initiatiefId) {
    return <Navigate to={withView(initiatiefPath(initiatiefId), view)} replace />;
  }

  if (leadId) {
    if (leadLoading) return <Waiting />;
    // A lead you cannot see, or one that is gone, still lands on something.
    const target = lead?.initiatief_id ? initiatiefPath(lead.initiatief_id) : INITIATIEVEN_PATH;
    return (
      <Navigate to={target} replace state={leadError ? undefined : { openLead: leadId }} />
    );
  }

  if (needList && listLoading) return <Waiting />;
  const first = initiatieven?.[0];
  return <Navigate to={first ? withView(initiatiefPath(first.id), view) : INITIATIEVEN_PATH} replace />;
}

function Waiting() {
  return (
    <nldd-container layout="row" horizontal-alignment="center" padding="48">
      <LoadingSpinner />
    </nldd-container>
  );
}
