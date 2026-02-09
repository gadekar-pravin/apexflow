export function ApexFlowLogo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <path
        d="M12 20L6 12.5M12 20L18 12.5M6 12.5L12 4M18 12.5L12 4"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <circle cx="12" cy="4" r="3" fill="currentColor" />
      <circle cx="6" cy="12.5" r="2.5" fill="currentColor" />
      <circle cx="18" cy="12.5" r="2.5" fill="currentColor" />
      <circle cx="12" cy="20" r="2.5" fill="currentColor" />
    </svg>
  )
}
