import { Link } from 'react-router-dom';
import { buttonClasses } from '@/components/ui/Button';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';

export function NotFoundPage() {
  useDocumentTitle('Page not found');
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 px-6 text-center">
      <p className="text-[88px] font-bold leading-none text-navy-100">404</p>
      <h1 className="mt-2 text-lg font-semibold text-navy-800">This page does not exist</h1>
      <p className="mt-1.5 max-w-sm text-sm text-navy-400">
        The address may have been mistyped, or the record was moved or archived.
      </p>
      <div className="mt-6 flex items-center gap-2">
        <Link to="/dashboard" className={buttonClasses('primary', 'md')}>
          Go to dashboard
        </Link>
        <Link to="/investigations" className={buttonClasses('outline', 'md')}>
          Browse investigations
        </Link>
      </div>
    </div>
  );
}
