import { Check, FileText } from 'lucide-react'
import { Brand } from '../ui/Brand'
import { demoOutput, examples } from './demoModel'

export function PrivacyOrbit() {
  return (
    <div className="privacy-orbit landing-loop-scene" aria-hidden="true">
      <div className="privacy-document privacy-document-source">
        <div><FileText size={16} /><span>Original</span></div>
        <strong>{examples[0].title}</strong>
        <p>{demoOutput(examples[0].parts, {})}</p>
      </div>
      <div className="privacy-orbit-hub">
        <div className="privacy-orbit-track privacy-orbit-track-outer" />
        <div className="privacy-orbit-track privacy-orbit-track-inner" />
        <div className="privacy-orbit-center"><Brand compact /></div>
      </div>
      <div className="privacy-document privacy-document-output">
        <div><Check size={16} /><span>Reviewed</span></div>
        <strong>{examples[0].title}</strong>
        <p>{demoOutput(examples[0].parts, { person: 'label', email: 'redact', phone: 'keep' })}</p>
      </div>
    </div>
  )
}
