import { useParams, useSearchParams } from 'react-router-dom'

/** Placeholder bodies for screens built in later tasks; the shell and routing around them are real. */
function Stub({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <section className="mx-auto max-w-[1480px] px-4 py-8">
      <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
      {children && <p className="mt-2 text-sm text-muted-foreground">{children}</p>}
    </section>
  )
}

export const DataPage = () => <Stub title="Data" />
export function DocumentPage() {
  const { id } = useParams()
  return <Stub title={`Document ${id}`} />
}
export function SearchPage() {
  const [params] = useSearchParams()
  const mode = params.get('mode') === 'analyze' ? 'analyze' : 'find'
  return (
    <Stub title="Search">
      {mode === 'analyze' ? 'Analyze' : 'Find'}: {params.get('q') ?? ''}
    </Stub>
  )
}
