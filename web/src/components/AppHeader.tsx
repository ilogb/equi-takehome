import { useIsFetching, useQueryClient } from '@tanstack/react-query'
import { FolderOpen, Layers, Loader2, LogOut, Moon, Search, Sun, SunMoon } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { SyncPill } from '@/components/SyncPill'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { keys, useFolder, useLogout, useMe } from '@/lib/api'
import { applyTheme, type Theme } from '@/lib/theme'
import { cn } from '@/lib/utils'

export type SearchMode = 'find' | 'analyze'

const navClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'inline-flex h-8 items-center rounded-md px-3 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground',
    isActive ? 'bg-accent text-accent-foreground' : 'text-muted-foreground',
  )

function initials(name: string | null | undefined, email: string | undefined): string {
  const src = (name || email || '?').trim()
  const parts = src.split(/[\s@.]+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '?') + (parts.length > 1 ? (parts[1]?.[0] ?? '') : '')).toUpperCase()
}

const PLACEHOLDER: Record<SearchMode, string> = {
  find: 'Find documents and figures',
  analyze: 'Ask a question about your funds',
}
const NARROW_PLACEHOLDER: Record<SearchMode, string> = { ...PLACEHOLDER, analyze: 'Ask about your funds' }
const NARROW = '(max-width: 767px)' // below md, where the box drops to its own row

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia?.(NARROW).matches ?? false)
  useEffect(() => {
    const mq = window.matchMedia?.(NARROW)
    if (!mq) return
    const on = () => setNarrow(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return narrow
}

/** Header search. On /search the text and mode mirror the URL (Back/Forward included);
 *  elsewhere the last query stays so it can be refined. */
function SearchBox() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const narrow = useNarrow()
  const { pathname, search } = useLocation()
  const onSearch = pathname === '/search'
  const params = new URLSearchParams(search)
  const urlQ = onSearch ? (params.get('q') ?? '').trim() : ''
  const urlMode: SearchMode = onSearch && params.get('mode') === 'analyze' ? 'analyze' : 'find'
  const [text, setText] = useState(urlQ)
  const [mode, setMode] = useState<SearchMode>(urlMode)

  // Follow the URL whenever it changes on /search (state adjusted during render, not in an effect).
  const urlKey = onSearch ? search : null
  const [seenKey, setSeenKey] = useState(urlKey)
  if (urlKey !== seenKey) {
    setSeenKey(urlKey)
    if (onSearch) {
      setText(urlQ)
      setMode(urlMode)
    }
  }

  const q = text.trim()
  const empty = q === ''
  // The search in the URL is still loading (Analyze can take a minute): show it on the button
  // and ignore repeats of it, so a second click never fires a second request.
  const loadingKey = urlMode === 'analyze' ? keys.analyze(urlQ) : keys.search(urlQ)
  const busy = useIsFetching({ queryKey: loadingKey }) > 0 && onSearch && urlQ !== ''

  function run(m: SearchMode) {
    if (empty) return
    if (onSearch && q === urlQ && m === urlMode) {
      if (busy) return
      // Same URL: navigating would be a no-op and serve the cache, so re-run explicitly.
      void qc.refetchQueries({ queryKey: m === 'analyze' ? keys.analyze(q) : keys.search(q) })
      return
    }
    navigate(`/search?${new URLSearchParams({ q, mode: m })}`)
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    run(mode)
  }

  function changeMode(v: string) {
    if (!v) return
    const m = v as SearchMode
    setMode(m)
    // Re-run only an unedited query, so a half-typed edit is never sent.
    if (onSearch && !empty && q === urlQ) run(m)
  }

  return (
    <form role="search" onSubmit={submit} className="mx-auto flex w-full max-w-xl items-center gap-2">
      <div className="relative min-w-0 flex-1">
        <Input
          type="search"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={(narrow ? NARROW_PLACEHOLDER : PLACEHOLDER)[mode]}
          aria-label="Search"
          className="h-8 pr-9 [&::-webkit-search-cancel-button]:appearance-none"
        />
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="submit"
                variant="ghost"
                size="icon-xs"
                aria-label="Search"
                aria-disabled={empty || undefined}
                aria-busy={busy || undefined}
                className={cn(
                  'absolute right-1 top-1/2 -translate-y-1/2',
                  empty ? 'cursor-default text-muted-foreground opacity-50 hover:bg-transparent' : 'text-primary',
                  busy && 'cursor-progress',
                )}
              >
                {busy ? <Loader2 className="animate-spin" aria-hidden /> : <Search aria-hidden />}
              </Button>
            </TooltipTrigger>
            {empty && <TooltipContent sideOffset={6}>Type something to search</TooltipContent>}
            {busy && !empty && (
              <TooltipContent sideOffset={6}>{urlMode === 'analyze' ? 'Analyzing…' : 'Searching…'}</TooltipContent>
            )}
          </Tooltip>
        </TooltipProvider>
      </div>
      <ToggleGroup
        type="single"
        value={mode}
        onValueChange={changeMode}
        aria-label="Search mode"
        className="h-8 shrink-0 gap-0 rounded-lg bg-muted p-[3px] text-muted-foreground"
      >
        {(['find', 'analyze'] as const).map((m) => (
          <ToggleGroupItem
            key={m}
            value={m}
            className="h-full min-w-0 px-3 hover:bg-transparent data-[state=on]:bg-background data-[state=on]:text-foreground data-[state=on]:shadow-sm"
          >
            {m === 'find' ? 'Find' : 'Analyze'}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </form>
  )
}

export function AppHeader() {
  const me = useMe()
  const folder = useFolder()
  const logout = useLogout()
  const qc = useQueryClient()
  const navigate = useNavigate()

  async function signOut() {
    await logout.mutateAsync()
    qc.clear()
    navigate('/connect')
  }

  const setTheme = (t: Theme) => applyTheme(t)

  return (
    <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex max-w-[1480px] flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5">
        <Link to="/library" className="flex items-center gap-2 text-sm font-semibold">
          <span className="flex size-6 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Layers className="size-3.5" aria-hidden />
          </span>
          Document Intelligence
        </Link>
        <nav aria-label="Sections" className="flex items-center gap-0.5">
          <NavLink to="/library" className={navClass}>
            Library
          </NavLink>
          <NavLink to="/data" className={navClass}>
            Data
          </NavLink>
        </nav>
        <div className="order-last w-full min-w-0 md:order-none md:w-auto md:flex-1">
          <SearchBox />
        </div>
        <div className="ml-auto flex items-center gap-2">
          {folder.data && <SyncPill folder={folder.data} />}
          <Button variant="outline" size="sm" asChild>
            <Link to="/connect" title="Change folder">
              <FolderOpen aria-hidden />
              <span className="hidden max-w-40 truncate lg:inline">{folder.data?.name ?? 'Choose folder'}</span>
              <span className="sr-only lg:hidden">Folder</span>
            </Link>
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="Account menu" className="rounded-full">
                <Avatar className="size-7">
                  <AvatarFallback className="text-xs">{initials(me.data?.name, me.data?.email)}</AvatarFallback>
                </Avatar>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              <DropdownMenuLabel className="font-normal">
                <div className="text-sm font-medium">{me.data?.name ?? 'Signed in'}</div>
                <div className="truncate text-xs text-muted-foreground">{me.data?.email}</div>
              </DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => setTheme('system')}>
                <SunMoon aria-hidden /> System theme
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setTheme('light')}>
                <Sun aria-hidden /> Light
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => setTheme('dark')}>
                <Moon aria-hidden /> Dark
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => void signOut()}>
                <LogOut aria-hidden /> Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  )
}
