import { PrivacyGlyph } from './PrivacyGlyph'

export function PrivacyOrbit() {
  return (
    <div className="privacy-orbit landing-loop-scene" aria-hidden="true">
      <div className="privacy-orbit-track privacy-orbit-track-outer" />
      <div className="privacy-orbit-track privacy-orbit-track-inner" />
      <div className="privacy-orbit-center"><PrivacyGlyph kind="fingerprint" size={78} /></div>
      <div className="privacy-orbit-satellite"><PrivacyGlyph kind="document" size={39} /></div>
      <div className="privacy-orbit-satellite"><PrivacyGlyph kind="scan" size={39} /></div>
      <div className="privacy-orbit-satellite"><PrivacyGlyph kind="shield" size={39} /></div>
      <span className="privacy-orbit-note">Your review.<br /><strong>Your call.</strong></span>
    </div>
  )
}
