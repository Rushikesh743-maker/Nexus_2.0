import { useMemo, useState } from 'react';
import { Search, Languages, ScanLine, Merge, Phone, FileStack } from 'lucide-react';
import { Card, CardBody, CardHeader } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Input } from '@/components/ui/Input';
import { Tabs } from '@/components/ui/Tabs';
import { Table, TBody, Td, Th, THead, Tr } from '@/components/ui/Table';
import { EmptyState } from '@/components/ui/EmptyState';
import { AnalysisDisclosure, AnalysisError, AnalysisSkeleton, SyntheticNotice } from '@/components/analysis/AnalysisState';
import { DocumentDrawer } from '@/components/analysis/DocumentDrawer';
import { useCnaResource } from '@/hooks/useCnaResource';
import { cnaService } from '@/services';
import { cnaSourceType, formatScore } from '@/lib/cna';
import { cn } from '@/lib/utils';

const TABS = [
  { id: 'mentions', label: 'Extraction', icon: Search },
  { id: 'merges', label: 'Identity merges', icon: Merge },
  { id: 'phones', label: 'Phone ownership', icon: Phone },
  { id: 'documents', label: 'Source documents', icon: FileStack },
  { id: 'ocr', label: 'OCR', icon: ScanLine },
];

const MENTION_TONE = {
  PERSON: 'bg-teal-50 text-teal-700 ring-teal-600/20',
  PHONE: 'bg-sky-50 text-sky-700 ring-sky-600/20',
  VEHICLE: 'bg-violet-50 text-violet-700 ring-violet-600/20',
  LOCATION: 'bg-amber-50 text-amber-700 ring-amber-600/25',
  ORG: 'bg-rose-50 text-rose-700 ring-rose-600/20',
  MONEY: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  DATE: 'bg-slate-100 text-navy-600 ring-navy-500/15',
};

/**
 * Shows the extracted span highlighted inside the surrounding text, so a node
 * can be traced to the exact words that produced it.
 *
 * The offsets are into the *document*, while `context` is a window around the
 * mention, so the span is located inside the context by matching the text.
 */
function MentionContext({ mention }) {
  const context = mention.context || '';
  const needle = mention.text || '';
  const at = needle ? context.indexOf(needle) : -1;

  if (at < 0) {
    return <span className="text-[12px] leading-relaxed text-navy-500">{context}</span>;
  }

  return (
    <span className="text-[12px] leading-relaxed text-navy-500">
      {context.slice(0, at)}
      <mark
        className={cn(
          'rounded px-1 py-0.5 font-medium ring-1 ring-inset',
          MENTION_TONE[mention.type] || MENTION_TONE.DATE
        )}
      >
        {needle}
      </mark>
      {context.slice(at + needle.length)}
    </span>
  );
}

export function PipelinePage() {
  const [tab, setTab] = useState('mentions');
  const [query, setQuery] = useState('');
  const [mentionType, setMentionType] = useState('all');
  const [docId, setDocId] = useState(null);

  const { data, error, loading, reload } = useCnaResource(() => cnaService.getPipeline(), []);

  const mentions = data?.mentions || [];
  const merges = data?.resolution_decisions || [];
  const phones = data?.phone_ownership || [];
  const documents = data?.documents || [];
  const ocr = data?.ocr || {};

  const mentionTypes = useMemo(() => Array.from(new Set(mentions.map((m) => m.type))).sort(), [mentions]);

  const filteredMentions = useMemo(() => {
    const q = query.trim().toLowerCase();
    return mentions.filter((m) => {
      if (mentionType !== 'all' && m.type !== mentionType) return false;
      if (!q) return true;
      return (
        String(m.text).toLowerCase().includes(q) ||
        String(m.source_id).toLowerCase().includes(q) ||
        String(m.context || '').toLowerCase().includes(q)
      );
    });
  }, [mentions, query, mentionType]);

  const filteredMerges = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return merges;
    return merges.filter(
      (m) =>
        String(m.a).toLowerCase().includes(q) ||
        String(m.b).toLowerCase().includes(q) ||
        String(m.reason).toLowerCase().includes(q)
    );
  }, [merges, query]);

  const devanagariCount = useMemo(() => mentions.filter((m) => m.script === 'devanagari').length, [mentions]);

  if (error && !data) {
    return (
      <Card>
        <AnalysisError error={error} onRetry={reload} />
      </Card>
    );
  }

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Pipeline transparency"
          subtitle="What the extractor found, and which identity merges were applied — each with the reason and score that drove it."
        />
        <CardBody className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="teal">Extractor: {data?.extractor || '—'}</Badge>
            <Badge variant="neutral">{mentions.length} mentions shown</Badge>
            <Badge variant="neutral">{merges.length} merge decisions</Badge>
            <Badge variant="neutral">{documents.length} source documents</Badge>
            {devanagariCount > 0 && (
              <Badge variant="info">
                <Languages className="h-3 w-3" aria-hidden />
                {devanagariCount} Devanagari mentions
              </Badge>
            )}
          </div>
          <p className="text-[12px] leading-relaxed text-navy-400">
            The default extractor is rule- and gazetteer-based so it runs offline. A transformer NER model drops into
            the same interface when one is available.
          </p>
          <Tabs tabs={TABS} value={tab} onChange={setTab} />
          {(tab === 'mentions' || tab === 'merges') && (
            <div className="flex flex-wrap items-center gap-2">
              <div className="w-64">
                <Input
                  icon={Search}
                  placeholder={tab === 'mentions' ? 'Search text, context, source…' : 'Search names or reasons…'}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Search the pipeline"
                />
              </div>
              {tab === 'mentions' && (
                <div className="flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    onClick={() => setMentionType('all')}
                    className={cn(
                      'rounded-lg px-2.5 py-1 text-[12px] font-medium transition-colors',
                      mentionType === 'all' ? 'bg-navy-800 text-white' : 'bg-slate-100 text-navy-500 hover:bg-slate-200'
                    )}
                  >
                    All
                  </button>
                  {mentionTypes.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setMentionType(t)}
                      className={cn(
                        'rounded-lg px-2.5 py-1 text-[12px] font-medium transition-colors',
                        mentionType === t ? 'bg-navy-800 text-white' : 'bg-slate-100 text-navy-500 hover:bg-slate-200'
                      )}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardBody>
      </Card>

      {loading && !data ? (
        <Card>
          <CardBody>
            <AnalysisSkeleton rows={8} />
          </CardBody>
        </Card>
      ) : (
        <Card>
          <CardBody className="p-0">
            {/* Extraction */}
            {tab === 'mentions' &&
              (filteredMentions.length === 0 ? (
                <EmptyState title="No mention matches" compact />
              ) : (
                <Table>
                  <THead>
                    <Tr>
                      <Th className="w-40">Extracted</Th>
                      <Th className="w-24">Type</Th>
                      <Th>In context</Th>
                      <Th className="w-32">Source</Th>
                      <Th className="w-24 text-right">Span</Th>
                      <Th className="w-20 text-right">Conf.</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {filteredMentions.map((m, i) => (
                      <Tr key={`${m.source_id}-${m.start}-${i}`}>
                        <Td>
                          <span className="font-medium text-navy-800">{m.text}</span>
                          {m.normalized && m.normalized !== m.text && (
                            <span className="mt-0.5 block font-mono text-[11px] text-navy-400">→ {m.normalized}</span>
                          )}
                          {m.script === 'devanagari' && (
                            <Badge variant="info" className="mt-1">
                              Devanagari
                            </Badge>
                          )}
                        </Td>
                        <Td>
                          <span
                            className={cn(
                              'inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset',
                              MENTION_TONE[m.type] || MENTION_TONE.DATE
                            )}
                          >
                            {m.type}
                          </span>
                        </Td>
                        <Td>
                          <MentionContext mention={m} />
                        </Td>
                        <Td>
                          <button
                            type="button"
                            onClick={() => setDocId(m.source_id)}
                            className="text-left font-mono text-[11px] text-teal-700 hover:text-teal-800"
                          >
                            {m.source_id}
                          </button>
                          <span className="mt-0.5 block text-[11px] text-navy-400">
                            {cnaSourceType(m.source_type).label}
                          </span>
                        </Td>
                        <Td className="text-right font-mono text-[11px] text-navy-400">
                          {m.start}–{m.end}
                        </Td>
                        <Td className="text-right font-mono text-[12px] font-medium">{formatScore(m.confidence, 2)}</Td>
                      </Tr>
                    ))}
                  </TBody>
                </Table>
              ))}

            {/* Identity merges */}
            {tab === 'merges' && (
              <>
                <p className="border-b border-slate-100 px-5 py-3 text-[12px] leading-relaxed text-navy-400">
                  Merges are driven by shared identifiers first, then order-insensitive name matching that tolerates
                  initials and added middle names. Cross-script matches use syllable-aware transliteration and a
                  consonant-skeleton phonetic key that absorbs Hindi schwa deletion.
                </p>
                {filteredMerges.length === 0 ? (
                  <EmptyState title="No merge matches" compact />
                ) : (
                  <Table>
                    <THead>
                      <Tr>
                        <Th>Record A</Th>
                        <Th>Record B</Th>
                        <Th className="w-72">Reason</Th>
                        <Th className="w-20 text-right">Score</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {filteredMerges.map((m, i) => (
                        <Tr key={`${m.key_a}-${m.key_b}-${i}`}>
                          <Td>
                            <span className="font-medium text-navy-800">{m.a}</span>
                            <span className="mt-0.5 block font-mono text-[11px] text-navy-300">{m.key_a}</span>
                          </Td>
                          <Td>
                            <span className="font-medium text-navy-800">{m.b}</span>
                            <span className="mt-0.5 block font-mono text-[11px] text-navy-300">{m.key_b}</span>
                          </Td>
                          <Td className="text-[12px] text-navy-500">{m.reason}</Td>
                          <Td className="text-right">
                            <Badge variant={m.score >= 0.95 ? 'success' : m.score >= 0.85 ? 'teal' : 'warning'}>
                              {formatScore(m.score, 2)}
                            </Badge>
                          </Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                )}
              </>
            )}

            {/* Phone ownership */}
            {tab === 'phones' && (
              <>
                <p className="border-b border-slate-100 px-5 py-3 text-[12px] leading-relaxed text-navy-400">
                  Attaching a phone to the wrong person fuses two unrelated people into one node, and every downstream
                  inference inherits the error. Ownership is therefore asserted only from an explicit textual cue —
                  ambiguous mentions are deliberately left unattributed.
                </p>
                {phones.length === 0 ? (
                  <EmptyState title="No phone ownership was asserted" compact />
                ) : (
                  <Table>
                    <THead>
                      <Tr>
                        <Th className="w-36">Handset</Th>
                        <Th className="w-48">Attributed to</Th>
                        <Th>Textual cue</Th>
                        <Th className="w-32">Source</Th>
                        <Th className="w-20 text-right">Conf.</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {phones.map((p, i) => (
                        <Tr key={`${p.phone}-${i}`}>
                          <Td className="font-mono text-[12px] font-medium text-navy-800">{p.phone}</Td>
                          <Td className="font-medium text-navy-800">{p.owner}</Td>
                          <Td>
                            <span className="text-[12px] leading-relaxed text-navy-500">…{p.evidence}…</span>
                          </Td>
                          <Td>
                            <button
                              type="button"
                              onClick={() => setDocId(p.source_id)}
                              className="text-left font-mono text-[11px] text-teal-700 hover:text-teal-800"
                            >
                              {p.source_id}
                            </button>
                          </Td>
                          <Td className="text-right font-mono text-[12px] font-medium">{formatScore(p.confidence, 2)}</Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                )}
              </>
            )}

            {/* Documents */}
            {tab === 'documents' &&
              (documents.length === 0 ? (
                <EmptyState title="No source documents" compact />
              ) : (
                <Table>
                  <THead>
                    <Tr>
                      <Th>Document</Th>
                      <Th className="w-44">Source system</Th>
                      <Th className="w-32">Script</Th>
                    </Tr>
                  </THead>
                  <TBody>
                    {documents.map((d) => {
                      const meta = cnaSourceType(d.source_type);
                      return (
                        <Tr key={d.id} onClick={() => setDocId(d.id)}>
                          <Td className="font-mono text-[12px] font-medium text-teal-700">{d.id}</Td>
                          <Td>
                            <span className="flex items-center gap-2">
                              <meta.icon className="h-3.5 w-3.5 shrink-0 text-navy-300" aria-hidden />
                              {meta.label}
                            </span>
                          </Td>
                          <Td>
                            <Badge variant={d.script === 'devanagari' ? 'info' : 'neutral'}>
                              {d.script === 'devanagari' ? 'Devanagari' : 'Latin'}
                            </Badge>
                          </Td>
                        </Tr>
                      );
                    })}
                  </TBody>
                </Table>
              ))}

            {/* OCR */}
            {tab === 'ocr' && (
              <div className="space-y-4 p-5">
                <div
                  className={cn(
                    'rounded-lg border px-3.5 py-3',
                    ocr.capabilities?.available
                      ? 'border-emerald-200 bg-emerald-50/50'
                      : 'border-amber-200 bg-amber-50/50'
                  )}
                >
                  <p className="text-[13px] font-semibold text-navy-800">
                    {ocr.capabilities?.available ? 'OCR is available on this machine' : 'OCR is not available on this machine'}
                  </p>
                  <p className="mt-1 text-[12px] leading-relaxed text-navy-500">{ocr.capabilities?.note}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    <Badge variant={ocr.capabilities?.tesseract ? 'success' : 'neutral'}>
                      tesseract {ocr.capabilities?.tesseract ? ocr.capabilities.tesseract_version || 'installed' : 'missing'}
                    </Badge>
                    <Badge variant={ocr.capabilities?.hindi_available ? 'success' : 'neutral'}>
                      Devanagari pack {ocr.capabilities?.hindi_available ? 'installed' : 'missing'}
                    </Badge>
                    <Badge variant={ocr.capabilities?.pytesseract ? 'success' : 'neutral'}>pytesseract</Badge>
                    <Badge variant={ocr.capabilities?.pillow ? 'success' : 'neutral'}>pillow</Badge>
                  </div>
                  {!ocr.capabilities?.available && (
                    <pre className="mt-2.5 overflow-x-auto rounded-lg bg-navy-900 px-3 py-2 font-mono text-[11px] text-slate-100">
                      brew install tesseract tesseract-lang{'\n'}sudo apt install tesseract-ocr tesseract-ocr-hin
                    </pre>
                  )}
                </div>

                {(ocr.documents || []).length === 0 ? (
                  <p className="text-[13px] text-navy-400">
                    No scanned page was read. Scanned pages are skipped rather than mis-read — a garbled name is worse
                    than a missing one.
                  </p>
                ) : (
                  <Table>
                    <THead>
                      <Tr>
                        <Th>Page</Th>
                        <Th className="w-28">Language</Th>
                        <Th className="w-28 text-right">Confidence</Th>
                        <Th className="w-28 text-right">Accuracy</Th>
                      </Tr>
                    </THead>
                    <TBody>
                      {ocr.documents.map((d, i) => (
                        <Tr key={i}>
                          <Td className="font-mono text-[12px]">{d.id || d.file || `page ${i + 1}`}</Td>
                          <Td>{d.language || d.script || '—'}</Td>
                          <Td className="text-right font-mono text-[12px]">{formatScore(d.confidence, 2)}</Td>
                          <Td className="text-right font-mono text-[12px]">{formatScore(d.accuracy, 2)}</Td>
                        </Tr>
                      ))}
                    </TBody>
                  </Table>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      )}

      <SyntheticNotice />
      <AnalysisDisclosure />

      <DocumentDrawer docId={docId} open={Boolean(docId)} onClose={() => setDocId(null)} />
    </div>
  );
}
