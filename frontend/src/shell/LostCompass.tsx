import { useState } from 'react'
import { RotateCcw } from 'lucide-react'

const directions = ['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest']

export function LostCompass() {
  const [rotation, setRotation] = useState(38)
  const bearing = ((rotation % 360) + 360) % 360
  const north = bearing < 6 || bearing > 354
  const direction = directions[Math.round(bearing / 45) % directions.length]
  function setBearing(next: number) {
    setRotation((previous) => {
      const current = ((previous % 360) + 360) % 360
      return previous + ((next - current + 540) % 360) - 180
    })
  }

  return (
    <div className="lost-compass-experience">
      <div className="lost-coordinates" aria-hidden="true">
        <span>OFF THE MAP</span>
        <span>404 / UNKNOWN ROUTE</span>
      </div>
      <div className="lost-figure">
        <span className="lost-digit" aria-hidden="true">
          4
        </span>
        <div
          className="lost-compass"
          data-north={north}
          onPointerMove={(event) => {
            if (event.pointerType !== 'mouse') return
            const bounds = event.currentTarget.getBoundingClientRect()
            const x = event.clientX - bounds.x - bounds.width / 2
            const y = event.clientY - bounds.y - bounds.height / 2
            if (Math.hypot(x, y) > 12) {
              setBearing(Math.round(((Math.atan2(x, -y) * 180) / Math.PI + 360) % 360))
            }
          }}
          aria-hidden="true"
        >
          <div className="lost-compass-halo" />
          <svg className="lost-compass-dial" viewBox="0 0 240 240">
            <circle cx="120" cy="120" r="112" />
            <circle cx="120" cy="120" r="79" className="lost-compass-inner" />
            {Array.from({ length: 48 }, (_, i) => (
              <line
                key={i}
                x1="120"
                y1="20"
                x2="120"
                y2={i % 4 === 0 ? 29 : 24}
                transform={`rotate(${i * 7.5} 120 120)`}
                className={i % 4 === 0 ? 'major' : ''}
              />
            ))}
            <text x="120" y="52" className="north">
              N
            </text>
            <text x="193" y="125">
              E
            </text>
            <text x="120" y="198">
              S
            </text>
            <text x="47" y="125">
              W
            </text>
            <g className="lost-compass-needle" style={{ transform: `rotate(${rotation}deg)` }}>
              <path d="M120 65L133 120L120 115L107 120Z" className="needle-north" />
              <path d="M120 175L133 120L120 125L107 120Z" className="needle-south" />
            </g>
            <circle cx="120" cy="120" r="5" className="lost-compass-pin" />
          </svg>
        </div>
        <span className="lost-digit" aria-hidden="true">
          4
        </span>
      </div>
      <div className="lost-compass-controls">
        <label htmlFor="compass-bearing">Find your bearings</label>
        <div className="lost-bearing-row">
          <input
            id="compass-bearing"
            type="range"
            min="0"
            max="359"
            value={bearing}
            aria-label="Compass direction"
            aria-valuetext={`${bearing} degrees, ${direction}`}
            onChange={(event) => setBearing(Number(event.target.value))}
          />
          <button type="button" onClick={() => setBearing(0)}>
            <RotateCcw size={14} aria-hidden="true" /> Find north
          </button>
        </div>
        <p className="lost-bearing-status" role="status">
          <span className={north ? 'is-north' : ''} aria-hidden="true" />
          {north
            ? 'North found. A familiar place is one click away.'
            : `Facing ${direction}. Turn the compass or find north.`}
        </p>
      </div>
    </div>
  )
}
