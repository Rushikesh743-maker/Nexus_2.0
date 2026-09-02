import { clsx } from 'clsx';

/** Merge conditional class names. */
export function cn(...inputs) {
  return clsx(inputs);
}

const dateFmt = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
const timeFmt = new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });

export function formatDate(value) {
  if (!value) return '—';
  return dateFmt.format(new Date(value));
}

export function formatTime(value) {
  if (!value) return '—';
  return timeFmt.format(new Date(value));
}

export function formatDateTime(value) {
  if (!value) return '—';
  const d = new Date(value);
  return `${dateFmt.format(d)} · ${timeFmt.format(d)}`;
}

export function timeAgo(value) {
  if (!value) return '—';
  const seconds = (Date.now() - new Date(value).getTime()) / 1000;
  if (seconds < 60) return 'just now';
  const minutes = seconds / 60;
  if (minutes < 60) return `${Math.floor(minutes)}m ago`;
  const hours = minutes / 60;
  if (hours < 24) return `${Math.floor(hours)}h ago`;
  const days = hours / 24;
  if (days < 7) return `${Math.floor(days)}d ago`;
  return formatDate(value);
}

export function initials(name = '') {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('');
}

export function hashString(str = '') {
  let h = 0;
  for (const ch of str) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return Math.abs(h);
}

export function truncate(str = '', max = 28) {
  return str.length > max ? `${str.slice(0, max - 1)}…` : str;
}

/** Human-readable file size. */
export function formatFileSize(bytes) {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb >= 100 ? Math.round(kb) : kb.toFixed(1)} KB`;
  return `${(kb / 1024).toFixed(1)} MB`;
}
