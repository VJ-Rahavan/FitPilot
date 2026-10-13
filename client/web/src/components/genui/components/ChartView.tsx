import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatAxisLabel, formatValue } from '../../../lib/format'
import type { ChartNode } from '../../../types/ui'
import { Panel, PanelHeader } from '../../ui/primitives'

const PALETTE = ['#c6f432', '#38bdf8', '#a78bfa', '#fb923c', '#f472b6', '#2dd4bf']
const GRID = '#252a32'
const AXIS = '#8b93a1'

const tooltipProps = {
  contentStyle: {
    background: '#181c22',
    border: '1px solid #333a44',
    borderRadius: 10,
    fontSize: 12,
    color: '#e9ecf1',
  },
  labelStyle: { color: '#8b93a1', marginBottom: 4 },
  cursor: { fill: 'rgba(198, 244, 50, 0.06)', stroke: '#333a44' },
}

export function ChartView({ node }: { node: ChartNode }) {
  const series = node.series.map((s, i) => ({
    ...s,
    color: PALETTE[i % PALETTE.length], // always on-theme
    name: s.label ?? s.key,
  }))
  const unit = node.unit ? ` ${node.unit}` : ''
  const valueFormatter = (v: unknown) => `${formatValue(v)}${unit}`
  const showLegend = series.length > 1 || node.chart_type === 'pie'

  const axes = (
    <>
      <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
      <XAxis
        dataKey={node.x_key}
        tickFormatter={formatAxisLabel}
        stroke={AXIS}
        tick={{ fontSize: 12 }}
        tickLine={false}
        axisLine={{ stroke: GRID }}
        minTickGap={16}
      />
      <YAxis
        stroke={AXIS}
        tick={{ fontSize: 12 }}
        tickLine={false}
        axisLine={false}
        width={48}
        domain={node.chart_type === 'bar' ? [0, 'auto'] : ['auto', 'auto']}
        tickFormatter={(v) => formatValue(v)}
      />
      <Tooltip {...tooltipProps} labelFormatter={formatAxisLabel} formatter={valueFormatter} />
      {showLegend && <Legend wrapperStyle={{ fontSize: 12, color: AXIS }} />}
    </>
  )

  const dense = node.data.length > 20

  let chart
  switch (node.chart_type) {
    case 'bar':
      chart = (
        <BarChart data={node.data}>
          {axes}
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} name={s.name} fill={s.color} radius={[4, 4, 0, 0]} maxBarSize={40} />
          ))}
        </BarChart>
      )
      break
    case 'area':
      chart = (
        <AreaChart data={node.data}>
          <defs>
            {series.map((s) => (
              <linearGradient key={s.key} id={`grad-${s.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={0.35} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          {axes}
          {series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.name}
              stroke={s.color}
              strokeWidth={2}
              fill={`url(#grad-${s.key})`}
            />
          ))}
        </AreaChart>
      )
      break
    case 'pie': {
      const valueKey = series[0].key
      chart = (
        <PieChart>
          <Pie
            data={node.data}
            dataKey={valueKey}
            nameKey={node.x_key}
            innerRadius="55%"
            outerRadius="85%"
            paddingAngle={2}
            stroke="none"
          >
            {node.data.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip {...tooltipProps} formatter={valueFormatter} />
          <Legend wrapperStyle={{ fontSize: 12, color: AXIS }} />
        </PieChart>
      )
      break
    }
    default:
      chart = (
        <LineChart data={node.data}>
          {axes}
          {series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.name}
              stroke={s.color}
              strokeWidth={2.5}
              dot={dense ? false : { r: 3, strokeWidth: 0, fill: s.color }}
              activeDot={{ r: 5 }}
              connectNulls
            />
          ))}
        </LineChart>
      )
  }

  return (
    <Panel>
      <PanelHeader title={node.title} description={node.description} />
      <div className="h-64 w-full sm:h-72">
        <ResponsiveContainer width="100%" height="100%">
          {chart}
        </ResponsiveContainer>
      </div>
    </Panel>
  )
}
