import { ACCOUNTS } from '../types';

const STYLES: Record<string, string> = {
  'badge-ent': 'bg-yellow-100 text-yellow-800',
  'badge-gro': 'bg-green-100 text-green-800',
  'badge-std': 'bg-blue-100 text-blue-800',
  'badge-int': 'bg-purple-100 text-purple-800',
};

interface Props { accountId: string; className?: string }

export default function Badge({ accountId, className = '' }: Props) {
  const meta = ACCOUNTS[accountId];
  if (!meta) return null;
  const style = STYLES[meta.badgeCls] ?? 'bg-slate-100 text-slate-700';
  return (
    <span className={`inline-flex items-center gap-1 text-[0.67rem] font-semibold px-2.5 py-0.5 rounded-full whitespace-nowrap ${style} ${className}`}>
      {meta.badgeText}
    </span>
  );
}
