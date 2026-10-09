import { useEffect } from 'react'
import { ArrowDownRight, ArrowRight, Check, Pause, Play } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Brand } from '../ui/Brand'
import { AppCredit } from '../ui/AppCredit'
import { LandingNav } from './LandingNav'
import { ReviewDemo } from './ReviewDemo'
import { WorkflowStory } from './WorkflowStory'
import { LandingQuestions } from './LandingQuestions'
import { useLandingMotion } from './useLandingMotion'
import { LandingBackground } from './LandingBackground'
import { PrivacyOrbit } from './PrivacyOrbit'
import './landing.css'

export function LandingPage({ signedIn, sessionError, onRetry }: {
  signedIn: boolean; sessionError?: string; onRetry: () => void
}) {
  const { root, paused, reduced, toggleMotion } = useLandingMotion()
  useEffect(() => {
    const oldTitle = document.title
    document.title = 'OpenAnonymi — Share the story. Keep control.'
    return () => { document.title = oldTitle }
  }, [])

  return (
    <div className="landing-page" ref={root} data-paused={paused}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <LandingBackground />
      <LandingNav signedIn={signedIn} />
      {sessionError && <div className="landing-session-error landing-container"><p role="alert">Workspace access is unavailable. You can still explore this example.</p><button type="button" onClick={onRetry}>Retry workspace access</button></div>}
      <main id="main-content" className="landing-main" tabIndex={-1}>
        <section className="landing-hero landing-container" aria-labelledby="landing-title">
          <div className="landing-hero-copy">
            <span className="landing-eyebrow landing-hero-eyebrow"><span className="landing-living-dot" aria-hidden="true" /> Privacy, on your terms.</span>
            <h1 id="landing-title"><span>Share the story.</span><span>Keep control.</span></h1>
            <p className="landing-hero-description">Review personal details before you share.</p>
            <div className="landing-hero-actions">
              <Link className="landing-button" to={signedIn ? '/new' : '/sign-up'}>Start a review <ArrowRight size={18} aria-hidden="true" /></Link>
              <a className="landing-try-link" href="#try-review">Explore the demo <ArrowDownRight size={18} aria-hidden="true" /></a>
            </div>
            <div className="landing-hero-assurance"><span><Check size={14} aria-hidden="true" /> Your decisions</span><span><Check size={14} aria-hidden="true" /> Encrypted drafts</span><span><Check size={14} aria-hidden="true" /> Review before sharing</span></div>
          </div>
          <figure className="landing-hero-visual" data-landing-reveal>
            <PrivacyOrbit />
            <figcaption>Fictional example</figcaption>
          </figure>
        </section>
        <section className="landing-demo-section landing-container" aria-labelledby="demo-title">
          <div className="landing-section-heading" data-landing-reveal><h2 id="demo-title">Try it for yourself.</h2><p>Pick a detail. Choose what stays.</p></div>
          <ReviewDemo />
        </section>
        <WorkflowStory signedIn={signedIn} />
        <LandingQuestions signedIn={signedIn} />
      </main>
      <footer className="landing-footer landing-container">
        <div><Link to="/welcome" aria-label="OpenAnonymi home"><Brand /></Link></div>
        <nav aria-label="Landing page footer"><a href="#how-it-works">The process</a><Link to={signedIn ? '/continue' : '/sign-in'}>{signedIn ? 'Continue review' : 'Sign in'}</Link><button className="landing-motion-button" type="button" disabled={reduced} aria-pressed={paused} onClick={toggleMotion}>
          {paused ? <Play size={14} aria-hidden="true" /> : <Pause size={14} aria-hidden="true" />}{reduced ? 'Reduced motion enabled' : paused ? 'Play animations' : 'Pause animations'}</button></nav>
        <AppCredit />
      </footer>
    </div>
  )
}
