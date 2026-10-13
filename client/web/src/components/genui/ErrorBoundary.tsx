import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  name: string
  children: ReactNode
}

/** Isolates a single generated component so one bad node can't break the whole answer. */
export class ComponentErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`Failed to render generated component "${this.props.name}"`, error, info)
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="rounded-xl border border-dashed border-border px-4 py-3 text-sm text-muted">
          Couldn't display this {this.props.name} component.
        </div>
      )
    }
    return this.props.children
  }
}
