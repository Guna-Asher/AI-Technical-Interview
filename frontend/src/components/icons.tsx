// Small inline icons (decorative; always paired with text). No icon package.
type IconProps = { className?: string };

function Svg({ className = "size-4", children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={`shrink-0 ${className}`}
    >
      {children}
    </svg>
  );
}

export const IconCheck = (p: IconProps) => (
  <Svg {...p}>
    <path d="m4.5 10.5 3.5 3.5 7.5-8" />
  </Svg>
);
export const IconChevronDown = (p: IconProps) => (
  <Svg {...p}>
    <path d="m5 8 5 5 5-5" />
  </Svg>
);

export const IconAlert = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10 3.5 2.5 16.5h15z" />
    <path d="M10 8.5v3.5M10 14.5h.01" />
  </Svg>
);
export const IconInfo = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="10" cy="10" r="7.25" />
    <path d="M10 9.25V14M10 6.25h.01" />
  </Svg>
);
export const IconBook = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H16v12H5.5A1.5 1.5 0 0 0 4 16.5z" />
    <path d="M4 16.5A1.5 1.5 0 0 0 5.5 18H16v-3" />
  </Svg>
);
export const IconFile = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 2.75h6.5L15 6.25v11H5z" />
    <path d="M11.25 2.75v3.75H15" />
  </Svg>
);
export const IconUpload = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10 13.5V4M6.25 7.5 10 3.75l3.75 3.75M4 14.5v1.75h12V14.5" />
  </Svg>
);
export const IconClose = (p: IconProps) => (
  <Svg {...p}>
    <path d="m5 5 10 10M15 5 5 15" />
  </Svg>
);
export const IconMinus = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4.5 10h11" />
  </Svg>
);
export const IconArrowUp = (p: IconProps) => (
  <Svg {...p}>
    <path d="M10 16V4.5M5.5 9 10 4.5 14.5 9" />
  </Svg>
);

/** The product mark (same drawing as app/icon.svg). */
export function Mark({ className = "size-7" }: IconProps) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false" className={`shrink-0 ${className}`}>
      <rect width="32" height="32" rx="8" fill="var(--color-cobalt)" />
      <path
        fill="#fff"
        d="M9 11a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3h-5.2l-4.1 3.3a.6.6 0 0 1-1-.5V20.8A3 3 0 0 1 9 17.9z"
      />
      <rect x="12.5" y="11.2" width="7" height="1.9" rx=".95" fill="var(--color-cobalt)" />
      <rect x="12.5" y="14.5" width="4.6" height="1.9" rx=".95" fill="var(--color-cobalt)" />
    </svg>
  );
}
