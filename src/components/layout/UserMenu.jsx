import { useNavigate } from 'react-router-dom';
import { Settings, LogOut, ChevronDown } from 'lucide-react';
import { Dropdown, DropdownItem, DropdownDivider, DropdownLabel } from '@/components/ui/Dropdown';
import { Avatar } from '@/components/ui/Avatar';
import { useAuth } from '@/context/AuthContext';
import { useToast } from '@/context/ToastContext';

export function UserMenu() {
  const { user, logout } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    toast.info('Signed out', 'Your demo session was cleared.');
  };

  return (
    <Dropdown
      width={224}
      trigger={
        <button
          type="button"
          className="flex items-center gap-2.5 rounded-lg py-1 pl-1 pr-2 transition-colors hover:bg-slate-100"
          aria-label="Account menu"
        >
          <Avatar name={user?.name || ''} size="sm" />
          <span className="hidden text-left lg:block">
            <span className="block text-[13px] font-semibold leading-tight text-navy-800">{user?.name}</span>
            <span className="block text-[11px] leading-tight text-navy-400">{user?.role}</span>
          </span>
          <ChevronDown className="h-3.5 w-3.5 text-navy-300" aria-hidden />
        </button>
      }
    >
      <DropdownLabel>{user?.email}</DropdownLabel>
      <DropdownItem icon={Settings} label="Settings" onClick={() => navigate('/settings')} />
      <DropdownDivider />
      <DropdownItem icon={LogOut} label="Sign out" variant="danger" onClick={handleLogout} />
    </Dropdown>
  );
}
