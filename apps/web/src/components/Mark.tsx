// DepositTrack mark: a receipt with a five-step ladder — an FDR and the Trust Ladder.
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 22 22" aria-hidden="true">
      <rect x="1.5" y="1.5" width="19" height="19" rx="4" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <rect x="5" y="13" width="2" height="4" fill="currentColor" />
      <rect x="8.25" y="11" width="2" height="6" fill="currentColor" />
      <rect x="11.5" y="9" width="2" height="8" fill="currentColor" />
      <rect x="14.75" y="7" width="2" height="10" fill="var(--hue)" />
      <path d="M5 5.5h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}
