import { CheckCircle2, MinusCircle } from 'lucide-react';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/LoadingState';
import { cn } from '@/lib/utils';

/**
 * Which optional capabilities are active on this machine.
 *
 * The reference system's rule is that every capability degrades to a *stated*
 * fallback — so an unavailable one is shown with the fallback that replaced it,
 * never hidden and never silently downgraded.
 */
function rows(caps) {
  if (!caps) return [];
  return [
    {
      key: 'ocr',
      label: 'OCR of scanned FIRs',
      on: Boolean(caps.ocr?.available),
      detail: caps.ocr?.available
        ? `tesseract ${caps.ocr.tesseract_version || ''}${
            caps.ocr.hindi_available ? ' · Devanagari pack installed' : ' · no Devanagari pack'
          }`.trim()
        : caps.ocr?.note || 'Scanned pages are skipped rather than mis-read.',
    },
    {
      key: 'summariser',
      label: 'Narrative summaries',
      on: caps.summariser?.active === 'llm',
      detail:
        caps.summariser?.active === 'llm'
          ? `LLM backend (${caps.summariser.model || 'configured'}), output checked against derived facts`
          : 'Template summariser — cannot invent a fact that is not in the source records.',
    },
    {
      key: 'pdf',
      label: 'Court-ready PDF export',
      on: Boolean(caps.pdf_export),
      detail: caps.pdf_export
        ? 'reportlab installed; documents carry a SHA-256 digest'
        : 'Install reportlab; the endpoint returns a clear 503 rather than a stack trace.',
    },
    {
      key: 'audit',
      label: 'Audit encryption at rest',
      on: Boolean(caps.audit_security?.at_rest_encryption),
      detail: caps.audit_security?.at_rest_encryption
        ? `${caps.audit_security.algorithm} · key from ${caps.audit_security.key_source}`
        : caps.audit_security?.note || 'Set CNAS_AUDIT_KEY to encrypt payloads. The hash chain is always on.',
    },
    {
      key: 'graph',
      label: 'Graph storage',
      on: Boolean(caps.graph_backends?.neo4j_configured),
      detail: caps.graph_backends?.neo4j_configured
        ? 'Live Neo4j'
        : `${caps.graph_backends?.active || 'in-process'} — exports: ${(caps.graph_backends?.available_exports || []).join(', ')}`,
    },
    {
      key: 'integrations',
      label: 'External adapters',
      on: (caps.integrations || []).length > 0,
      detail: (caps.integrations || []).length
        ? `${(caps.integrations || []).map((k) => k.toUpperCase()).join(', ')} · read-only`
        : 'None registered.',
    },
  ];
}

export function CapabilityStrip({ capabilities, loading, className }) {
  const items = rows(capabilities);

  return (
    <Card className={className}>
      <CardHeader
        title="Capabilities on this machine"
        subtitle="Every optional capability degrades to a stated fallback. Nothing silently produces a worse answer while claiming to be fine."
      />
      <CardBody>
        {loading && !capabilities ? (
          <div className="grid gap-2.5 sm:grid-cols-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <p className="text-[13px] text-navy-400">Capability status is unavailable.</p>
        ) : (
          <div className="grid gap-2.5 sm:grid-cols-2">
            {items.map((item) => (
              <div
                key={item.key}
                className={cn(
                  'flex items-start gap-2.5 rounded-lg border px-3 py-2.5',
                  item.on ? 'border-emerald-200 bg-emerald-50/40' : 'border-slate-200 bg-slate-50/60'
                )}
              >
                {item.on ? (
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-hidden />
                ) : (
                  <MinusCircle className="mt-0.5 h-4 w-4 shrink-0 text-navy-300" aria-hidden />
                )}
                <div className="min-w-0">
                  <p className="text-[13px] font-medium text-navy-800">{item.label}</p>
                  <p className="mt-0.5 text-[12px] leading-relaxed text-navy-400">{item.detail}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
