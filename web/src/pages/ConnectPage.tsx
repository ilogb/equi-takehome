import { useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { urls } from '@/lib/api'

const ERRORS: Record<string, string> = {
  access_denied: 'Google sign-in was cancelled.',
  auth_failed: 'Google sign-in failed. Try again.',
  not_allowed: 'That Google account is not allowed to use this app.',
}

export function ConnectPage() {
  const [params] = useSearchParams()
  const error = params.get('error')
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-4">
      <h1 className="text-xl font-semibold tracking-tight">Connect Google Drive</h1>
      <p className="text-sm text-muted-foreground">Sign in with Google and pick the folder that holds your fund documents.</p>
      {error && (
        <p role="alert" className="text-sm text-negative">
          {ERRORS[error] ?? 'Something went wrong.'}
        </p>
      )}
      <Button asChild>
        <a href={urls.googleStart}>Sign in with Google</a>
      </Button>
    </main>
  )
}
