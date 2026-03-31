/**
 * Client-side parsing of .eml and .msg email files dropped from Outlook.
 * Extracts subject, sender, date, body text and attachments.
 */

export interface ParsedEmail {
  subject: string;
  senderName: string;
  senderEmail: string;
  date: string | null;
  bodyText: string;
  bodyHtml: string | null;
  attachments: File[];
}

export function isEmailFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return name.endsWith('.eml') || name.endsWith('.msg');
}

function isEmlFile(file: File): boolean {
  return file.name.toLowerCase().endsWith('.eml');
}

function isMsgFile(file: File): boolean {
  return file.name.toLowerCase().endsWith('.msg');
}

/**
 * Parse a .eml file using postal-mime (lazy-loaded).
 */
async function parseEml(file: File): Promise<ParsedEmail> {
  const { default: PostalMime } = await import('postal-mime');
  const buffer = await file.arrayBuffer();
  const email = await PostalMime.parse(buffer);

  const from = email.from;
  const attachments: File[] = [];
  for (const att of email.attachments) {
    if (att.disposition === 'inline' && !att.filename) continue;
    const blob = new Blob([att.content as BlobPart], { type: att.mimeType });
    attachments.push(new File([blob], att.filename ?? 'bijlage', { type: att.mimeType }));
  }

  return {
    subject: email.subject ?? '',
    senderName: from?.name ?? '',
    senderEmail: from?.address ?? '',
    date: email.date ?? null,
    bodyText: email.text ?? '',
    bodyHtml: email.html ?? null,
    attachments,
  };
}

/**
 * Parse a .msg file using @kenjiuno/msgreader (lazy-loaded).
 */
async function parseMsg(file: File): Promise<ParsedEmail> {
  const { default: MsgReader } = await import('@kenjiuno/msgreader');
  const buffer = await file.arrayBuffer();
  const reader = new MsgReader(buffer);
  const data = reader.getFileData();

  const attachments: File[] = [];
  if (data.attachments) {
    for (const attField of data.attachments) {
      const att = reader.getAttachment(attField);
      if (!att.fileName) continue;
      const blob = new Blob([att.content as BlobPart]);
      attachments.push(new File([blob], att.fileName));
    }
  }

  return {
    subject: data.subject ?? '',
    senderName: data.senderName ?? '',
    senderEmail: data.senderSmtpAddress ?? data.senderEmail ?? '',
    date: data.clientSubmitTime ?? data.messageDeliveryTime ?? data.creationTime ?? null,
    bodyText: data.body ?? '',
    bodyHtml: data.bodyHtml ?? null,
    attachments,
  };
}

/**
 * Parse an email file (.eml or .msg) and return structured data.
 * Libraries are lazy-loaded to avoid bloating the main bundle.
 */
export async function parseEmailFile(file: File): Promise<ParsedEmail> {
  if (isEmlFile(file)) return parseEml(file);
  if (isMsgFile(file)) return parseMsg(file);
  throw new Error(`Onbekend e-mailformaat: ${file.name}`);
}

/**
 * Build a text summary suitable for passing to VLAM as rawText.
 */
export function emailToRawText(email: ParsedEmail): string {
  const lines: string[] = [];
  if (email.subject) lines.push(`Onderwerp: ${email.subject}`);
  if (email.senderName || email.senderEmail) {
    const sender = email.senderName
      ? `${email.senderName} <${email.senderEmail}>`
      : email.senderEmail;
    lines.push(`Van: ${sender}`);
  }
  if (email.date) lines.push(`Datum: ${email.date}`);
  lines.push('');
  lines.push(email.bodyText);
  return lines.join('\n');
}
