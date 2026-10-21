export const CitaloSymbol = ({ className = "h-9 w-9" }) => (
  <svg viewBox="0 0 100 100" className={className} aria-hidden="true">
    <rect x="8" y="24" width="84" height="58" rx="15" fill="#FFB020" />
    <path d="M26 78 L26 96 L46 80 Z" fill="#FFB020" />
    <line x1="34" y1="12" x2="34" y2="36" stroke="#2E1A47" strokeWidth="9" strokeLinecap="round" />
    <line x1="66" y1="12" x2="66" y2="36" stroke="#2E1A47" strokeWidth="9" strokeLinecap="round" />
    <polyline points="31,52 45,64 70,41" fill="none" stroke="#2E1A47" strokeWidth="9" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

export const CitaloLogo = ({ light = false, size = "text-2xl", symbol = "h-9 w-9", tagline = false, testid = "citalo-logo" }) => (
  <div className="inline-flex items-center gap-2.5" data-testid={testid}>
    <CitaloSymbol className={symbol} />
    <div className="leading-none">
      <div className={`${size} font-heading font-extrabold tracking-[-0.04em] ${light ? "text-[#FFF7E6]" : "text-[#2E1A47]"}`}>Cítalo</div>
      {tagline && <div className={`mt-1 text-xs ${light ? "text-[#FFF7E6]/70" : "text-[#2E1A47]/70"}`}>Tu agenda, por WhatsApp.</div>}
    </div>
  </div>
);
