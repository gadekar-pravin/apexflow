export function ApexFlowLogo({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      {/* Brain left hemisphere */}
      <path
        d="M9.5 2C7.5 2 5.5 3.5 5 5.5C4.3 5.7 3 6.7 3 8.5C3 9.8 3.5 10.8 4 11.3C3.5 12 3 13 3 14.5C3 16.5 4.5 18 6 18.5C6.5 20 8 21.5 10 22C11 22.2 11.5 22 12 22"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      {/* Brain right hemisphere */}
      <path
        d="M14.5 2C16.5 2 18.5 3.5 19 5.5C19.7 5.7 21 6.7 21 8.5C21 9.8 20.5 10.8 20 11.3C20.5 12 21 13 21 14.5C21 16.5 19.5 18 18 18.5C17.5 20 16 21.5 14 22C13 22.2 12.5 22 12 22"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      {/* Center divide */}
      <path
        d="M12 2V22"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      {/* Neural folds */}
      <path
        d="M12 5.5C10 5.5 7.5 7 7.5 9"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M12 5.5C14 5.5 16.5 7 16.5 9"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M12 11C10 11 6.5 12.5 6 14.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M12 11C14 11 17.5 12.5 18 14.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M12 16.5C10.5 16.5 8 17.5 7.5 18.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <path
        d="M12 16.5C13.5 16.5 16 17.5 16.5 18.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  )
}
