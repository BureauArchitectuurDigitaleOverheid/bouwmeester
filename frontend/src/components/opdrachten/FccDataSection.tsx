import { Cloud } from 'lucide-react';

import { Badge } from '@/components/common/Badge';
import { DetailSection } from '@/components/common/DetailSection';
import {
  FCC_TRAFFIC_LIGHT_COLORS,
  FCC_TRAFFIC_LIGHT_FIELDS,
  type FccTrafficLight,
} from '@/types';
import { formatCurrency } from '@/utils/format';

interface FccDataSectionProps {
  data: Record<string, unknown>;
  funnelfase?: string | null;
  afdeling?: string | null;
  portfolio?: string | null;
  labels?: string | null;
}

export function FccDataSection({
  data,
  funnelfase,
  afdeling,
  portfolio,
  labels,
}: FccDataSectionProps) {
  const trafficLights = FCC_TRAFFIC_LIGHT_FIELDS.map(({ key, label }) => ({
    label,
    value: data[key] as string | undefined,
  })).filter((tl) => tl.value);

  const labelList = labels
    ? labels.split(',').map((l) => l.trim()).filter(Boolean)
    : [];

  const metaItems: { label: string; value: string }[] = [];
  if (funnelfase) metaItems.push({ label: 'Funnelfase', value: funnelfase });
  if (afdeling) metaItems.push({ label: 'Afdeling', value: afdeling });
  const domein = data.PDD_Domein as string | undefined;
  if (domein && domein !== afdeling) metaItems.push({ label: 'Domein', value: domein });
  if (portfolio) metaItems.push({ label: 'Portfolio', value: portfolio });
  const fccType = data.Type as string | undefined;
  if (fccType) metaItems.push({ label: 'FCC Type', value: fccType });
  const fccStatus = data.Status as string | undefined;
  if (fccStatus) metaItems.push({ label: 'FCC Status', value: fccStatus });
  const eigenaar = data.Eigenaar as string | undefined;
  if (eigenaar) metaItems.push({ label: 'Eigenaar', value: eigenaar });
  const contactOpdrachtnemer = data.Contact_opdrachtnemer as string | undefined;
  if (contactOpdrachtnemer) metaItems.push({ label: 'Contact opdrachtnemer', value: contactOpdrachtnemer });
  const contactOpdrachtgever = data.Contactpersoon_opdrachtgever as string | undefined;
  if (contactOpdrachtgever) metaItems.push({ label: 'Contactpersoon opdrachtgever', value: contactOpdrachtgever });

  // Multi-year budget totals
  const budgetTotaal = data.Budget_totaal_ as number | undefined;
  const gerealiseerTotaal = data.Gerealiseerde_kosten_totaal_ as number | undefined;

  if (trafficLights.length === 0 && metaItems.length === 0 && labelList.length === 0) {
    return null;
  }

  return (
    <DetailSection
      title="Fortes Change Cloud"
      icon={<Cloud className="h-3.5 w-3.5" />}
      separated
    >
      <div className="space-y-3">
        {/* Traffic lights */}
        {trafficLights.length > 0 && (
          <div className="flex flex-wrap gap-3">
            {trafficLights.map(({ label, value }) => (
              <div key={label} className="flex items-center gap-1.5 text-xs text-text-secondary">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${FCC_TRAFFIC_LIGHT_COLORS[value as FccTrafficLight] || 'bg-gray-300'}`}
                  title={`${label}: ${value}`}
                />
                {label}
              </div>
            ))}
          </div>
        )}

        {/* Metadata grid */}
        {metaItems.length > 0 && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
            {metaItems.map(({ label, value }) => (
              <div key={label} className="contents">
                <dt className="text-text-secondary text-xs">{label}</dt>
                <dd className="text-text text-xs">{value}</dd>
              </div>
            ))}
          </dl>
        )}

        {/* Labels */}
        {labelList.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {labelList.map((label) => (
              <Badge key={label} variant="slate">
                {label}
              </Badge>
            ))}
          </div>
        )}

        {/* Multi-year totals */}
        {(budgetTotaal != null || gerealiseerTotaal != null) && (
          <div className="flex gap-4 text-xs text-text-secondary">
            {budgetTotaal != null && (
              <span>Budget totaal: {formatCurrency(budgetTotaal)}</span>
            )}
            {gerealiseerTotaal != null && (
              <span>Gerealiseerd totaal: {formatCurrency(gerealiseerTotaal)}</span>
            )}
          </div>
        )}
      </div>
    </DetailSection>
  );
}
