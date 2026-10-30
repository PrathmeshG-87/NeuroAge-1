import React from 'react'
import { ChevronRight, Menu } from 'lucide-react'
import { useLocation } from 'react-router-dom'

const routeLabels: Record<string, string> = {
  '/assessment': 'Assessment',
  '/assessments': 'Assessments',
  '/reports': 'Reports',
  '/progress': 'Progress',
  '/methodology': 'Methodology',
  '/settings': 'Settings',
}

interface TopBarProps {
  onMenuClick: () => void
}

export const TopBar: React.FC<TopBarProps> = ({ onMenuClick }) => {
  const location = useLocation()
  const pathname = location.pathname

  const segments = pathname
    .split('/')
    .filter(Boolean)
    .map((segment, index, all) => {
      const path = `/${all.slice(0, index + 1).join('/')}`
      return {
        label:
          routeLabels[path] ??
          (all[index - 1] === 'assessments'
            ? 'Assessment results'
            : segment.replace(/-/g, ' ')),
        path,
      }
    })

  const currentLabel = segments.at(-1)?.label ?? 'Overview'

  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.08] bg-[#111217]/80 backdrop-blur-md">
      <div className="flex h-16 items-center justify-between gap-3 px-4 sm:px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-[#0a0b0e] text-[#ebecef] md:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5eead4]"
            aria-label="Open navigation menu"
            onClick={onMenuClick}
          >
            <Menu className="h-4 w-4" />
          </button>

          <div className="hidden min-w-0 items-center gap-2 text-xs font-mono text-[#8d909c] sm:flex">
            <span className="uppercase tracking-[0.18em] text-[#8d909c]">
              Workspace
            </span>
            {segments.length > 0 && (
              <>
                <ChevronRight className="h-3.5 w-3.5" />
                <span className="truncate text-[#ebecef]">{currentLabel}</span>
              </>
            )}
          </div>
        </div>

      </div>
    </header>
  )
}
