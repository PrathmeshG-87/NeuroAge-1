import React from 'react'
import { NavLink } from 'react-router-dom'
import {
  Brain,
  FileText,
  Gauge,
  HelpCircle,
  Layers3,
  Settings,
  X,
} from 'lucide-react'
import { cn } from '@/utils/cn'
import { appConfig } from '@/config/env'

const links = [
  { to: '/assessment', label: 'Assessment', icon: Gauge },
  { to: '/reports', label: 'Reports', icon: FileText },
  { to: '/methodology', label: 'Methodology', icon: Layers3 },
  { to: '/settings', label: 'Settings', icon: Settings },
]

interface SidebarProps {
  mobileOpen: boolean
  onClose: () => void
}

export const Sidebar: React.FC<SidebarProps> = ({ mobileOpen, onClose }) => {
  const content = (
    <aside className="flex h-full w-full flex-col border-r border-white/[0.08] bg-[#111217] p-4">
      <div className="flex items-center justify-between border-b border-white/[0.06] pb-4">
        <NavLink
          to="/"
          onClick={onClose}
          aria-label="NeuroAge home"
          className="flex items-center gap-3 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5eead4]"
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-xl border border-[#5eead4]/35 bg-[#5eead4]/12 text-[#5eead4]">
            <Brain className="h-5 w-5" />
          </div>
          <div>
            <div className="text-base font-semibold text-[#ebecef]">
              NeuroAge
            </div>
            <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[#8d909c]">
              Research Console
            </div>
          </div>
        </NavLink>

        <button
          type="button"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 bg-[#0a0b0e] text-[#ebecef] md:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5eead4]"
          aria-label="Close navigation menu"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <nav className="mt-6 space-y-1">
        {links.map((link) => {
          const Icon = link.icon

          return (
            <NavLink
              key={link.to}
              to={link.to}
              onClick={onClose}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5eead4]',
                  isActive
                    ? 'border border-[#5eead4]/20 bg-[#171921] text-[#5eead4]'
                    : 'text-[#c6c9d2] hover:bg-white/5 hover:text-[#ebecef]',
                )
              }
            >
              <Icon className="h-4 w-4" />
              <span>{link.label}</span>
            </NavLink>
          )
        })}
      </nav>

      <div className="mt-auto rounded-2xl border border-white/[0.08] bg-[#0a0b0e] p-3 text-xs text-[#8d909c]">
        <div className="flex items-center gap-1.5 text-[#ebecef]">
          <HelpCircle className="h-3.5 w-3.5 text-[#5eead4]" />
          <span className="font-medium">Academic Edition</span>
        </div>
        <p className="mt-2 text-[11px] leading-relaxed">
          {appConfig.isDemoMode
            ? 'Demo mode only. Configure the API to submit a real assessment.'
            : 'Live API mode. Assessment access is protected by a private token.'}
        </p>
      </div>
    </aside>
  )

  return (
    <>
      <div className="hidden w-72 shrink-0 md:block">{content}</div>

      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/50 transition-opacity md:hidden',
          mobileOpen ? 'opacity-100' : 'pointer-events-none opacity-0',
        )}
        aria-hidden={!mobileOpen}
        onClick={onClose}
      />

      <div
        className={cn(
          'fixed inset-y-0 left-0 z-50 w-72 -translate-x-full transition-transform duration-200 md:hidden',
          mobileOpen && 'translate-x-0',
        )}
        aria-label="Mobile navigation"
      >
        {content}
      </div>
    </>
  )
}
