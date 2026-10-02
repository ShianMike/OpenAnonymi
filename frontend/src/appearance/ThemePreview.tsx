import { Check, FileText, Fingerprint, Search } from 'lucide-react'
import type { AppearancePreference } from './appearanceStore'

/** Decorative previews use their own palettes, independent of the chosen theme. */
export function ThemePreview({ mode }: { mode: AppearancePreference }) {
  if (mode === 'system') {
    return (
      <span className="theme-preview theme-preview--system" aria-hidden="true">
        <ThemePreview mode="light" />
        <ThemePreview mode="dark" />
      </span>
    )
  }
  return (
    <span className={`theme-preview theme-preview--${mode}`} aria-hidden="true">
      <span className="theme-preview-sidebar">
        <Fingerprint size={15} strokeWidth={1.5} />
        <span />
        <span className="theme-preview-nav-active" />
        <span />
      </span>
      <span className="theme-preview-main">
        <span className="theme-preview-heading">Your workspace</span>
        <span className="theme-preview-search"><Search size={10} /> Search documents</span>
        <span className="theme-preview-document">
          <FileText size={13} />
          <span>Interview notes<small>Just updated</small></span>
          <Check size={11} />
        </span>
        <span className="theme-preview-document theme-preview-document--second">
          <FileText size={13} />
          <span>Research summary<small>Ready to share</small></span>
          <Check size={11} />
        </span>
      </span>
    </span>
  )
}
