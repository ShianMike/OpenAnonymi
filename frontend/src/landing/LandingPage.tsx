import { useEffect } from 'react'
import { ArrowDownRight, ArrowRight, Check, Pause, Play, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Brand } from '../ui/Brand'
import { LandingNav } from './LandingNav'
import { ReviewDemo } from './ReviewDemo'
import { WorkflowStory } from './WorkflowStory'
import { LandingQuestions } from './LandingQuestions'
import { useLandingMotion } from './useLandingMotion'
import { LandingBackground } from './LandingBackground'
import './landing.css'
import './glass.css'

export function LandingPage({ signedIn, sessionError, onRetry }: {
  signedIn: boolean; sessionError?: string; onRetry: () => void
}) {
  const { root, paused, reduced, toggleMotion } = useLandingMotion()
  useEffect(() => {
    const oldTitle = document.title
    document.title = 'OpenAnonymi — Your words. Less exposure.'
    return () => { document.title = oldTitle }
  }, [])

  return (
    <div className="landing-page" ref={root} data-paused={paused}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <LandingBackground paused={paused} />
      <LandingNav signedIn={signedIn} />
      {sessionError && <div className="landing-session-error landing-container"><p role="alert">Workspace access is unavailable. You can still explore this example.</p><button type="button" onClick={onRetry}>Retry workspace access</button></div>}
      <main id="main-content" className="landing-main" tabIndex={-1}>
        <section className="landing-hero landing-container landing-loop-scene" aria-labelledby="landing-title">
          <div className="landing-hero-copy">
            <span className="landing-eyebrow landing-hero-eyebrow"><span className="landing-living-dot" aria-hidden="true" /> A little more private.</span>
            <h1 id="landing-title"><span className="landing-title-line"><span>Your words.</span></span><span className="landing-title-line"><span>Less exposure.</span></span></h1>
            <p className="landing-hero-description">Share the insight, the feedback, the story.<br className="landing-desktop-break" /> Give the personal details a little more thought.</p>
            <div className="landing-hero-actions">
              <Link className="landing-button" to={signedIn ? '/new' : '/sign-up'}>Start a review <ArrowRight size={18} aria-hidden="true" /></Link>
              <a className="landing-try-link" href="#try-review">Try a little review <ArrowDownRight size={19} aria-hidden="true" /></a>
            </div>
            <div className="landing-hero-assurance"><ShieldCheck size={16} strokeWidth={1.5} aria-hidden="true" /> Suggestions help. Your judgment leads.</div>
            <div className="landing-hero-bottom"><span className="landing-small-rule" aria-hidden="true" /><span>More thought.<br /><strong>Less unnecessary exposure.</strong></span></div>
          </div>
          <ReviewDemo />
        </section>
        <div className="landing-principles landing-container" data-landing-reveal>
          <span>Made for considered sharing.</span>
          <ul><li><Check size={16} aria-hidden="true" /> Your decisions</li><li><Check size={16} aria-hidden="true" /> Local suggestions</li><li><Check size={16} aria-hidden="true" /> A reviewed version</li></ul>
        </div>
        <WorkflowStory signedIn={signedIn} />
        <LandingQuestions signedIn={signedIn} />
      </main>
      <footer className="landing-footer landing-container">
        <div><Link to="/welcome" aria-label="OpenAnonymi home"><Brand /></Link><p>A little care. A lot more privacy.</p></div>
        <nav aria-label="Landing page footer"><a href="#how-it-works">The process</a><Link to={signedIn ? '/continue' : '/sign-in'}>{signedIn ? 'Continue review' : 'Sign in'}</Link><button className="landing-motion-button" type="button" disabled={reduced} aria-pressed={paused} onClick={toggleMotion}>
          {paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}{reduced ? 'Reduced motion enabled' : paused ? 'Play animations' : 'Pause animations'}</button></nav>
        <small>OpenAnonymi · Privacy review</small>
      </footer>
    </div>
  )
}
