/**
 * Bridge from this app's icon names to `nldd-icon`.
 *
 * The design system ships a closed set (359 icons + 318 aliases). Every name in
 * the map below is checked against that set; do not invent one, an unknown name
 * renders nothing at all, with no error.
 *
 * `nldd-icon` sizes in pixels, so the `size` prop maps this app's named scales
 * onto them.
 */
import type { CSSProperties } from 'react';

/**
 * Named icon scales, in pixels.
 *
 * nldd-icon only accepts spacer-aligned sizes (16, 20, 24, 28, 32, 40, ...),
 * so `xs` and `sm` both land on 16: that is the design system's grid, not an
 * approximation to work around.
 */
export const ICON_SIZES = {
  xs: '16', // the smallest supported size
  sm: '16',
  md: '16', // by far the most common
  lg: '20',
  xl: '24',
} as const;

export type IconSize = keyof typeof ICON_SIZES;

/**
 * lucide name -> nldd-icon name.
 *
 * Eight lucide icons have no counterpart in the NLDD set. Each is mapped to the
 * nearest honest neighbour and flagged here so the choice is visible rather than
 * buried:
 *   Bot         -> sparkles   (used for AI actions; 'cpu' read as hardware)
 *   Briefcase   -> business-suitcase
 *   Compass     -> signpost   (wayfinding, same intent)
 *   Fingerprint -> key        (WebAuthn/passkey settings)
 *   Hash        -> tag        (hashtag mentions are tags in this domain)
 *   Merge       -> git-merge
 *   Phone       -> at         (contact detail; no telephone glyph exists)
 *   Wallet      -> euro-sign  (financial context)
 */
export const ICON_MAP = {
  AlertTriangle: 'exclamation-triangle',
  ArrowLeft: 'arrow-left',
  ArrowLeftRight: 'arrow-left-right',
  ArrowRight: 'arrow-right',
  Bell: 'bell',
  BellOff: 'bell',
  BellRing: 'bell',
  Blocks: 'blocks-9',
  BookOpen: 'book',
  Bot: 'sparkles',
  Briefcase: 'business-suitcase',
  Building2: 'apartment-building',
  Calendar: 'calendar',
  CalendarDays: 'calendar-event',
  Camera: 'photo-camera',
  Check: 'check-mark',
  CheckCheck: 'check-list',
  CheckCircle: 'check-mark-circle',
  CheckCircle2: 'check-mark-circle',
  CheckSquare: 'check-list',
  ChevronDown: 'chevron-down',
  ChevronLeft: 'chevron-left',
  ChevronRight: 'chevron-right',
  ChevronUp: 'chevron-up',
  Circle: 'circle',
  ClipboardList: 'clipboard-bullet-list',
  Clock: 'clock',
  Cloud: 'cloud',
  Columns3: 'columns-3',
  Compass: 'signpost',
  Copy: 'copy',
  Database: 'database',
  Download: 'download',
  Euro: 'euro-sign',
  ExternalLink: 'external-link',
  Eye: 'eye',
  EyeOff: 'eye-slash',
  FileQuestion: 'question-mark-circle',
  FileSearch: 'file-text',
  FileText: 'file-text',
  Fingerprint: 'key',
  GitFork: 'git-fork',
  Globe: 'globe',
  Grid3x3: 'square-grid-3x3',
  Handshake: 'handshake',
  Hash: 'tag',
  Inbox: 'inbox',
  LayoutGrid: 'square-grid-2x2',
  LayoutList: 'list',
  Lightbulb: 'lightbulb',
  Link: 'link',
  Link2: 'link',
  LinkIcon: 'link',
  ListTree: 'tree-structure',
  Loader2: 'arrow-clockwise',
  Lock: 'lock-closed',
  LogOut: 'logout',
  Mail: 'envelope',
  Megaphone: 'megaphone',
  Menu: 'menu',
  Merge: 'git-merge',
  MessageCircle: 'message-rectangle-text',
  MessageSquare: 'message-rectangle-text',
  MinusCircle: 'minus-circle',
  Network: 'network-structure',
  Paperclip: 'paperclip',
  Pencil: 'pencil',
  Phone: 'at',
  Play: 'media-play',
  Plus: 'plus',
  RefreshCw: 'refresh',
  RotateCcw: 'arrow-u-turn-backward',
  Search: 'magnifier',
  SearchIcon: 'magnifier',
  Send: 'paper-plane',
  Settings: 'gear',
  Share2: 'share',
  Shield: 'shield',
  Smile: 'face-smiling',
  SmilePlus: 'face-smiling-badge-plus',
  Snowflake: 'snowflake',
  Sparkles: 'sparkles',
  Star: 'star',
  Tag: 'tag',
  Terminal: 'terminal',
  Trash2: 'trash',
  TrendingUp: 'chart-x-y-axis-line',
  Undo2: 'undo',
  Unlink: 'link',
  Upload: 'upload',
  User: 'person',
  UserPlus: 'person-badge-plus',
  Users: 'users',
  Volume2: 'speaker-volume-high',
  VolumeOff: 'mute',
  Wallet: 'euro-sign',
  X: 'close',
  XCircle: 'dismiss-circle',
} as const satisfies Record<string, string>;

export type LucideName = keyof typeof ICON_MAP;

interface IconProps {
  /** An nldd-icon name, or a lucide name that the map translates. */
  name: LucideName | (string & {});
  /** A scale from ICON_SIZES, or an nldd-icon size ('full', 'inherit', '24'). */
  size?: IconSize | NlddIconSize;
  /** Screen-reader label. Without one the icon is decorative and hidden. */
  label?: string;
  /**
   * An nldd-icon colour: a role ('secondary-content', 'critical', ...) or a
   * Rijkshuisstijl name. Forwarded so a call site never has to reach for an
   * inline style, which is how a hand-picked palette step ends up standing in
   * for a role that already exists.
   */
  color?: NonNullable<React.ComponentProps<'nldd-icon'>['color']>;
  className?: string;
  style?: CSSProperties;
}

/** The sizes nldd-icon itself accepts: spacer-aligned pixels, or a keyword. */
type NlddIconSize =
  | 'full'
  | 'inherit'
  | '16'
  | '20'
  | '24'
  | '28'
  | '32'
  | '40'
  | '44'
  | '48'
  | '56'
  | '64'
  | '80'
  | '96';

/**
 * Renders an `nldd-icon`, accepting either an NLDD name or a lucide one.
 *
 * Accepting both keeps the screen-by-screen conversion incremental: a file can
 * move to `<Icon name="Trash2" />` without every name being decided up front,
 * and settle on `<Icon name="trash" />` later.
 */
export function Icon({ name, size = 'md', label, color, className, style }: IconProps) {
  const resolved = (ICON_MAP as Record<string, string>)[name] ?? name;
  const px = size in ICON_SIZES ? ICON_SIZES[size as IconSize] : (size as NlddIconSize);

  return (
    <nldd-icon
      name={resolved}
      size={px}
      className={className}
      style={style}
      {...(color ? { color } : {})}
      {...(label ? { 'accessible-label': label } : { 'aria-hidden': true })}
    />
  );
}
