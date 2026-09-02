import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip as RechartsTooltip } from 'recharts';

/**
 * Donut chart with a center total and a legend list.
 * data: [{ label, value, color }]
 */
export function StatusDonut({ data = [], centerLabel = 'Total', size = 176, className }) {
  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className={className}>
      <div className="relative mx-auto" style={{ height: size, width: size }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="label"
              innerRadius="62%"
              outerRadius="92%"
              paddingAngle={2}
              strokeWidth={0}
            >
              {data.map((d) => (
                <Cell key={d.label} fill={d.color} />
              ))}
            </Pie>
            <RechartsTooltip
              formatter={(value, name) => [value, name]}
              contentStyle={{
                borderRadius: 10,
                border: '1px solid #e2e8f0',
                fontSize: 12,
                boxShadow: '0 4px 6px -1px rgb(16 42 67 / 0.08)',
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-semibold leading-none text-navy-900">{total}</span>
          <span className="mt-0.5 text-[10px] font-medium uppercase tracking-wide text-navy-300">{centerLabel}</span>
        </div>
      </div>
      <ul className="mt-4 space-y-1.5">
        {data.map((d) => (
          <li key={d.label} className="flex items-center justify-between gap-3 text-[13px]">
            <span className="flex items-center gap-2 text-navy-500">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: d.color }} aria-hidden />
              {d.label}
            </span>
            <span className="font-semibold text-navy-800">{d.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
