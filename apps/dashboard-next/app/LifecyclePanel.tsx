import type { ReactNode } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { getServerEvents, type LifecyclePhase } from '@/lib/preview';
import { cn } from '@/lib/utils';

// patterns-explicit-variants: olay-rengi kararı cva-variant'ta — bileşende
// ternary değil. Renkler repo-token'ları (tek kaynak: design-system).
const eventVariants = cva('py-2', {
  variants: {
    tone: {
      start: 'text-ok',
      recovery: 'text-warn',
      graceful: 'text-muted',
      crash: 'text-err',
      unknown: 'text-muted',
    },
  },
  defaultVariants: { tone: 'unknown' },
});

type Tone = NonNullable<VariantProps<typeof eventVariants>['tone']>;

const TONE: Record<LifecyclePhase, Tone> = {
  start: 'start',
  recovery: 'recovery',
  graceful: 'graceful',
  crash: 'crash',
  unknown: 'unknown',
};

const PHASE_LABEL: Record<LifecyclePhase, string> = {
  start: 'AÇILIŞ',
  recovery: 'KURTARMA',
  graceful: 'KAPANIŞ',
  crash: 'ÇÖKME',
  unknown: '—',
};

// Server Component — veri burada toplanır, istemciye JS gitmez.
// Olay-kaydı append-only'dir; pano yalnız okur, sunucu-yüzeyine dokunmaz.
export default async function LifecyclePanel() {
  const { events, last_crash, last_recovery } = await getServerEvents(12);

  return (
    <section className="rounded-lg border border-border bg-surface p-6">
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.22em] text-muted">
          Yaşam Döngüsü
        </h2>
        <span className="font-mono text-[11px] text-muted">
          logs/server_events.jsonl
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-4 font-mono text-sm">
        <Summary
          label="SON ÇÖKME"
          tone={last_crash ? 'crash' : 'unknown'}
          value={
            last_crash?.ts ? (
              <time>{last_crash.ts}</time>
            ) : (
              'yok — sinyalsiz ölüm kaydı düşmemiş'
            )
          }
        />
        <Summary
          label="SON KURTARMA"
          tone={last_recovery ? 'recovery' : 'unknown'}
          value={
            last_recovery?.ts ? (
              <time>{last_recovery.ts}</time>
            ) : (
              'yok — önbellek geri yükleme kaydı düşmemiş'
            )
          }
        />
      </dl>

      {events.length === 0 ? (
        <p className="mt-4 text-sm text-muted">
          henüz olay yok — ilk başlatma bekleniyor
        </p>
      ) : (
        <table className="mt-4 w-full font-mono text-sm">
          <thead>
            <tr className="border-b border-border text-left text-[10px] tracking-[0.14em] text-muted">
              <th className="py-2">ZAMAN</th>
              <th className="py-2">FAZ</th>
              <th className="py-2">OLAY</th>
              <th className="py-2">PID</th>
              <th className="py-2">AYRINTI</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e, i) => (
              <tr key={i} className="border-b border-surface-raised">
                <td className="py-2 text-muted">
                  {e.ts ? <time>{e.ts}</time> : '—'}
                </td>
                <td className={eventVariants({ tone: TONE[e.phase] })}>
                  {PHASE_LABEL[e.phase]}
                </td>
                <td className="py-2">{e.event ?? '—'}</td>
                <td className="py-2 text-muted">{e.pid ?? '—'}</td>
                <td className="py-2 text-muted">{e.detail ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function Summary({
  label,
  value,
  tone,
}: {
  label: string;
  value: ReactNode;
  tone: Tone;
}) {
  return (
    <div className="bg-bg">
      <dt className="text-[10px] tracking-[0.14em] text-muted">{label}</dt>
      <dd className={cn('mt-1 font-semibold', eventVariants({ tone }))}>
        {value}
      </dd>
    </div>
  );
}
