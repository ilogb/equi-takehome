/** Root error boundary: a render error shows a reload prompt instead of a blank page. */
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="mx-auto max-w-xl p-8">
        <Alert variant="destructive">
          <AlertTitle>Something went wrong — reload</AlertTitle>
          <AlertDescription className="space-y-2">
            <p>This page hit an unexpected error.</p>
            <Button size="sm" variant="destructive" onClick={() => window.location.reload()}>
              Reload
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    )
  }
}
