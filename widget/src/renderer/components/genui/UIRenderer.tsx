import { lazy, Suspense, type ComponentType } from 'react'
import type { UINode, UINodeType } from '../../types/ui'
import { ComponentErrorBoundary } from './ErrorBoundary'
import { AlertView } from './components/AlertView'
import { ButtonView } from './components/ButtonView'
import { CardView } from './components/CardView'
import { ExerciseCardView } from './components/ExerciseCardView'
import { FormView } from './components/FormView'
import { LayoutView } from './components/LayoutView'
import { ListView } from './components/ListView'
import { MetricView } from './components/MetricView'
import { ProgressView } from './components/ProgressView'
import { TableView } from './components/TableView'
import { TextView } from './components/TextView'
import { TimerView } from './components/TimerView'
import { WorkoutPlanView } from './components/WorkoutPlanView'

// Recharts is large: keep it out of the initial bundle, but fetch it while the browser is
// idle so it's ready before the first chart streams in (loading it mid-stream would block
// the main thread and make streamed components appear in a burst).
const loadChart = () => import('./components/ChartView')
const LazyChart = lazy(() => loadChart().then((m) => ({ default: m.ChartView })))

if (typeof window !== 'undefined') {
  const idle = window.requestIdleCallback ?? ((cb: () => void) => window.setTimeout(cb, 1500))
  idle(() => void loadChart())
}

function ChartView(props: { node: Extract<UINode, { type: 'chart' }> }) {
  return (
    <Suspense fallback={<div className="h-72 animate-pulse rounded-2xl bg-surface" />}>
      <LazyChart {...props} />
    </Suspense>
  )
}

type Registry = { [K in UINodeType]: ComponentType<{ node: Extract<UINode, { type: K }> }> }

/** One renderer per component type in the backend catalog. */
const registry: Registry = {
  text: TextView,
  metric: MetricView,
  card: CardView,
  layout: LayoutView,
  table: TableView,
  chart: ChartView,
  list: ListView,
  alert: AlertView,
  progress: ProgressView,
  button: ButtonView,
  form: FormView,
  exercise_card: ExerciseCardView,
  workout_plan: WorkoutPlanView,
  timer: TimerView,
}

export function UINodeView({ node }: { node: UINode }) {
  const View = registry[node.type] as ComponentType<{ node: UINode }> | undefined
  if (!View) {
    return (
      <div className="rounded-xl border border-dashed border-border px-4 py-3 text-sm text-muted">
        Unsupported component: <code>{String((node as { type?: unknown }).type)}</code>
      </div>
    )
  }
  return (
    <ComponentErrorBoundary name={node.type}>
      <View node={node} />
    </ComponentErrorBoundary>
  )
}

export function UIRenderer({
  components,
  streaming = false,
}: {
  components: UINode[]
  streaming?: boolean
}) {
  return (
    <div className="flex flex-col gap-4">
      {components.map((node, i) => (
        // Stable index keys: earlier components never re-mount as new ones stream in.
        <div key={i} className="animate-fade-in" data-component={node.type}>
          <UINodeView node={node} />
        </div>
      ))}
      {streaming && <ComponentSkeleton />}
    </div>
  )
}

/** Placeholder for the component currently being generated. */
function ComponentSkeleton() {
  return (
    <div
      aria-label="Generating"
      className="flex animate-pulse flex-col gap-3 rounded-2xl border border-border/60 bg-surface p-5"
    >
      <div className="h-3 w-1/3 rounded bg-surface-3" />
      <div className="h-3 w-2/3 rounded bg-surface-3" />
      <div className="h-3 w-1/2 rounded bg-surface-3" />
    </div>
  )
}
