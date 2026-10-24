import { Component, type ReactNode } from 'react'
import { LoadingFailure } from './LoadingFailure'
import type { BootTone } from './bootScreen'

/** A rejected lazy import must end loading with a useful action. Never reload automatically. */
export class PageLoadBoundary extends Component<{ children: ReactNode; fullScreen?: boolean; tone?: BootTone }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) return <LoadingFailure title="This page couldn’t open"
      message="The connection may have been interrupted, or this tab may be using an older version."
      onRetry={() => window.location.reload()} fullScreen={this.props.fullScreen} tone={this.props.tone} protectEdits />
    return this.props.children
  }
}
