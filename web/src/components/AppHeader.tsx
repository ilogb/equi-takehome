import { useQueryClient } from '@tanstack/react-query'
import { FolderOpen, Layers, LogOut, Moon, Search, Sun, SunMoon } from 'lucide-react'
import { useState, type FormEvent } from 'react'
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
import { useFolder, useLogout, useMe } from '@/lib/api'
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

function SearchBox() {
  const navigate = useNavigate()
  const { pathname, search } = useLocation()
  const params = new URLSearchParams(search)
  const onSearch = pathname === '/search'
  const [text, setText] = useState(onSearch ? (params.get('q') ?? '') : '')
  const [mode, setMode] = useState<SearchMode>(params.get('mode') === 'analyze' ? 'analyze' : 'find')

  function submit(e: FormEvent) {
    e.preventDefault()
    const q = text.trim()
    if (!q) return
    navigate(`/search?${new URLSearchParams({ q, mode })}`)
  }

  return (
    <form role="search" onSubmit={submit} className="mx-auto flex w-full max-w-xl items-center gap-2">
      <div className="relative min-w-0 flex-1">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
        <Input
          type="search"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={mode === 'find' ? 'Find documents and figures' : 'Ask a question about your funds'}
          aria-label="Search"
          className="h-8 pl-8"
        />
      </div>
      <ToggleGroup
        type="single"
        variant="outline"
        size="sm"
        value={mode}
        onValueChange={(v) => v && setMode(v as SearchMode)}
        aria-label="Search mode"
      >
        <ToggleGroupItem value="find">Find</ToggleGroupItem>
        <ToggleGroupItem value="analyze">Analyze</ToggleGroupItem>
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
