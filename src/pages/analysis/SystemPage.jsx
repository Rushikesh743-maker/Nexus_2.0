import { useState } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  Database,
  Download,
  KeyRound,
  Link2,
  RefreshCw,
  UserCog,
  Lock,
} from 'lucide-react';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Tabs } from '@/components/ui/Tabs';
import { Table, TBody, Td, Th, THead, Tr } from '@/components/ui/Table';
import { EmptyState } from '@/components/ui/EmptyState';
import { AnalysisDisclosure, AnalysisError, AnalysisSkeleton } from '@/components/analysis/AnalysisState';
import { CapabilityStrip } from '@/components/analysis/CapabilityStrip';
import { useCnaResource } from '@/hooks/useCnaResource';
import { useToast } from '@/context/ToastContext';
import { cnaService } from '@/services';
import { CNA_ROLES } from '@/services/cnaService';
import { cn, formatDateTime } from '@/lib/utils';

const TABS = [
  { id: 'access', label: 'Access control', icon: UserCog },
  { id: 'audit', label: 'Audit log', icon: ShieldCheck },
  { id: 'integrations', label: 'Integrations', icon: Link2 },
  { id: 'storage', label: 'Storage & export', icon: Database },
];

/** Role switcher — the backend genuinely enforces this, it is not cosmetic. */
function RoleSwitcher({ onChange }) {
  const [token, setToken] = useState(cnaService.getRoleToken());

  function pick(next) {
    cnaService.setRoleToken(next);
    setToken(next);
    onChange?.(next);
  }

  return (
    <div className="space-y-2">
      {CNA_ROLES.map((r) => (
        <button
          key={r.token}
          type="button"
          onClick={() => pick(r.token)}
          className={cn(
            'flex w-full items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left transition-colors',
            token === r.token ? 'border-teal-500 bg-teal-50/50' : 'border-slate-200 hover:bg-slate-50'
          )}
        >
          <span
            className={cn(
              'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2',
              token === r.token ? 'border-teal-600' : 'border-slate-300'
            )}
          >
            {token === r.token && <span className="h-1.5 w-1.5 rounded-full bg-teal-600" />}
          </span>
          <span className="min-w-0">
            <span className="block text-[13px] font-medium text-navy-800">{r.label}</span>
            <span className="mt-0.5 block text-[12px] leading-relaxed text-navy-400">{r.description}</span>
          </span>
        </button>
      ))}
      <p className="pt-1 text-[12px] leading-relaxed text-navy-400">
        Every request carries this role. Permission is checked and an audit entry written before any answer is
        returned — so switching here genuinely changes what the API will hand back.
      </p>
    </div>
  );
}

export function SystemPage() {
  const toast = useToast();
  const [tab, setTab] = useState('access');
  const [roleNonce, setRoleNonce] = useState(0);
  const [authRef, setAuthRef] = useState('');
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [reloading, setReloading] = useState(false);

  const me = useCnaResource(() => cnaService.me(), [roleNonce]);
  const security = useCnaResource(() => cnaService.getSecurity(), [roleNonce]);
  const stats = useCnaResource(() => cnaService.getStats(), [roleNonce]);
  const audit = useCnaResource(() => cnaService.getAudit(200), [roleNonce], { enabled: tab === 'audit' });
  const verify = useCnaResource(() => cnaService.verifyAudit(), [roleNonce], { enabled: tab === 'audit' });
  const integrations = useCnaResource(() => cnaService.getIntegrations(), [roleNonce], {
    enabled: tab === 'integrations',
  });

  function onRoleChange() {
    setRoleNonce((n) => n + 1);
    setPreview(null);
    toast.info('Role switched', 'Every subsequent request is made as the new principal.');
  }

  async function fetchPreview(key) {
    setPreviewing(key);
    try {
      const result = await cnaService.previewIntegration(key, authRef);
      setPreview({ key, result });
      if (!result.ok) toast.warning('Fetch refused', result.error);
    } catch (e) {
      toast.error('Fetch failed', e.message);
    } finally {
      setPreviewing(null);
    }
  }

  async function exportCypher() {
    setExporting(true);
    try {
      const { bytes, headers } = await cnaService.downloadCypher();
      toast.success(
        `Cypher export written (${(bytes / 1024).toFixed(0)} KB)`,
        `${headers['x-export-nodes'] || '?'} nodes, ${headers['x-export-edges'] || '?'} edges — loadable into Neo4j as-is.`
      );
    } catch (e) {
      toast.error('Export failed', e.message);
    } finally {
      setExporting(false);
    }
  }

  async function rerunPipeline() {
    setReloading(true);
    try {
      const result = await cnaService.reload();
      toast.success('Pipeline re-run', `${result.nodes} entities, ${result.edges} relationships.`);
      stats.reload();
    } catch (e) {
      toast.error('Re-run failed', e.message);
    } finally {
      setReloading(false);
    }
  }

  const caps = stats.data?.capabilities;
  const backends = caps?.graph_backends;
  const auditSec = caps?.audit_security;

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="System"
          subtitle="Access control, the tamper-evident audit log, external adapters and storage — the parts that decide whether an answer can be trusted."
        />
        <CardBody>
          <Tabs tabs={TABS} value={tab} onChange={setTab} />
        </CardBody>
      </Card>

      {/* Access control */}
      {tab === 'access' && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader title="Acting as" subtitle="Switch role to see access control behave differently." />
            <CardBody className="space-y-4">
              <RoleSwitcher onChange={onRoleChange} />

              {me.loading && !me.data ? (
                <AnalysisSkeleton rows={2} />
              ) : me.error ? (
                <AnalysisError error={me.error} onRetry={me.reload} compact />
              ) : me.data ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50/70 px-3.5 py-3">
                  <p className="text-[13px] font-semibold text-navy-800">{me.data.name}</p>
                  <p className="mt-0.5 text-[12px] text-navy-400">
                    {me.data.role} · {me.data.unit} · badge {me.data.badge}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(me.data.permissions || []).map((p) => (
                      <Badge key={p} variant="teal">
                        {p}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Roles and permissions" subtitle="Defined in backend/app/auth.py." />
            <CardBody>
              {security.loading && !security.data ? (
                <AnalysisSkeleton rows={4} />
              ) : security.error ? (
                <AnalysisError error={security.error} onRetry={security.reload} compact />
              ) : (
                <div className="space-y-3">
                  {Object.entries(security.data?.roles || {}).map(([role, perms]) => (
                    <div key={role} className="rounded-lg border border-slate-200 p-3">
                      <p className="flex items-center gap-2 text-[13px] font-semibold text-navy-800">
                        {role}
                        {security.data?.your_role === role && <Badge variant="teal">you</Badge>}
                      </p>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {perms.map((p) => (
                          <Badge key={p} variant="neutral">
                            {p}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardBody>
          </Card>
        </div>
      )}

      {/* Audit */}
      {tab === 'audit' && (
        <div className="space-y-5">
          <Card>
            <CardHeader
              title="Hash-chain integrity"
              subtitle="Each entry links the hash of the previous one, so altering any entry breaks every hash after it."
              actions={
                <Button variant="outline" size="sm" icon={RefreshCw} onClick={() => { verify.reload(); audit.reload(); }}>
                  Re-verify
                </Button>
              }
            />
            <CardBody>
              {verify.loading && !verify.data ? (
                <AnalysisSkeleton rows={2} />
              ) : verify.error ? (
                <AnalysisError error={verify.error} onRetry={verify.reload} compact />
              ) : verify.data ? (
                <div
                  className={cn(
                    'flex items-start gap-3 rounded-lg border px-3.5 py-3',
                    verify.data.intact ? 'border-emerald-200 bg-emerald-50/50' : 'border-rose-200 bg-rose-50/50'
                  )}
                >
                  {verify.data.intact ? (
                    <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" aria-hidden />
                  ) : (
                    <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-rose-600" aria-hidden />
                  )}
                  <div className="min-w-0">
                    <p className="text-[13px] font-semibold text-navy-800">
                      {verify.data.intact ? 'Chain intact' : 'Chain broken'}
                    </p>
                    <p className="mt-0.5 text-[12px] text-navy-500">
                      {verify.data.entries} entries · head hash{' '}
                      <span className="font-mono">{verify.data.head_hash}</span>
                      {!verify.data.intact && verify.data.broken_at !== undefined && (
                        <> · first broken entry: #{verify.data.broken_at}</>
                      )}
                    </p>
                    <p className="mt-1.5 flex items-center gap-1.5 text-[12px] text-navy-400">
                      <Lock className="h-3.5 w-3.5" aria-hidden />
                      {verify.data.encryption?.at_rest_encryption
                        ? `Payloads encrypted at rest with ${verify.data.encryption.algorithm}. The chain covers the ciphertext, so integrity is verifiable by someone who cannot read the contents.`
                        : verify.data.encryption?.note}
                    </p>
                  </div>
                </div>
              ) : null}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Audit log" subtitle="Written before any answer is returned." />
            <CardBody className="p-0">
              {audit.loading && !audit.data ? (
                <div className="p-5">
                  <AnalysisSkeleton rows={7} />
                </div>
              ) : audit.error ? (
                <div className="p-5">
                  <AnalysisError error={audit.error} onRetry={audit.reload} compact />
                </div>
              ) : (audit.data || []).length === 0 ? (
                <EmptyState title="No audit entries" compact />
              ) : (
                <Table>
                  <THead>
                    <Tr>
                      <Th className="w-16">Seq</Th>
                      <Th className="w-44">When</Th>
                      <Th className="w-48">Who</Th>
                      <Th className="w-52">Action</Th>
                      <Th>Detail</Th>
                      <Th className="w-32">Hash</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {audit.data.map((e) => (
                      <Tr key={e.seq}>
                        <Td className="font-mono text-[12px] text-navy-400">{e.seq}</Td>
                        <Td className="text-[12px] text-navy-500">{formatDateTime(e.timestamp)}</Td>
                        <Td>
                          <span className="text-[12px] font-medium text-navy-800">{e.user}</span>
                          <span className="mt-0.5 block text-[11px] text-navy-400">
                            {e.role} · {e.badge}
                          </span>
                        </Td>
                        <Td>
                          <Badge variant="neutral">{e.action}</Badge>
                        </Td>
                        <Td>
                          {e.encrypted ? (
                            <span className="flex items-center gap-1.5 text-[12px] text-navy-400">
                              <Lock className="h-3 w-3" aria-hidden />
                              Encrypted at rest
                            </span>
                          ) : Object.keys(e.detail || {}).length === 0 ? (
                            <span className="text-navy-300">—</span>
                          ) : (
                            <span className="font-mono text-[11px] leading-relaxed text-navy-500">
                              {JSON.stringify(e.detail)}
                            </span>
                          )}
                        </Td>
                        <Td className="font-mono text-[11px] text-navy-400">{e.hash}</Td>
                      </Tr>
                    ))}
                  </TBody>
                </Table>
              )}
            </CardBody>
          </Card>
        </div>
      )}

      {/* Integrations */}
      {tab === 'integrations' && (
        <div className="space-y-5">
          <Card>
            <CardHeader
              title="External adapters"
              subtitle={integrations.data?.posture || 'Read-only; this system never writes to a source of record.'}
            />
            <CardBody className="space-y-4">
              {integrations.loading && !integrations.data ? (
                <AnalysisSkeleton rows={4} />
              ) : integrations.error ? (
                <AnalysisError error={integrations.error} onRetry={integrations.reload} compact />
              ) : (
                <>
                  <div className="max-w-sm">
                    <Input
                      icon={KeyRound}
                      label="Authorisation reference"
                      placeholder="e.g. WARRANT-2026-0142"
                      value={authRef}
                      onChange={(e) => setAuthRef(e.target.value)}
                      hint="Records are not retrieved without one. The reference is written to the audit entry."
                    />
                  </div>

                  {(integrations.data?.adapters || []).map((a) => (
                    <div key={a.adapter} className="rounded-lg border border-slate-200 p-3.5">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="text-[13px] font-semibold text-navy-800">{a.system}</p>
                          <p className="mt-0.5 text-[12px] text-navy-400">
                            {a.record_type} · {a.access}
                          </p>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Badge variant={a.configured ? 'success' : 'warning'}>
                            {a.configured ? 'configured' : a.mode}
                          </Badge>
                          <Button
                            variant="outline"
                            size="sm"
                            loading={previewing === a.adapter}
                            onClick={() => fetchPreview(a.adapter)}
                          >
                            Fetch records
                          </Button>
                        </div>
                      </div>

                      <details className="mt-2.5">
                        <summary className="cursor-pointer text-[12px] font-medium text-navy-500 hover:text-teal-700">
                          Field mapping
                        </summary>
                        <Table className="mt-2 min-w-0">
                          <THead>
                            <Tr>
                              <Th>External field</Th>
                              <Th>Maps to</Th>
                            </Tr>
                          </THead>
                          <TBody>
                            {Object.entries(a.field_mapping || {}).map(([from, to]) => (
                              <Tr key={from}>
                                <Td className="font-mono text-[12px]">{from}</Td>
                                <Td className="font-mono text-[12px] text-teal-700">{to}</Td>
                              </Tr>
                            ))}
                          </TBody>
                        </Table>
                      </details>

                      {preview?.key === a.adapter && (
                        <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50/70 p-3">
                          {!preview.result.ok ? (
                            <p className="text-[12px] leading-relaxed text-amber-700">{preview.result.error}</p>
                          ) : (
                            <>
                              <p className="text-[12px] font-medium text-navy-600">
                                {preview.result.records.length} record
                                {preview.result.records.length === 1 ? '' : 's'} fetched at{' '}
                                {formatDateTime(preview.result.fetched_at)}
                              </p>
                              <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-white p-2.5 font-mono text-[11px] leading-relaxed text-navy-600">
                                {JSON.stringify(preview.result.records, null, 2)}
                              </pre>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  ))}
                </>
              )}
            </CardBody>
          </Card>
        </div>
      )}

      {/* Storage & export */}
      {tab === 'storage' && (
        <div className="space-y-5">
          <Card>
            <CardHeader
              title="Graph storage"
              subtitle="One module knows the storage engine, so Neo4j is a swap rather than a rewrite."
              actions={
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" icon={RefreshCw} loading={reloading} onClick={rerunPipeline}>
                    Re-run pipeline
                  </Button>
                  <Button variant="primary" size="sm" icon={Download} loading={exporting} onClick={exportCypher}>
                    Export Cypher
                  </Button>
                </div>
              }
            />
            <CardBody>
              {stats.loading && !stats.data ? (
                <AnalysisSkeleton rows={3} />
              ) : stats.error ? (
                <AnalysisError error={stats.error} onRetry={stats.reload} compact />
              ) : (
                <div className="space-y-2.5">
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="teal">Active: {backends?.active}</Badge>
                    <Badge variant={backends?.neo4j_driver_installed ? 'success' : 'neutral'}>
                      neo4j driver {backends?.neo4j_driver_installed ? 'installed' : 'not installed'}
                    </Badge>
                    <Badge variant={backends?.neo4j_configured ? 'success' : 'neutral'}>
                      {backends?.neo4j_configured ? 'Neo4j configured' : 'Neo4j not configured'}
                    </Badge>
                    {(backends?.available_exports || []).map((x) => (
                      <Badge key={x} variant="neutral">
                        export: {x}
                      </Badge>
                    ))}
                  </div>
                  <p className="text-[12px] leading-relaxed text-navy-500">{backends?.reason}</p>
                  <p className="text-[12px] leading-relaxed text-navy-400">{backends?.swap_path}</p>
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Audit encryption at rest" />
            <CardBody className="space-y-2">
              <div className="flex flex-wrap gap-1.5">
                <Badge variant={auditSec?.at_rest_encryption ? 'success' : 'neutral'}>
                  {auditSec?.at_rest_encryption ? auditSec.algorithm : 'not enabled'}
                </Badge>
                <Badge variant={auditSec?.library_available ? 'success' : 'warning'}>
                  cryptography {auditSec?.library_available ? 'available' : 'missing'}
                </Badge>
                <Badge variant="neutral">{auditSec?.hash_chain}</Badge>
              </div>
              <p className="text-[12px] leading-relaxed text-navy-500">{auditSec?.note}</p>
              {!auditSec?.at_rest_encryption && (
                <pre className="overflow-x-auto rounded-lg bg-navy-900 px-3 py-2 font-mono text-[11px] text-slate-100">
                  export CNAS_AUDIT_KEY=$(python3 -c &quot;import base64,os;print(base64.b64encode(os.urandom(32)).decode())&quot;)
                </pre>
              )}
            </CardBody>
          </Card>

          <CapabilityStrip capabilities={caps} loading={stats.loading} />
        </div>
      )}

      <AnalysisDisclosure />
    </div>
  );
}
