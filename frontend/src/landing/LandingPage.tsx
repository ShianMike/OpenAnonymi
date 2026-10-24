import './landing.css'
import { useEffect } from 'react'
import { ArrowRight } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { LandingNav } from './LandingNav'
import { LandingFormats } from './LandingFormats'
import { WorkflowStory } from './WorkflowStory'
import { LandingSecurity } from './LandingSecurity'
import { LandingQuestions } from './LandingQuestions'
import { LandingFooter } from './LandingFooter'
import { useLandingMotion } from './useLandingMotion'
import overview from './assets/overview-desktop-4k.jpg'
import overviewPhone from './assets/overview-phone-3x.jpg'

export function LandingPage({ signedIn, sessionError, onRetry }: {
  signedIn: boolean; sessionError?: string; onRetry: () => void
}) {
  const { root, sentinel, scrolled } = useLandingMotion()
  const { hash } = useLocation()
  const startTo = signedIn ? '/new' : '/sign-up'
  useEffect(() => {
    const oldTitle = document.title
    document.title = 'OpenAnonymi — Share the story. Keep control.'
    return () => { document.title = oldTitle }
  }, [])
  // Links such as /welcome#how-it-works arrive before the lazy page exists, so scroll once it renders.
  useEffect(() => {
    if (hash.length > 1) document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView()
  }, [hash])

  return (
    <div className="landing-page" ref={root}>
      <a className="skip-link" href="#main-content">Skip to content</a>
      <span className="landing-top-sentinel" ref={sentinel} aria-hidden="true" />
      <LandingNav signedIn={signedIn} startTo={startTo} scrolled={scrolled} />
      {sessionError && <div className="landing-session-error">
        <div className="landing-container landing-session-error-inner">
          <p role="alert">Workspace access is unavailable. You can still read about OpenAnonymi here.</p>
          <button className="landing-button landing-button-sm landing-button-secondary" type="button" onClick={onRetry}>Retry workspace access</button>
        </div>
      </div>}
      <main id="main-content" className="landing-main" tabIndex={-1}>
        <section className="landing-hero" aria-labelledby="landing-title">
          <div className="landing-container">
            <div className="landing-hero-copy">
              <h1 id="landing-title"><span>Share the story.</span> <span>Keep control.</span></h1>
              <p className="landing-hero-lede">OpenAnonymi flags personal details in your text and files. You decide what to replace, hide, or keep before sharing.</p>
              <div className="landing-hero-actions">
                <Link className="landing-button landing-button-lg" to={startTo}>Start a review <ArrowRight size={18} aria-hidden="true" /></Link>
                <a className="landing-button landing-button-lg landing-button-secondary" href="#how-it-works">See how it works</a>
              </div>
            </div>
            <figure className="landing-shot">
              <div className="landing-shot-frame">
                <picture>
                  <source media="(max-width: 640px)" srcSet={overviewPhone} width={1170} height={2532} />
                  <img src={overview} width={3840} height={2400} fetchPriority="high"
                    alt="The current OpenAnonymi workspace overview: review totals, progress, recent documents, and review status." />
                </picture>
              </div>
              <figcaption className="sr-only">Workspace overview with fictional reviews.</figcaption>
            </figure>
          </div>
        </section>
        <LandingFormats />
        <WorkflowStory />
        <LandingSecurity />
        <LandingQuestions signedIn={signedIn} startTo={startTo} />
      </main>
      <LandingFooter signedIn={signedIn} startTo={startTo} />
    </div>
  )
}
