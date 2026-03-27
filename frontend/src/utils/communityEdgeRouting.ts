/**
 * Routing logic for edge creation in the community graph.
 *
 * Different node-type pairs require different backend APIs.
 * This utility parses prefixed node IDs and returns a discriminated
 * union describing which API to call and what extra input is needed.
 */

type ParsedNode =
  | { type: 'lead'; rawId: string }
  | { type: 'person'; rawId: string }
  | { type: 'org'; rawId: string }
  | { type: 'node'; rawId: string }
  | { type: 'unknown'; rawId: string };

export function parseNodeId(prefixedId: string): ParsedNode {
  if (prefixedId.startsWith('lead-')) return { type: 'lead', rawId: prefixedId.slice(5) };
  if (prefixedId.startsWith('person-')) return { type: 'person', rawId: prefixedId.slice(7) };
  if (prefixedId.startsWith('org-')) return { type: 'org', rawId: prefixedId.slice(4) };
  if (prefixedId.startsWith('node-')) return { type: 'node', rawId: prefixedId.slice(5) };
  // orgtext- and oe- prefixes are not real entities we can link
  return { type: 'unknown', rawId: prefixedId };
}

export type ConnectionRoute =
  | { kind: 'lead_contact'; leadId: string; personId: string }
  | { kind: 'lead_node'; leadId: string; nodeId: string }
  | { kind: 'lead_org'; leadId: string; orgId: string }
  | { kind: 'corpus_edge'; fromNodeId: string; toNodeId: string }
  | { kind: 'node_stakeholder'; nodeId: string; personId: string }
  | { kind: 'invalid'; reason: string };

export function routeConnection(sourceId: string, targetId: string): ConnectionRoute {
  const src = parseNodeId(sourceId);
  const tgt = parseNodeId(targetId);

  if (src.type === 'unknown' || tgt.type === 'unknown') {
    return { kind: 'invalid', reason: 'Dit type node kan niet gekoppeld worden.' };
  }

  // Same-type connections are only valid for corpus nodes (node ↔ node)
  if (src.type === tgt.type && src.type !== 'node') {
    const label = src.type === 'lead' ? 'lead' : src.type === 'person' ? 'persoon' : 'organisatie';
    return { kind: 'invalid', reason: `Een ${label} kan niet aan een andere ${label} gekoppeld worden.` };
  }

  const pair = [src, tgt] as const;

  const lead = pair.find((n) => n.type === 'lead');
  const person = pair.find((n) => n.type === 'person');
  const org = pair.find((n) => n.type === 'org');
  const nodes = pair.filter((n) => n.type === 'node');

  if (lead && person) {
    return { kind: 'lead_contact', leadId: lead.rawId, personId: person.rawId };
  }

  if (lead && nodes.length === 1) {
    return { kind: 'lead_node', leadId: lead.rawId, nodeId: nodes[0].rawId };
  }

  if (lead && org) {
    return { kind: 'lead_org', leadId: lead.rawId, orgId: org.rawId };
  }

  if (nodes.length === 2) {
    return { kind: 'corpus_edge', fromNodeId: nodes[0].rawId, toNodeId: nodes[1].rawId };
  }

  if (nodes.length === 1 && person) {
    return { kind: 'node_stakeholder', nodeId: nodes[0].rawId, personId: person.rawId };
  }

  // Everything else is invalid
  const typeA = src.type === 'node' ? 'beleidsnode' : src.type;
  const typeB = tgt.type === 'node' ? 'beleidsnode' : tgt.type;
  return {
    kind: 'invalid',
    reason: `Een ${typeA} kan niet direct aan een ${typeB} gekoppeld worden.`,
  };
}
