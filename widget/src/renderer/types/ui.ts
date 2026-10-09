/**
 * UI component catalog — mirrors backend/src/genui/ui/components.py.
 * The backend validates every component before it reaches the client
 * (and serves the JSON Schema at GET /api/ui/schema).
 */

export type Scalar = string | number | boolean | null

export type IconName =
  | 'dumbbell'
  | 'flame'
  | 'trophy'
  | 'activity'
  | 'scale'
  | 'calendar'
  | 'timer'
  | 'heart'
  | 'target'
  | 'zap'

export interface TextNode {
  type: 'text'
  content: string
  variant?: 'body' | 'heading' | 'subheading' | 'muted'
}

export interface MetricNode {
  type: 'metric'
  label: string
  value: string | number
  unit?: string
  change_pct?: number
  good_direction?: 'up' | 'down'
  caption?: string
  icon?: IconName
}

export interface CardNode {
  type: 'card'
  title?: string
  description?: string
  children?: UINode[]
}

export interface LayoutNode {
  type: 'layout'
  direction?: 'row' | 'column' | 'grid'
  columns?: number
  children: UINode[]
}

export interface TableColumn {
  key: string
  label: string
  align?: 'left' | 'center' | 'right'
}

export interface TableNode {
  type: 'table'
  title?: string
  columns: TableColumn[]
  rows: Record<string, Scalar>[]
}

export interface ChartSeries {
  key: string
  label?: string
}

export interface ChartNode {
  type: 'chart'
  chart_type: 'line' | 'bar' | 'area' | 'pie'
  title?: string
  description?: string
  data: Record<string, Scalar>[]
  x_key: string
  series: ChartSeries[]
  unit?: string
}

export interface ListItem {
  title: string
  description?: string
  badge?: string
}

export interface ListNode {
  type: 'list'
  title?: string
  ordered?: boolean
  items: ListItem[]
}

export interface AlertNode {
  type: 'alert'
  variant?: 'info' | 'success' | 'warning' | 'error'
  title?: string
  message: string
}

export interface ProgressNode {
  type: 'progress'
  label: string
  value: number
  max?: number
  unit?: string
  caption?: string
}

export interface ButtonNode {
  type: 'button'
  label: string
  action: string
  payload?: Record<string, unknown>
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
}

export interface SelectOption {
  label: string
  value: string | number
}

export interface FormFieldSpec {
  name: string
  label: string
  input?: 'text' | 'number' | 'email' | 'textarea' | 'select' | 'checkbox' | 'date'
  placeholder?: string
  required?: boolean
  default?: Scalar
  options?: SelectOption[]
  min?: number
  max?: number
  step?: number
  unit?: string
}

export interface FormNode {
  type: 'form'
  title?: string
  description?: string
  fields: FormFieldSpec[]
  submit_label?: string
  action: string
}

export interface ExerciseCardNode {
  type: 'exercise_card'
  name: string
  primary_muscles: string[]
  secondary_muscles?: string[]
  equipment?: string
  difficulty?: 'beginner' | 'intermediate' | 'advanced'
  instructions: string[]
  tips?: string[]
}

export interface PlanExercise {
  name: string
  sets: number
  reps: string
  rest_seconds?: number
  notes?: string
}

export interface PlanDay {
  day: string
  focus: string
  exercises: PlanExercise[]
}

export interface WorkoutPlanNode {
  type: 'workout_plan'
  title: string
  goal?: string
  weeks?: number
  days: PlanDay[]
}

export interface TimerNode {
  type: 'timer'
  label?: string
  seconds: number
}

export type UINode =
  | TextNode
  | MetricNode
  | CardNode
  | LayoutNode
  | TableNode
  | ChartNode
  | ListNode
  | AlertNode
  | ProgressNode
  | ButtonNode
  | FormNode
  | ExerciseCardNode
  | WorkoutPlanNode
  | TimerNode

export type UINodeType = UINode['type']
