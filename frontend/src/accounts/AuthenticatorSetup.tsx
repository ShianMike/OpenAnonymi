import type { EnrollmentView } from '../api/client'
import './security.css'

export function AuthenticatorSetup({ enrollment }: { enrollment: EnrollmentView }) {
  return (
    <div className="authenticator-setup">
      <p>Scan this code with your authenticator app, or enter the manual key.</p>
      <svg role="img" aria-label="Authenticator setup QR code" className="authenticator-qr"
        viewBox={`0 0 ${enrollment.qr_size} ${enrollment.qr_size}`} shapeRendering="crispEdges">
        <rect width={enrollment.qr_size} height={enrollment.qr_size} fill="white" />
        <path d={enrollment.qr_svg_path} fill="black" />
      </svg>
      <div className="authenticator-key"><strong>Manual key</strong><code>{enrollment.manual_key}</code></div>
      <small>Keep this key private. Setup expires at {new Date(enrollment.expires_at).toLocaleTimeString()}.</small>
    </div>
  )
}

export function BackupCodes({ codes, onSaved }: { codes: string[]; onSaved: () => void }) {
  return (
    <section className="backup-codes" aria-labelledby="backup-codes-title">
      <h3 id="backup-codes-title">Save your backup codes</h3>
      <p>Each code works once if you lose access to your authenticator. Store them somewhere private. They are shown only now.</p>
      <ul>{codes.map((code) => <li key={code}><code>{code}</code></li>)}</ul>
      <button type="button" onClick={onSaved}>I saved my backup codes</button>
    </section>
  )
}
