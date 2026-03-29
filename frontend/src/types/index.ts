// Node Types
export enum NodeType {
  DOSSIER = 'dossier',
  DOEL = 'doel',
  INSTRUMENT = 'instrument',
  BELEIDSKADER = 'beleidskader',
  MAATREGEL = 'maatregel',
  POLITIEKE_INPUT = 'politieke_input',
  PROBLEEM = 'probleem',
  EFFECT = 'effect',
  BELEIDSOPTIE = 'beleidsoptie',
  BRON = 'bron',
  NOTITIE = 'notitie',
  OVERIG = 'overig',
}

export const NODE_TYPE_LABELS: Record<NodeType, string> = {
  [NodeType.DOSSIER]: 'Dossier',
  [NodeType.DOEL]: 'Doel',
  [NodeType.INSTRUMENT]: 'Instrument',
  [NodeType.BELEIDSKADER]: 'Beleidskader',
  [NodeType.MAATREGEL]: 'Maatregel',
  [NodeType.POLITIEKE_INPUT]: 'Politieke Input',
  [NodeType.PROBLEEM]: 'Probleem',
  [NodeType.EFFECT]: 'Effect',
  [NodeType.BELEIDSOPTIE]: 'Beleidsoptie',
  [NodeType.BRON]: 'Bron',
  [NodeType.NOTITIE]: 'Notitie',
  [NodeType.OVERIG]: 'Overig',
};

/** Dutch plural forms for node type labels. */
export const NODE_TYPE_LABELS_PLURAL: Partial<Record<NodeType, string>> = {
  [NodeType.PROBLEEM]: 'problemen',
  [NodeType.DOEL]: 'doelen',
  [NodeType.BELEIDSOPTIE]: 'beleidsopties',
  [NodeType.BELEIDSKADER]: 'beleidskaders',
  [NodeType.INSTRUMENT]: 'instrumenten',
  [NodeType.MAATREGEL]: 'maatregelen',
  [NodeType.EFFECT]: 'effecten',
};

export const NODE_TYPE_COLORS: Record<NodeType, BadgeVariant> = {
  [NodeType.DOSSIER]: 'blue',
  [NodeType.DOEL]: 'green',
  [NodeType.INSTRUMENT]: 'purple',
  [NodeType.BELEIDSKADER]: 'amber',
  [NodeType.MAATREGEL]: 'cyan',
  [NodeType.POLITIEKE_INPUT]: 'rose',
  [NodeType.PROBLEEM]: 'red',
  [NodeType.EFFECT]: 'emerald',
  [NodeType.BELEIDSOPTIE]: 'indigo',
  [NodeType.BRON]: 'orange',
  [NodeType.NOTITIE]: 'slate',
  [NodeType.OVERIG]: 'gray',
};

export const NODE_TYPE_HEX_COLORS: Record<NodeType, string> = {
  [NodeType.DOSSIER]: '#3B82F6',
  [NodeType.DOEL]: '#10B981',
  [NodeType.INSTRUMENT]: '#8B5CF6',
  [NodeType.BELEIDSKADER]: '#F59E0B',
  [NodeType.MAATREGEL]: '#06B6D4',
  [NodeType.POLITIEKE_INPUT]: '#F43F5E',
  [NodeType.PROBLEEM]: '#EF4444',
  [NodeType.EFFECT]: '#059669',
  [NodeType.BELEIDSOPTIE]: '#6366F1',
  [NodeType.BRON]: '#F97316',
  [NodeType.NOTITIE]: '#64748b',
  [NodeType.OVERIG]: '#9ca3af',
};

export const NODE_TYPE_BG_COLORS: Record<NodeType, string> = {
  [NodeType.DOSSIER]: '#EFF6FF',
  [NodeType.DOEL]: '#ECFDF5',
  [NodeType.INSTRUMENT]: '#F5F3FF',
  [NodeType.BELEIDSKADER]: '#FFFBEB',
  [NodeType.MAATREGEL]: '#ECFEFF',
  [NodeType.POLITIEKE_INPUT]: '#FFF1F2',
  [NodeType.PROBLEEM]: '#FEF2F2',
  [NodeType.EFFECT]: '#ECFDF5',
  [NodeType.BELEIDSOPTIE]: '#EEF2FF',
  [NodeType.BRON]: '#FFF7ED',
  [NodeType.NOTITIE]: '#F8FAFC',
  [NodeType.OVERIG]: '#F9FAFB',
};

export const BRON_TYPE_LABELS: Record<string, string> = {
  rapport: 'Rapport',
  onderzoek: 'Onderzoek',
  wetgeving: 'Wetgeving',
  advies: 'Advies',
  opinie: 'Opinie',
  beleidsnota: 'Beleidsnota',
  evaluatie: 'Evaluatie',
  overig: 'Overig',
};

// Node Status
export enum NodeStatus {
  CONCEPT = 'concept',
  ACTIEF = 'actief',
  GEPAUZEERD = 'gepauzeerd',
  AFGEROND = 'afgerond',
  GEKOZEN = 'gekozen',
  AFGEWEZEN = 'afgewezen',
}

export const NODE_STATUS_LABELS: Record<NodeStatus, string> = {
  [NodeStatus.CONCEPT]: 'Concept',
  [NodeStatus.ACTIEF]: 'Actief',
  [NodeStatus.GEPAUZEERD]: 'Gepauzeerd',
  [NodeStatus.AFGEROND]: 'Afgerond',
  [NodeStatus.GEKOZEN]: 'Gekozen',
  [NodeStatus.AFGEWEZEN]: 'Afgewezen',
};

// Beleidskompas progress (returned for dossier nodes)
export interface BeleidskompasProgress {
  completed_steps: number;
  total_steps: number;
}

// Financial summary (returned for instrument nodes)
export interface FinancieelSummary {
  totaal_budget: number;
  totaal_gerealiseerd: number;
}

// Corpus Node
export interface CorpusNode {
  id: string;
  title: string;
  node_type: NodeType;
  description?: string;
  status?: string;
  metadata?: Record<string, unknown>;
  geldig_van?: string | null;
  geldig_tot?: string | null;
  created_at: string;
  updated_at: string;
  edge_count?: number;
  beleidskompas_progress?: BeleidskompasProgress | null;
  financieel_summary?: FinancieelSummary | null;
}

export interface CorpusNodeCreate {
  title: string;
  node_type: NodeType;
  description?: string;
  status?: string;
  metadata?: Record<string, unknown>;
  geldig_van?: string | null;
}

export interface CorpusNodeUpdate {
  title?: string;
  description?: string;
  status?: string;
  metadata?: Record<string, unknown>;
  geldig_tot?: string | null;
  wijzig_datum?: string | null;
}

export interface NodeTitleRecord {
  id: string;
  title: string;
  geldig_van: string;
  geldig_tot?: string | null;
}

export interface NodeStatusRecord {
  id: string;
  status: string;
  geldig_van: string;
  geldig_tot?: string | null;
}

// Edge Types
export interface EdgeType {
  id: string;
  name: string;
  label: string;
  description?: string;
}

// Edges
export interface Edge {
  id: string;
  from_node_id: string;
  to_node_id: string;
  edge_type_id: string;
  weight?: number;
  description?: string;
  created_at: string;
  from_node?: CorpusNode;
  to_node?: CorpusNode;
}

export interface EdgeCreate {
  from_node_id: string;
  to_node_id: string;
  edge_type_id: string;
  description?: string;
}

// Tasks
export enum TaskStatus {
  OPEN = 'open',
  IN_PROGRESS = 'in_progress',
  DONE = 'done',
  CANCELLED = 'cancelled',
}

export enum TaskPriority {
  KRITIEK = 'kritiek',
  HOOG = 'hoog',
  NORMAAL = 'normaal',
  LAAG = 'laag',
}

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  [TaskStatus.OPEN]: 'Open',
  [TaskStatus.IN_PROGRESS]: 'In uitvoering',
  [TaskStatus.DONE]: 'Afgerond',
  [TaskStatus.CANCELLED]: 'Geannuleerd',
};

export const TASK_PRIORITY_LABELS: Record<TaskPriority, string> = {
  [TaskPriority.KRITIEK]: 'Kritiek',
  [TaskPriority.HOOG]: 'Hoog',
  [TaskPriority.NORMAAL]: 'Normaal',
  [TaskPriority.LAAG]: 'Laag',
};

export const TASK_PRIORITY_COLORS: Record<TaskPriority, BadgeVariant> = {
  [TaskPriority.KRITIEK]: 'red',
  [TaskPriority.HOOG]: 'orange',
  [TaskPriority.NORMAAL]: 'blue',
  [TaskPriority.LAAG]: 'gray',
};

export const TASK_STATUS_COLORS: Record<TaskStatus, BadgeVariant> = {
  [TaskStatus.OPEN]: 'blue',
  [TaskStatus.IN_PROGRESS]: 'amber',
  [TaskStatus.DONE]: 'green',
  [TaskStatus.CANCELLED]: 'gray',
};

export interface TaskOrgEenheidSummary {
  id: string;
  naam: string;
  type: string;
}

export interface TaskSubtask {
  id: string;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  assignee?: { id: string; naam: string; is_agent: boolean };
  due_date?: string;
  order?: number;
  work_type?: string;
}

export interface TaskOpdrachtSummary {
  id: string;
  titel: string;
  type: string;
  status: string;
}

export interface Task {
  id: string;
  title: string;
  description?: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_date?: string;
  assignee_id?: string;
  assignee?: Person;
  organisatie_eenheid_id?: string;
  organisatie_eenheid?: TaskOrgEenheidSummary;
  parent_id?: string;
  parlementair_item_id?: string;
  opdracht_id?: string;
  opdracht?: TaskOpdrachtSummary;
  subtasks?: TaskSubtask[];
  node_id?: string;
  node?: CorpusNode;
  order?: number;
  work_type?: string;
  created_at: string;
  updated_at: string;
}

export interface TaskCreate {
  title: string;
  description?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  due_date?: string;
  assignee_id?: string;
  organisatie_eenheid_id?: string;
  parent_id?: string;
  parlementair_item_id?: string;
  opdracht_id?: string;
  node_id: string;
  work_type?: string;
}

export interface TaskUpdate {
  title?: string;
  description?: string | null;
  status?: TaskStatus;
  priority?: TaskPriority;
  due_date?: string | null;
  assignee_id?: string | null;
  organisatie_eenheid_id?: string | null;
  parent_id?: string | null;
  opdracht_id?: string | null;
  work_type?: string | null;
}

export interface EenheidPersonTaskStats {
  person_id: string;
  person_naam: string;
  open_count: number;
  in_progress_count: number;
  done_count: number;
  overdue_count: number;
}

export interface EenheidSubeenheidStats {
  eenheid_id: string;
  eenheid_naam: string;
  eenheid_type: string;
  open_count: number;
  in_progress_count: number;
  done_count: number;
  overdue_count: number;
}

export interface EenheidOverviewResponse {
  unassigned_count: number;
  unassigned_no_unit: Task[];
  unassigned_no_unit_count: number;
  unassigned_no_person: Task[];
  unassigned_no_person_count: number;
  by_person: EenheidPersonTaskStats[];
  by_subeenheid: EenheidSubeenheidStats[];
  eenheid_type: string;
}

// Organisatie Eenheid
export interface OrganisatieEenheid {
  id: string;
  naam: string;
  type: string;
  parent_id?: string | null;
  manager_id?: string | null;
  manager?: Person | null;
  beschrijving?: string | null;
  geldig_van?: string | null;
  geldig_tot?: string | null;
  created_at: string;
}

export interface OrganisatieEenheidTreeNode extends OrganisatieEenheid {
  children: OrganisatieEenheidTreeNode[];
  personen_count: number;
}

export interface OrganisatieEenheidCreate {
  naam: string;
  type: string;
  parent_id?: string | null;
  manager_id?: string | null;
  beschrijving?: string | null;
  geldig_van?: string | null;
}

export interface OrganisatieEenheidUpdate {
  naam?: string;
  type?: string;
  parent_id?: string | null;
  manager_id?: string | null;
  beschrijving?: string | null;
  geldig_tot?: string | null;
  wijzig_datum?: string | null;
}

export interface OrgNaamRecord {
  id: string;
  naam: string;
  geldig_van: string;
  geldig_tot?: string | null;
}

export interface OrgParentRecord {
  id: string;
  parent_id: string;
  geldig_van: string;
  geldig_tot?: string | null;
}

export interface OrgManagerRecord {
  id: string;
  manager_id?: string | null;
  manager?: Person | null;
  geldig_van: string;
  geldig_tot?: string | null;
}

export interface OrganisatieEenheidPersonenGroup {
  eenheid: OrganisatieEenheid;
  personen: Person[];
  children: OrganisatieEenheidPersonenGroup[];
}

export const ORGANISATIE_TYPE_LABELS: Record<string, string> = {
  ministerie: 'Ministerie',
  directoraat_generaal: 'Directoraat-Generaal',
  directie: 'Directie',
  dienst: 'Dienst',
  bureau: 'Bureau',
  afdeling: 'Afdeling',
  cluster: 'Cluster',
  team: 'Team',
};

export type BadgeVariant = 'blue' | 'green' | 'purple' | 'amber' | 'cyan' | 'rose' | 'slate' | 'gray' | 'red' | 'orange' | 'emerald' | 'indigo';

export const ORGANISATIE_TYPE_BADGE_COLORS: Record<string, BadgeVariant> = {
  ministerie: 'blue',
  directoraat_generaal: 'purple',
  directie: 'amber',
  dienst: 'gray',
  bureau: 'gray',
  cluster: 'gray',
  afdeling: 'cyan',
  team: 'green',
};

export const ORGANISATIE_TYPE_OPTIONS: { value: string; label: string }[] =
  Object.entries(ORGANISATIE_TYPE_LABELS).map(([value, label]) => ({ value, label }));

export const FUNCTIE_LABELS: Record<string, string> = {
  minister: 'Minister',
  staatssecretaris: 'Staatssecretaris',
  secretaris_generaal: 'Secretaris-Generaal',
  plaatsvervangend_secretaris_generaal: 'Plaatsvervangend Secretaris-Generaal',
  directeur_generaal: 'Directeur-Generaal',
  plaatsvervangend_directeur_generaal: 'Plaatsvervangend Directeur-Generaal',
  directeur: 'Directeur',
  afdelingshoofd: 'Afdelingshoofd',
  coordinator: 'Coördinator',
  beleidsmedewerker: 'Beleidsmedewerker',
  senior_beleidsmedewerker: 'Senior Beleidsmedewerker',
  adviseur: 'Adviseur',
  projectleider: 'Projectleider',
  programmamanager: 'Programmamanager',
  jurist: 'Jurist',
  'coördinerend_beleidsmedewerker': 'Coördinerend Beleidsmedewerker',
  communicatieadviseur: 'Communicatieadviseur',
  staff_engineer: 'Staff Engineer',
};

/**
 * Unicode-safe title case: capitalize the first letter of each space-separated word.
 * Unlike \b\w which treats non-ASCII (ö, é, …) as word boundaries, this splits
 * on whitespace so "coördinerend beleidsmedewerker" → "Coördinerend Beleidsmedewerker".
 */
export function titleCase(str: string): string {
  return str
    .split(' ')
    .map(w => (w.length > 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(' ');
}

export function formatFunctie(functie?: string | null): string | undefined {
  if (!functie) return undefined;
  return FUNCTIE_LABELS[functie] ?? titleCase(functie.replace(/_/g, ' '));
}

// People
export interface PersonEmail {
  id: string;
  email: string;
  is_default: boolean;
  created_at: string;
}

export interface PersonPhone {
  id: string;
  phone_number: string;
  label: string;
  is_default: boolean;
  created_at: string;
}

export const PHONE_LABELS: Record<string, string> = {
  werk: 'Werk',
  mobiel: 'Mobiel',
  prive: 'Priv\u00e9',
};

export interface Person {
  id: string;
  naam: string;
  email?: string;
  functie?: string;
  description?: string;
  is_agent: boolean;
  is_admin: boolean;
  has_api_key?: boolean;
  is_active: boolean;
  created_at: string;
  last_seen_at?: string | null;
  emails: PersonEmail[];
  phones: PersonPhone[];
  default_email?: string | null;
  default_phone?: string | null;
}

/** Extended response from POST /api/people — includes one-time api_key for agents. */
export interface PersonCreateResult extends Person {
  api_key?: string | null;
}

export interface PersonCreate {
  naam: string;
  email?: string;
  functie?: string;
  description?: string;
  is_agent?: boolean;
}

export interface ApiKeyResponse {
  api_key: string;
  person_id: string;
}

// PersonEditForm submit discriminated union
/** Create a new person (optionally link to org) */
interface PersonFormCreate {
  kind: 'create';
  data: PersonCreate;
  orgEenheidId?: string;
  dienstverband?: string;
}

/** Link an existing person to an org */
interface PersonFormLink {
  kind: 'link';
  existingPersonId: string;
  orgEenheidId?: string;
  dienstverband?: string;
}

/** Edit an existing person's fields */
interface PersonFormEdit {
  kind: 'edit';
  personId: string;
  data: PersonCreate;
}

export type PersonFormSubmitParams = PersonFormCreate | PersonFormLink | PersonFormEdit;

// Person ↔ OrganisatieEenheid placements
export interface PersonOrganisatie {
  id: string;
  person_id: string;
  organisatie_eenheid_id: string;
  organisatie_eenheid_naam: string;
  dienstverband: string;
  start_datum: string;
  eind_datum?: string | null;
}

export const DIENSTVERBAND_LABELS: Record<string, string> = {
  in_dienst: 'In dienst',
  ingehuurd: 'Ingehuurd',
  extern: 'Extern',
};

// Person Summary (expanded card)
export interface PersonTaskSummary {
  id: string;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_date?: string;
}

export interface PersonStakeholderNode {
  node_id: string;
  node_title: string;
  node_type: NodeType;
  stakeholder_rol: string;
}

export interface PersonSummaryResponse {
  open_task_count: number;
  done_task_count: number;
  open_tasks: PersonTaskSummary[];
  stakeholder_nodes: PersonStakeholderNode[];
}

export interface NodeStakeholder {
  id: string;
  person: Person;
  rol: string;
}

export const STAKEHOLDER_ROL_LABELS: Record<string, string> = {
  eigenaar: 'Eigenaar',
  betrokken: 'Betrokken',
  adviseur: 'Adviseur',
  indiener: 'Indiener',
};

export const LEAD_CONTACT_ROL_LABELS: Record<string, string> = {
  contactpersoon: 'Contactpersoon',
  opdrachtgever: 'Opdrachtgever',
  betrokken: 'Betrokken',
};

export const INITIATIEF_ROL_LABELS: Record<string, string> = {
  eigenaar: 'Eigenaar',
  contributor: 'Bijdrager',
  viewer: 'Lezer',
};

// Notification type labels and colors
export const NOTIFICATION_TYPE_LABELS: Record<string, string> = {
  task_assigned: 'taak toegewezen',
  task_overdue: 'taak verlopen',
  task_completed: 'taak afgerond',
  task_reassigned: 'taak overgedragen',
  node_updated: 'node bijgewerkt',
  edge_created: 'relatie aangemaakt',
  coverage_needed: 'vervanging nodig',
  stakeholder_added: 'betrokkene toegevoegd',
  stakeholder_role_changed: 'rol gewijzigd',
  direct_message: 'bericht',
  agent_prompt: 'agent prompt',
  mention: 'vermelding',
  politieke_input_imported: 'parlementair item',
  access_request: 'toegangsverzoek',
  placement_request: 'plaatsingsverzoek',
  placement_approved: 'plaatsing goedgekeurd',
  placement_denied: 'plaatsing afgewezen',
  emoji_reaction: 'reactie',
};

export const NOTIFICATION_TYPE_COLORS: Record<string, string> = {
  task_assigned: 'bg-blue-100 text-blue-700',
  task_overdue: 'bg-red-100 text-red-700',
  task_completed: 'bg-green-100 text-green-700',
  task_reassigned: 'bg-orange-100 text-orange-700',
  node_updated: 'bg-green-100 text-green-700',
  edge_created: 'bg-purple-100 text-purple-700',
  coverage_needed: 'bg-amber-100 text-amber-700',
  stakeholder_added: 'bg-teal-100 text-teal-700',
  stakeholder_role_changed: 'bg-teal-100 text-teal-700',
  direct_message: 'bg-green-100 text-green-700',
  agent_prompt: 'bg-violet-100 text-violet-700',
  mention: 'bg-cyan-100 text-cyan-700',
  politieke_input_imported: 'bg-rose-100 text-rose-700',
  access_request: 'bg-amber-100 text-amber-700',
  placement_request: 'bg-indigo-100 text-indigo-700',
  placement_approved: 'bg-green-100 text-green-700',
  placement_denied: 'bg-red-100 text-red-700',
  emoji_reaction: 'bg-pink-100 text-pink-700',
};

export const INBOX_TYPE_COLORS: Record<string, BadgeVariant> = {
  task: 'blue',
  node: 'purple',
  notification: 'amber',
  message: 'green',
};

// Activity
export interface Activity {
  id: string;
  event_type: string;
  actor_id?: string;
  actor_naam?: string;
  node_id?: string;
  task_id?: string;
  edge_id?: string;
  details?: Record<string, unknown>;
  created_at: string;
}

export interface ActivityFeedResponse {
  items: Activity[];
  total: number;
}

export const EVENT_TYPE_LABELS: Record<string, string> = {
  'node.created': 'Node aangemaakt',
  'node.updated': 'Node bewerkt',
  'node.deleted': 'Node verwijderd',
  'stakeholder.added': 'Betrokkene toegevoegd',
  'stakeholder.updated': 'Betrokkene rol gewijzigd',
  'stakeholder.removed': 'Betrokkene verwijderd',
  'node_tag.added': 'Tag toegevoegd aan node',
  'node_tag.removed': 'Tag verwijderd van node',
  'tag.created': 'Tag aangemaakt',
  'tag.updated': 'Tag bewerkt',
  'tag.deleted': 'Tag verwijderd',
  'task.created': 'Taak aangemaakt',
  'task.updated': 'Taak bewerkt',
  'task.deleted': 'Taak verwijderd',
  'edge.created': 'Relatie aangemaakt',
  'edge.updated': 'Relatie bewerkt',
  'edge.deleted': 'Relatie verwijderd',
  'person.created': 'Persoon aangemaakt',
  'person.updated': 'Persoon bewerkt',
  'person.deleted': 'Persoon verwijderd',
  'person.organisatie_added': 'Organisatie-plaatsing toegevoegd',
  'person.organisatie_updated': 'Organisatie-plaatsing bewerkt',
  'person.organisatie_removed': 'Organisatie-plaatsing verwijderd',
  'organisatie.created': 'Organisatie aangemaakt',
  'organisatie.updated': 'Organisatie bewerkt',
  'organisatie.deleted': 'Organisatie verwijderd',
  'parlementair.rejected': 'Parlementair item afgewezen',
  'parlementair.reviewed': 'Parlementair item beoordeeld',
  'parlementair.edge_approved': 'Parlementaire relatie goedgekeurd',
  'parlementair.edge_rejected': 'Parlementaire relatie afgewezen',
  'parlementair.edge_reset': 'Parlementaire relatie gereset',
  'parlementair.import_triggered': 'Parlementaire import gestart',
  'lead.created': 'Lead aangemaakt',
  'lead.updated': 'Lead bewerkt',
  'lead.deleted': 'Lead verwijderd',
  'lead.moved': 'Lead verplaatst',
  'lead.merged': 'Leads samengevoegd',
  'lead_contact.added': 'Contactpersoon toegevoegd aan lead',
  'lead_contact.removed': 'Contactpersoon verwijderd van lead',
  'lead_node.added': 'Node gekoppeld aan lead',
  'lead_node.removed': 'Node ontkoppeld van lead',
  'lead_tag.added': 'Tag toegevoegd aan lead',
  'lead_tag.removed': 'Tag verwijderd van lead',
  'lead_activity.added': 'Notitie toegevoegd aan lead',
  'lead_attachment.uploaded': 'Bijlage geüpload bij lead',
  'lead_attachment.deleted': 'Bijlage verwijderd bij lead',
  'initiatief.created': 'Initiatief aangemaakt',
  'initiatief.updated': 'Initiatief bewerkt',
  'initiatief.deleted': 'Initiatief verwijderd',
  'initiatief_member.added': 'Lid toegevoegd aan initiatief',
  'initiatief_member.removed': 'Lid verwijderd van initiatief',
  'initiatief_member.updated': 'Lidrol gewijzigd in initiatief',
  'initiatief_eenheid.added': 'Eenheid toegevoegd aan initiatief',
  'initiatief_eenheid.removed': 'Eenheid verwijderd van initiatief',
  'externe_organisatie.created': 'Externe organisatie aangemaakt',
  'externe_organisatie.updated': 'Externe organisatie bewerkt',
  'externe_organisatie.deleted': 'Externe organisatie verwijderd',
  'bijlage.uploaded': 'Bijlage geüpload',
  'bijlage.deleted': 'Bijlage verwijderd',
  'import.politieke_inputs': 'Politieke inputs geïmporteerd',
  'import.nodes': 'Nodes geïmporteerd',
  'import.edges': 'Relaties geïmporteerd',
  'opdracht.created': 'Opdracht aangemaakt',
  'opdracht.updated': 'Opdracht bewerkt',
  'opdracht.deleted': 'Opdracht verwijderd',
};

export const EVENT_TYPE_CATEGORY_LABELS: Record<string, string> = {
  node: 'Nodes',
  task: 'Taken',
  edge: 'Relaties',
  person: 'Personen',
  organisatie: 'Organisatie',
  tag: 'Tags',
  node_tag: 'Node-tags',
  stakeholder: 'Betrokkenen',
  parlementair: 'Parlementair',
  lead: 'Leads',
  lead_contact: 'Lead-contacten',
  lead_node: 'Lead-nodes',
  lead_tag: 'Lead-tags',
  lead_activity: 'Lead-activiteiten',
  lead_attachment: 'Lead-bijlagen',
  initiatief: 'Initiatieven',
  initiatief_member: 'Initiatief-leden',
  initiatief_eenheid: 'Initiatief-eenheden',
  externe_organisatie: 'Externe organisaties',
  bijlage: 'Bijlagen',
  import: 'Imports',
  opdracht: 'Opdrachten',
};

// Inbox
export interface InboxItem {
  id: string;
  type: string;
  /** Original notification type (e.g. "stakeholder_added") for display label */
  notification_type?: string;
  title: string;
  description?: string;
  source?: string;
  node_id?: string;
  task_id?: string;
  sender_name?: string;
  reply_count?: number;
  created_at: string;
  read: boolean;
}

export interface InboxResponse {
  items: InboxItem[];
  total: number;
  unread_count: number;
}

// Search
export type SearchResultType =
  | 'corpus_node'
  | 'task'
  | 'person'
  | 'organisatie_eenheid'
  | 'parlementair_item'
  | 'tag'
  | 'lead';

export const SEARCH_RESULT_TYPE_LABELS: Record<SearchResultType, string> = {
  corpus_node: 'Beleidscorpus',
  task: 'Taak',
  person: 'Persoon',
  organisatie_eenheid: 'Organisatie',
  parlementair_item: 'Parlementair',
  tag: 'Tag',
  lead: 'Lead',
};

export const SEARCH_RESULT_TYPE_COLORS: Record<SearchResultType, BadgeVariant> = {
  corpus_node: 'blue',
  task: 'amber',
  person: 'green',
  organisatie_eenheid: 'purple',
  parlementair_item: 'rose',
  tag: 'cyan',
  lead: 'orange',
};

export interface SearchResult {
  id: string;
  result_type: SearchResultType;
  title: string;
  subtitle?: string;
  description?: string;
  score: number;
  highlights?: string[];
  url: string;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  query: string;
}

// Graph View
export interface GraphViewResponse {
  nodes: CorpusNode[];
  edges: Edge[];
}

// Tags
export interface Tag {
  id: string;
  name: string;
  parent_id?: string | null;
  description?: string | null;
  created_at: string;
  children?: Tag[];
}

export interface TagCreate {
  name: string;
  parent_id?: string | null;
  description?: string | null;
}

export interface NodeTagResponse {
  id: string;
  tag: Tag;
  created_at: string;
}

// Parlementair Item
export type ParlementairItemType = 'motie' | 'kamervraag' | 'toezegging' | 'amendement' | 'commissiedebat' | 'schriftelijk_overleg' | 'interpellatie';
export type ParlementairItemStatus = 'pending' | 'imported' | 'reviewed' | 'rejected' | 'out_of_scope';
export type SuggestedEdgeStatus = 'pending' | 'approved' | 'rejected';

export const PARLEMENTAIR_TYPE_LABELS: Record<string, string> = {
  motie: 'Motie',
  kamervraag: 'Kamervraag',
  toezegging: 'Toezegging',
  amendement: 'Amendement',
  commissiedebat: 'Commissiedebat',
  schriftelijk_overleg: 'Schriftelijk Overleg',
  interpellatie: 'Interpellatie',
};

export const PARLEMENTAIR_TYPE_COLORS: Record<string, BadgeVariant> = {
  motie: 'rose',
  kamervraag: 'blue',
  toezegging: 'amber',
  amendement: 'purple',
  commissiedebat: 'cyan',
  schriftelijk_overleg: 'slate',
  interpellatie: 'red',
};

export const ALL_PARLEMENTAIR_TYPES: ParlementairItemType[] = Object.keys(
  PARLEMENTAIR_TYPE_LABELS,
) as ParlementairItemType[];

export const PARLEMENTAIR_TYPE_HEX_COLORS: Record<string, string> = {
  motie: '#F43F5E',
  kamervraag: '#3B82F6',
  toezegging: '#F59E0B',
  amendement: '#8B5CF6',
  commissiedebat: '#06B6D4',
  schriftelijk_overleg: '#64748b',
  interpellatie: '#EF4444',
};

export interface ParlementairItem {
  id: string;
  type: ParlementairItemType;
  zaak_id: string;
  zaak_nummer: string;
  titel: string;
  onderwerp: string;
  bron: string;
  datum?: string;
  status: ParlementairItemStatus;
  corpus_node_id?: string;
  indieners?: string[];
  document_tekst?: string;
  document_url?: string;
  llm_samenvatting?: string;
  matched_tags?: string[];
  deadline?: string;
  ministerie?: string;
  extra_data?: Record<string, unknown>;
  imported_at?: string;
  reviewed_at?: string;
  created_at: string;
  suggested_edges?: SuggestedEdge[];
}

export interface SuggestedEdge {
  id: string;
  parlementair_item_id: string;
  target_node_id: string;
  target_node?: CorpusNode;
  edge_type_id: string;
  confidence: number;
  reason?: string;
  status: SuggestedEdgeStatus;
  edge_id?: string;
  reviewed_at?: string;
  created_at: string;
}

export const PARLEMENTAIR_ITEM_STATUS_LABELS: Record<ParlementairItemStatus, string> = {
  pending: 'In wachtrij',
  imported: 'Geïmporteerd',
  reviewed: 'Beoordeeld',
  rejected: 'Afgewezen',
  out_of_scope: 'Buiten scope',
};

export const PARLEMENTAIR_ITEM_STATUS_COLORS: Record<ParlementairItemStatus, BadgeVariant> = {
  pending: 'amber',
  imported: 'blue',
  reviewed: 'green',
  rejected: 'gray',
  out_of_scope: 'gray',
};

// Access Requests
export type AccessRequestStatus = 'pending' | 'approved' | 'denied';

export interface AccessRequest {
  id: string;
  email: string;
  naam: string;
  status: AccessRequestStatus;
  requested_at: string;
  reviewed_at?: string | null;
  reviewed_by_id?: string | null;
  deny_reason?: string | null;
}

// Node sub-detail types (parlementair item, bron, bijlage)
export interface NodeParlementairItem {
  type: string;
  indieners: string[];
  document_url: string | null;
  zaak_nummer: string;
  bron: string;
  datum: string | null;
  deadline: string | null;
  ministerie: string | null;
}

export interface NodeBronDetail {
  type: string;
  auteur: string | null;
  publicatie_datum: string | null;
  url: string | null;
}

export interface BijlageInfo {
  id: string;
  bestandsnaam: string;
  content_type: string;
  bestandsgrootte: number;
  created_at: string;
}

// LLM suggestion types
export interface TagSuggestionRequest {
  title: string;
  description?: string | null;
  node_type?: string;
}

export interface TagSuggestionResponse {
  matched_tags: string[];
  suggested_new_tags: string[];
  available: boolean;
}

export interface EdgeSuggestionItem {
  target_node_id: string;
  target_node_title: string;
  target_node_type: string;
  confidence: number;
  suggested_edge_type: string;
  reason: string;
}

// Gap detection (B3)
export interface GapItem {
  step_number: number;
  step_question: string;
  missing_types: string[];
  present_types: string[];
  has_stakeholders: boolean;
}

export interface GapAnalysisResponse {
  gaps: GapItem[];
  completed_count: number;
  total_steps: number;
  narrative: string;
  recommendations: string[];
  available: boolean;
}

export interface CorpusGapSummaryItem {
  dossier_id: string;
  dossier_title: string;
  completed_count: number;
  total_steps: number;
  has_stakeholders: boolean;
}

export interface CorpusGapOverviewResponse {
  items: CorpusGapSummaryItem[];
  total: number;
}

// Kompas guidance (A5)
export interface KompasGuidanceResponse {
  suggestions: EdgeSuggestionItem[];
  available: boolean;
}

// Similar nodes (A3)
export interface SimilarNodeItem {
  id: string;
  title: string;
  node_type: string;
  similarity: number;
}

export interface SimilarNodesResponse {
  items: SimilarNodeItem[];
}

// Mention types
export interface MentionSearchResult {
  id: string;
  label: string;
  type: string;
  subtitle?: string;
}

export interface MentionReference {
  source_type: string;
  source_id: string;
  source_title: string;
}

// Edge Schema Rules
export interface EdgeSchemaRule {
  id: string;
  from_node_type: string;
  to_node_type: string;
  edge_type_id: string;
}

export interface EdgeSchemaRuleCreate {
  from_node_type: string;
  to_node_type: string;
  edge_type_id: string;
}

export interface ValidEdgeTypesResponse {
  edge_type_ids: string[];
  schema_active: boolean;
}

// Filter types
export interface EdgeFilters {
  from_node_id?: string;
  to_node_id?: string;
  edge_type_id?: string;
  node_id?: string;
}

export interface TaskFilters {
  status?: TaskStatus;
  priority?: TaskPriority;
  assignee_id?: string;
  node_id?: string;
  organisatie_eenheid_id?: string;
  opdracht_id?: string;
  include_children?: boolean;
}

export interface ActivityFeedParams {
  [key: string]: string | number | boolean | undefined;
  skip?: number;
  limit?: number;
  event_type?: string;
  actor_id?: string;
}

export interface ParlementairItemFilters {
  status?: string;
  bron?: string;
  type?: string;
  search?: string;
}

// Parlementair review types
export interface ReprocessResult {
  total: number;
  matched: number;
  out_of_scope: number;
  skipped: number;
  error?: string;
}

export interface CompleteReviewData {
  eigenaar_id: string;
  tasks?: { title: string; description?: string; assignee_id?: string; deadline?: string }[];
}

// Notification types
export interface ReactionSummary {
  emoji: string;
  count: number;
  sender_names: string[];
  reacted_by_me: boolean;
}

export interface Notification {
  id: string;
  person_id: string;
  sender_id?: string;
  sender_name?: string;
  type: string;
  title: string;
  message?: string;
  is_read: boolean;
  related_node_id?: string;
  related_task_id?: string;
  parent_id?: string;
  thread_id?: string;
  reply_count: number;
  created_at: string;
  last_activity_at?: string;
  last_message?: string;
  reactions: ReactionSummary[];
}

export interface UnreadCountResponse {
  count: number;
}

export interface DashboardStats {
  corpus_node_count: number;
  open_task_count: number;
  overdue_task_count: number;
  active_opdracht_budget: number;
}

// Import/Export types
export interface ImportResult {
  imported: number;
  skipped: number;
  errors: string[];
}

export interface DatabaseBackupInfo {
  exported_at: string;
  alembic_revision: string;
  format_version: number;
  encrypted: boolean;
}

export interface DatabaseRestoreResult {
  success: boolean;
  tables_restored: number;
  alembic_revision_from: string;
  alembic_revision_to: string;
  migrations_applied: number;
  message: string;
}

export interface DatabaseResetResult {
  success: boolean;
  tables_cleared: number;
  admin_persons_created: number;
  message: string;
}

// WebAuthn types
export interface WebAuthnCredential {
  id: string;
  label: string;
  created_at: string;
  last_used_at: string | null;
}

// Externe Organisatie
export enum ExterneOrganisatieType {
  UITVOERINGSORGANISATIE = 'uitvoeringsorganisatie',
  ZBO = 'zbo',
  KOEPELORGANISATIE = 'koepelorganisatie',
  STICHTING = 'stichting',
  MARKTPARTIJ = 'marktpartij',
  OVERIG = 'overig',
}

export const EXTERNE_ORG_TYPE_LABELS: Record<ExterneOrganisatieType, string> = {
  [ExterneOrganisatieType.UITVOERINGSORGANISATIE]: 'Uitvoeringsorganisatie',
  [ExterneOrganisatieType.ZBO]: 'ZBO',
  [ExterneOrganisatieType.KOEPELORGANISATIE]: 'Koepelorganisatie',
  [ExterneOrganisatieType.STICHTING]: 'Stichting',
  [ExterneOrganisatieType.MARKTPARTIJ]: 'Marktpartij',
  [ExterneOrganisatieType.OVERIG]: 'Overig',
};

export const EXTERNE_ORG_TYPE_COLORS: Record<ExterneOrganisatieType, BadgeVariant> = {
  [ExterneOrganisatieType.UITVOERINGSORGANISATIE]: 'blue',
  [ExterneOrganisatieType.ZBO]: 'purple',
  [ExterneOrganisatieType.KOEPELORGANISATIE]: 'green',
  [ExterneOrganisatieType.STICHTING]: 'amber',
  [ExterneOrganisatieType.MARKTPARTIJ]: 'cyan',
  [ExterneOrganisatieType.OVERIG]: 'gray',
};

export interface ExterneOrganisatie {
  id: string;
  naam: string;
  afkorting?: string | null;
  type: string;
  kvk_nummer?: string | null;
  website?: string | null;
  beschrijving?: string | null;
  created_at: string;
}

export interface ExterneOrganisatieCreate {
  naam: string;
  afkorting?: string | null;
  type: ExterneOrganisatieType;
  kvk_nummer?: string | null;
  website?: string | null;
  beschrijving?: string | null;
}

export interface ExterneOrganisatieUpdate {
  naam?: string;
  afkorting?: string | null;
  type?: ExterneOrganisatieType;
  kvk_nummer?: string | null;
  website?: string | null;
  beschrijving?: string | null;
}

// Opdracht
export enum OpdrachtType {
  OPDRACHT = 'opdracht',
  SUBSIDIE = 'subsidie',
}

export const OPDRACHT_TYPE_LABELS: Record<OpdrachtType, string> = {
  [OpdrachtType.OPDRACHT]: 'Opdracht',
  [OpdrachtType.SUBSIDIE]: 'Subsidie',
};

export const OPDRACHT_TYPE_COLORS: Record<OpdrachtType, BadgeVariant> = {
  [OpdrachtType.OPDRACHT]: 'blue',
  [OpdrachtType.SUBSIDIE]: 'green',
};

export enum OpdrachtStatus {
  CONCEPT = 'concept',
  ACTIEF = 'actief',
  AFGEROND = 'afgerond',
  VERANTWOORD = 'verantwoord',
  GEANNULEERD = 'geannuleerd',
}

export const OPDRACHT_STATUS_LABELS: Record<OpdrachtStatus, string> = {
  [OpdrachtStatus.CONCEPT]: 'Concept',
  [OpdrachtStatus.ACTIEF]: 'Actief',
  [OpdrachtStatus.AFGEROND]: 'Afgerond',
  [OpdrachtStatus.VERANTWOORD]: 'Verantwoord',
  [OpdrachtStatus.GEANNULEERD]: 'Geannuleerd',
};

export const OPDRACHT_STATUS_COLORS: Record<OpdrachtStatus, BadgeVariant> = {
  [OpdrachtStatus.CONCEPT]: 'slate',
  [OpdrachtStatus.ACTIEF]: 'blue',
  [OpdrachtStatus.AFGEROND]: 'green',
  [OpdrachtStatus.VERANTWOORD]: 'emerald',
  [OpdrachtStatus.GEANNULEERD]: 'gray',
};

export enum Kostensoort {
  INVESTERING = 'investering',
  EXPLOITATIE = 'exploitatie',
  GEMENGD = 'gemengd',
}

export const KOSTENSOORT_LABELS: Record<Kostensoort, string> = {
  [Kostensoort.INVESTERING]: 'Investering',
  [Kostensoort.EXPLOITATIE]: 'Exploitatie',
  [Kostensoort.GEMENGD]: 'Gemengd',
};

export interface OpdrachtNodeResponse {
  id: string;
  opdracht_id: string;
  node_id: string;
  relatie_type: string;
  node_title?: string | null;
  node_type?: string | null;
}

export interface OpdrachtNodeCreate {
  node_id: string;
  relatie_type?: string;
}

export interface Opdracht {
  id: string;
  type: string;
  titel: string;
  beschrijving?: string | null;
  begrotingsjaar: number;
  budget?: number | null;
  gerealiseerd?: number | null;
  kostensoort?: string | null;
  volgend_jaar_benodigd?: number | null;
  volgend_jaar_aangevraagd?: number | null;
  instrument_id: string;
  instrument?: { id: string; title: string; node_type: string } | null;
  opdrachtnemer_id?: string | null;
  opdrachtnemer?: ExterneOrganisatie | null;
  opdrachtgever_id?: string | null;
  opdrachtgever?: { id: string; naam: string } | null;
  verantwoordelijke_id?: string | null;
  verantwoordelijke?: { id: string; naam: string } | null;
  subsidieregeling?: string | null;
  beschikking_nummer?: string | null;
  status: string;
  referentie?: string | null;
  startdatum?: string | null;
  einddatum?: string | null;
  node_koppelingen?: OpdrachtNodeResponse[];
  created_at: string;
  updated_at?: string | null;
}

export interface OpdrachtCreate {
  type: OpdrachtType;
  titel: string;
  beschrijving?: string | null;
  begrotingsjaar: number;
  budget?: number | null;
  gerealiseerd?: number | null;
  kostensoort?: Kostensoort | null;
  volgend_jaar_benodigd?: number | null;
  volgend_jaar_aangevraagd?: number | null;
  instrument_id: string;
  opdrachtnemer_id?: string | null;
  opdrachtgever_id?: string | null;
  verantwoordelijke_id?: string | null;
  subsidieregeling?: string | null;
  beschikking_nummer?: string | null;
  status?: OpdrachtStatus;
  referentie?: string | null;
  startdatum?: string | null;
  einddatum?: string | null;
  node_koppelingen?: OpdrachtNodeCreate[];
}

export interface OpdrachtUpdate {
  type?: OpdrachtType;
  titel?: string;
  beschrijving?: string | null;
  begrotingsjaar?: number;
  budget?: number | null;
  gerealiseerd?: number | null;
  kostensoort?: Kostensoort | null;
  volgend_jaar_benodigd?: number | null;
  volgend_jaar_aangevraagd?: number | null;
  instrument_id?: string;
  opdrachtnemer_id?: string | null;
  opdrachtgever_id?: string | null;
  verantwoordelijke_id?: string | null;
  subsidieregeling?: string | null;
  beschikking_nummer?: string | null;
  status?: OpdrachtStatus;
  referentie?: string | null;
  startdatum?: string | null;
  einddatum?: string | null;
}

export interface OpdrachtFilters {
  begrotingsjaar?: number;
  type?: string;
  status?: string;
  instrument_id?: string;
  opdrachtnemer_id?: string;
  opdrachtgever_id?: string;
  verantwoordelijke_id?: string;
}

// Financieel Overzicht
export interface FinancieelJaar {
  begrotingsjaar: number;
  budget: number;
  gerealiseerd: number;
  volgend_jaar_benodigd: number;
  volgend_jaar_aangevraagd: number;
  opdracht_count: number;
}

export interface OpdrachtenSummary {
  count: number;
  totaal_budget: number;
  totaal_gerealiseerd: number;
  uitnutting_percentage?: number | null;
}

export interface FinancieelOverzicht {
  node_id: string;
  node_title: string;
  node_type: string;
  totaal_budget: number;
  totaal_gerealiseerd: number;
  uitnutting_percentage?: number | null;
  per_jaar: FinancieelJaar[];
}

// Lead Stage enum and labels
export enum LeadStage {
  VERKENNEN = 'verkennen',
  EERSTE_GESPREK = 'eerste_gesprek',
  INTERNE_CHECK = 'interne_check',
  FOLLOW_UP = 'follow_up',
  IN_THE_POCKET = 'in_the_pocket',
  KOELKAST = 'koelkast',
}

export const LEAD_STAGE_LABELS: Record<LeadStage, string> = {
  [LeadStage.VERKENNEN]: 'Verkennen',
  [LeadStage.EERSTE_GESPREK]: 'Eerste gesprek',
  [LeadStage.INTERNE_CHECK]: 'Interne check',
  [LeadStage.FOLLOW_UP]: 'Follow-up',
  [LeadStage.IN_THE_POCKET]: 'In the pocket',
  [LeadStage.KOELKAST]: 'Koelkast',
};

export const LEAD_STAGE_COLORS: Record<LeadStage, string> = {
  [LeadStage.VERKENNEN]: 'bg-blue-100 text-blue-800',
  [LeadStage.EERSTE_GESPREK]: 'bg-yellow-100 text-yellow-800',
  [LeadStage.INTERNE_CHECK]: 'bg-orange-100 text-orange-800',
  [LeadStage.FOLLOW_UP]: 'bg-purple-100 text-purple-800',
  [LeadStage.IN_THE_POCKET]: 'bg-green-100 text-green-800',
  [LeadStage.KOELKAST]: 'bg-gray-100 text-gray-800',
};

export const LEAD_STAGE_ORDER: LeadStage[] = [
  LeadStage.VERKENNEN,
  LeadStage.EERSTE_GESPREK,
  LeadStage.INTERNE_CHECK,
  LeadStage.FOLLOW_UP,
  LeadStage.IN_THE_POCKET,
  LeadStage.KOELKAST,
];

export enum LeadActivityType {
  NOTE = 'note',
  STAGE_CHANGE = 'stage_change',
  MEETING = 'meeting',
  CALL = 'call',
  EMAIL = 'email',
}

export const LEAD_ACTIVITY_TYPE_LABELS: Record<LeadActivityType, string> = {
  [LeadActivityType.NOTE]: 'Notitie',
  [LeadActivityType.STAGE_CHANGE]: 'Stage wijziging',
  [LeadActivityType.MEETING]: 'Meeting',
  [LeadActivityType.CALL]: 'Telefoongesprek',
  [LeadActivityType.EMAIL]: 'E-mail',
};

export interface LeadAssigneeSummary {
  id: string;
  naam: string;
}

export interface LeadInitiatiefSummary {
  id: string;
  naam: string;
  kleur: string | null;
}

export interface LeadExterneOrgSummary {
  id: string;
  naam: string;
  type: string | null;
}

export interface LeadAttachment {
  id: string;
  lead_id: string;
  bestandsnaam: string;
  content_type: string;
  bestandsgrootte: number;
  created_at: string;
}

export interface LeadContact {
  id: string;
  person_id: string;
  person_naam: string;
  rol: string;
  created_at: string;
}

export interface LeadNode {
  id: string;
  node_id: string;
  node_title: string;
  node_type: string;
  created_at: string;
}

export interface LeadActivity {
  id: string;
  lead_id: string;
  author_id: string | null;
  author_naam: string | null;
  content: string;
  activity_type: LeadActivityType;
  metadata_: Record<string, unknown>;
  created_at: string;
}

export interface Lead {
  id: string;
  title: string;
  description: string | null;
  organization: string | null;
  externe_organisatie_id: string | null;
  externe_organisatie: LeadExterneOrgSummary | null;
  stage: LeadStage;
  assignee_id: string | null;
  assignee: LeadAssigneeSummary | null;
  brought_by_id: string | null;
  brought_by: LeadAssigneeSummary | null;
  initiatief_id: string | null;
  initiatief: LeadInitiatiefSummary | null;
  next_action: string | null;
  next_action_date: string | null;
  tags: string[];
  sort_order: number;
  raw_intake_text: string | null;
  attachment_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface LeadDetail extends Lead {
  activities: LeadActivity[];
  attachments: LeadAttachment[];
  contacts: LeadContact[];
  linked_nodes: LeadNode[];
}

export interface LeadCreate {
  title: string;
  description?: string | null;
  organization?: string | null;
  externe_organisatie_id?: string | null;
  stage?: LeadStage;
  assignee_id?: string | null;
  brought_by_id?: string | null;
  next_action?: string | null;
  next_action_date?: string | null;
  raw_intake_text?: string | null;
  initiatief_id?: string | null;
  created_at?: string | null;
}

export interface LeadUpdate {
  title?: string;
  description?: string | null;
  organization?: string | null;
  externe_organisatie_id?: string | null;
  stage?: LeadStage;
  assignee_id?: string | null;
  brought_by_id?: string | null;
  next_action?: string | null;
  next_action_date?: string | null;
  raw_intake_text?: string | null;
  initiatief_id?: string | null;
}

export interface LeadActivityCreate {
  content: string;
  activity_type?: LeadActivityType;
}

export interface LeadMetrics {
  total: number;
  by_stage: Record<string, number>;
  stale_count: number;
}

export interface LeadFilters {
  stage?: string;
  tag?: string;
  assignee_id?: string;
  date_from?: string;
  date_to?: string;
  next_action_filter?: string;  // "overdue" | "today" | "this_week"
  sort_by?: string;  // "created_at" | "updated_at" | "next_action_date" | "stage"
  initiatief_id?: string;
}

export interface LeadTimelineEvent {
  id: string;
  lead_id: string;
  lead_title: string;
  event_type: 'created' | 'stage_change' | 'note' | 'meeting' | 'call' | 'email';
  timestamp: string;
  actor_naam: string | null;
  content: string | null;
  from_stage: string | null;
  to_stage: string | null;
  organization: string | null;
  stage: string;
  assignee_naam: string | null;
}

export interface LeadTimelineResponse {
  events: LeadTimelineEvent[];
  total: number;
  earliest: string | null;
  latest: string | null;
}

// ---------------------------------------------------------------------------
// Initiatief
// ---------------------------------------------------------------------------

export interface Initiatief {
  id: string;
  naam: string;
  beschrijving: string | null;
  kleur: string | null;
  created_by_id: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface InitiatiefCreate {
  naam: string;
  beschrijving?: string | null;
  kleur?: string | null;
}

export interface InitiatiefUpdate {
  naam?: string;
  beschrijving?: string | null;
  kleur?: string | null;
}

export interface InitiatiefMember {
  initiatief_id: string;
  person_id: string;
  person_naam: string;
  rol: string;
  created_at: string;
}

export interface InitiatiefEenheid {
  initiatief_id: string;
  eenheid_id: string;
  eenheid_naam: string;
  rol: string;
  created_at: string;
}

export interface InitiatiefDetail extends Initiatief {
  members: InitiatiefMember[];
  eenheden: InitiatiefEenheid[];
  access_level: 'eigenaar' | 'contributor' | 'viewer' | null;
}

export const INITIATIEF_COLORS = [
  '#3B82F6', // blue
  '#10B981', // green
  '#F59E0B', // amber
  '#EF4444', // red
  '#8B5CF6', // purple
  '#EC4899', // pink
  '#06B6D4', // cyan
  '#F97316', // orange
];

export interface LeadParseResult {
  title: string | null;
  organization: string | null;
  description: string | null;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  original_date: string | null;
  suggested_tags: string[];
  addressed_to: string | null;
}

// Community Graph types (used by LeadGraphView / CommunityGraph)
export interface CommunityGraphNode {
  id: string; // prefixed: "lead-xxx", "person-xxx", "org-xxx", "node-xxx"
  node_type: 'lead' | 'person' | 'organisation' | 'corpus_node';
  label: string;
  stage?: string | null;
  initiatief_id?: string | null;
  functie?: string | null;
  org_type?: string | null;
  corpus_node_type?: string | null;
}

export interface CommunityGraphEdge {
  id: string;
  source: string;
  target: string;
  edge_type: string;
  label?: string | null;
}

export interface CommunityGraphResponse {
  nodes: CommunityGraphNode[];
  edges: CommunityGraphEdge[];
}
