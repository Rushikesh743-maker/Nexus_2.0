import { Badge } from '@/components/ui/Badge';
import { CASE_STATUS_TONE, CASE_PRIORITY_TONE } from '@/lib/caseTypes';

export function StatusBadge({ status }) {
  return <Badge variant={CASE_STATUS_TONE[status] || 'neutral'}>{status}</Badge>;
}

export function PriorityBadge({ priority }) {
  return <Badge variant={CASE_PRIORITY_TONE[priority] || 'neutral'}>{priority}</Badge>;
}
