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
  [NodeType.NOTITIE]: 'Notitie',
  [NodeType.OVERIG]: 'Overig',
};

export const NODE_TYPE_COLORS: Record<NodeType, string> = {
  [NodeType.DOSSIER]: 'blue',
  [NodeType.DOEL]: 'green',
  [NodeType.INSTRUMENT]: 'purple',
  [NodeType.BELEIDSKADER]: 'amber',
  [NodeType.MAATREGEL]: 'cyan',
  [NodeType.POLITIEKE_INPUT]: 'rose',
  [NodeType.PROBLEEM]: 'red',
  [NodeType.EFFECT]: 'emerald',
  [NodeType.BELEIDSOPTIE]: 'indigo',
  [NodeType.NOTITIE]: 'slate',
  [NodeType.OVERIG]: 'gray',
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

export const TASK_PRIORITY_COLORS: Record<TaskPriority, string> = {
  [TaskPriority.KRITIEK]: 'red',
  [TaskPriority.HOOG]: 'orange',
  [TaskPriority.NORMAAL]: 'blue',
  [TaskPriority.LAAG]: 'gray',
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
  subtasks?: TaskSubtask[];
  node_id?: string;
  node?: CorpusNode;
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
  node_id: string;
}

export interface TaskUpdate {
  title?: string;
  description?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  due_date?: string;
  assignee_id?: string;
  organisatie_eenheid_id?: string;
  parent_id?: string;
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

export const ORGANISATIE_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'ministerie', label: 'Ministerie' },
  { value: 'directoraat_generaal', label: 'Directoraat-Generaal' },
  { value: 'directie', label: 'Directie' },
  { value: 'dienst', label: 'Dienst' },
  { value: 'bureau', label: 'Bureau' },
  { value: 'afdeling', label: 'Afdeling' },
  { value: 'cluster', label: 'Cluster' },
  { value: 'team', label: 'Team' },
];

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
  communicatieadviseur: 'Communicatieadviseur',
};

// People
export interface Person {
  id: string;
  naam: string;
  email?: string;
  functie?: string;
  description?: string;
  is_agent: boolean;
  api_key?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface PersonCreate {
  naam: string;
  email?: string;
  functie?: string;
  description?: string;
  is_agent?: boolean;
  api_key?: string;
}

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
};

// Activity
export interface Activity {
  id: string;
  action: string;
  description: string;
  node_id?: string;
  node?: CorpusNode;
  person_id?: string;
  person?: Person;
  created_at: string;
}

// Inbox
export interface InboxItem {
  id: string;
  type: string;
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
export interface SearchResult {
  id: string;
  title: string;
  node_type: NodeType;
  description?: string;
  score: number;
  highlights?: string[];
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

export const PARLEMENTAIR_TYPE_COLORS: Record<string, string> = {
  motie: 'rose',
  kamervraag: 'blue',
  toezegging: 'amber',
  amendement: 'purple',
  commissiedebat: 'cyan',
  schriftelijk_overleg: 'slate',
  interpellatie: 'red',
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

export const PARLEMENTAIR_ITEM_STATUS_COLORS: Record<ParlementairItemStatus, string> = {
  pending: 'amber',
  imported: 'blue',
  reviewed: 'green',
  rejected: 'gray',
  out_of_scope: 'gray',
};
