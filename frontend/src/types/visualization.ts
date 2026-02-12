export type ChartType = "bar" | "line" | "pie" | "area"

export interface VisualizationSpec {
  schema_version: 1
  id: string
  title: string
  chart_type: ChartType
  data: Record<string, string | number>[]
  x_key: string
  y_keys: string[]
  y_labels?: Record<string, string>
  x_label?: string
  y_label?: string
  value_format?: "number" | "percent" | "currency"
  currency_code?: string
  stacked?: boolean
}
