import { FileText } from 'lucide-react'
import { AuthIllustration, type AuthIllustrationKind } from './AuthIllustration'
import { useLoadingMotion } from '../loading/useLoadingMotion'

const assurances: { icon: AuthIllustrationKind; text: string }[] = [
  { icon: 'scan', text: 'Detection suggests. You decide every finding.' },
  { icon: 'document', text: 'Your original stays intact.' },
  { icon: 'clock', text: 'Saved content expires on a schedule you can see.' },
]

/** The product story beside the form. The specimen is decorative and entirely fictional. */
export function AuthStory() {
  const motion = useLoadingMotion<HTMLElement>()
  return (
    <aside ref={motion} className="auth-story" aria-label="About OpenAnonymi">
      <div className="auth-story-silk" aria-hidden="true">
        <span className="auth-silk auth-silk--depth" />
        <span className="auth-silk auth-silk--light" />
        <span className="auth-silk-grain" />
      </div>
      <div className="auth-story-body">
        <p className="auth-display">
          Share the story. <span>Keep identities private.</span>
        </p>
        <figure className="auth-specimen" aria-hidden="true">
          <div className="auth-specimen-head">
            <FileText size={15} strokeWidth={1.7} />
            <span>Interview notes</span>
            <span className="auth-specimen-badge">Reviewed</span>
          </div>
          <div className="auth-specimen-row">
            <span className="auth-specimen-tag">Original</span>
            <p>
              <mark>Maya Chen</mark> said the invite felt unclear. Reach her at <mark>maya@example.com</mark>.
            </p>
          </div>
          <div className="auth-specimen-row auth-specimen-row--output">
            <span className="auth-specimen-tag">Reviewed output</span>
            <p>
              <code>PERSON_001</code> said the invite felt unclear. Reach her at <code>EMAIL_001</code>.
            </p>
          </div>
        </figure>
        <ul className="auth-assurances">
          {assurances.map(({ icon, text }) => (
            <li key={text}>
              <span className="auth-assurance-icon">
                <AuthIllustration kind={icon} size={40} />
              </span>
              {text}
            </li>
          ))}
        </ul>
      </div>
    </aside>
  )
}
