import {
  BarChart, Bar,
  LineChart, Line,
  PieChart, Pie, Cell,
  AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from "recharts"
import type { VisualizationSpec } from "@/types"

const COLORS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]

function formatValue(value: number, spec: VisualizationSpec): string {
  if (spec.value_format === "percent") {
    return `${(value * 100).toFixed(1)}%`
  }
  if (spec.value_format === "currency") {
    const prefix = spec.currency_code ? `${spec.currency_code} ` : "$"
    return `${prefix}${value.toLocaleString()}`
  }
  return typeof value === "number" ? value.toLocaleString() : String(value)
}

function validateSpec(spec: VisualizationSpec): boolean {
  if (!spec.data || spec.data.length === 0) return false
  if (!spec.x_key || !spec.y_keys || spec.y_keys.length === 0) return false
  const first = spec.data[0]
  if (typeof first !== "object" || first === null) return false
  if (!(spec.x_key in first)) return false
  if (!spec.y_keys.every((k) => k in first)) return false
  if (spec.chart_type === "pie" && spec.y_keys.length !== 1) return false
  return true
}

interface ChartCardProps {
  spec: VisualizationSpec
}

export function ChartCard({ spec }: ChartCardProps) {
  if (!validateSpec(spec)) {
    return (
      <div className="rounded-lg border border-border/60 bg-card p-4">
        <p className="text-sm text-muted-foreground">Chart unavailable</p>
      </div>
    )
  }

  const labelFor = (key: string) => spec.y_labels?.[key] ?? key

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const tooltipFormatter = (value: any) => {
    if (typeof value === "number") return formatValue(value, spec)
    return String(value)
  }

  return (
    <div className="rounded-lg border border-border/60 bg-card p-4 space-y-3">
      <h4 className="text-sm font-medium text-foreground">{spec.title}</h4>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          {renderChart(spec, labelFor, tooltipFormatter)}
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function renderChart(
  spec: VisualizationSpec,
  labelFor: (key: string) => string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  tooltipFormatter: (value: any) => string,
) {
  const { chart_type, data, x_key, y_keys, x_label, y_label, stacked } = spec

  switch (chart_type) {
    case "bar":
      return (
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
          <XAxis dataKey={x_key} tick={{ fontSize: 12 }} label={x_label ? { value: x_label, position: "insideBottom", offset: -5, fontSize: 12 } : undefined} />
          <YAxis tick={{ fontSize: 12 }} label={y_label ? { value: y_label, angle: -90, position: "insideLeft", fontSize: 12 } : undefined} />
          <Tooltip formatter={tooltipFormatter} />
          {y_keys.length > 1 && <Legend />}
          {y_keys.map((key, i) => (
            <Bar key={key} dataKey={key} name={labelFor(key)} fill={COLORS[i % COLORS.length]} stackId={stacked ? "stack" : undefined} />
          ))}
        </BarChart>
      )
    case "line":
      return (
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
          <XAxis dataKey={x_key} tick={{ fontSize: 12 }} label={x_label ? { value: x_label, position: "insideBottom", offset: -5, fontSize: 12 } : undefined} />
          <YAxis tick={{ fontSize: 12 }} label={y_label ? { value: y_label, angle: -90, position: "insideLeft", fontSize: 12 } : undefined} />
          <Tooltip formatter={tooltipFormatter} />
          {y_keys.length > 1 && <Legend />}
          {y_keys.map((key, i) => (
            <Line key={key} type="monotone" dataKey={key} name={labelFor(key)} stroke={COLORS[i % COLORS.length]} strokeWidth={2} dot={{ r: 3 }} />
          ))}
        </LineChart>
      )
    case "area":
      return (
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
          <XAxis dataKey={x_key} tick={{ fontSize: 12 }} label={x_label ? { value: x_label, position: "insideBottom", offset: -5, fontSize: 12 } : undefined} />
          <YAxis tick={{ fontSize: 12 }} label={y_label ? { value: y_label, angle: -90, position: "insideLeft", fontSize: 12 } : undefined} />
          <Tooltip formatter={tooltipFormatter} />
          {y_keys.length > 1 && <Legend />}
          {y_keys.map((key, i) => (
            <Area key={key} type="monotone" dataKey={key} name={labelFor(key)} stroke={COLORS[i % COLORS.length]} fill={COLORS[i % COLORS.length]} fillOpacity={0.3} stackId={stacked ? "stack" : undefined} />
          ))}
        </AreaChart>
      )
    case "pie":
      return (
        <PieChart>
          <Pie
            data={data}
            dataKey={y_keys[0]}
            nameKey={x_key}
            cx="50%"
            cy="50%"
            outerRadius={80}
            label={({ name, value }) => `${name}: ${tooltipFormatter(value)}`}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip formatter={tooltipFormatter} />
          <Legend />
        </PieChart>
      )
  }
}
