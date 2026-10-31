import { useId } from "react";

export function Brand({ className = "" }: { className?: string }) {
  const gradientId = useId().replace(/:/g, "");

  return (
    <span className={`brand ${className}`.trim()}>
      <svg
        className="brand-mark"
        viewBox="0 0 44 44"
        aria-hidden="true"
        focusable="false"
      >
        <defs>
          <linearGradient id={gradientId} x1="4" y1="38" x2="40" y2="6">
            <stop offset="0%" stopColor="#38e8ff" />
            <stop offset="52%" stopColor="#5b8dff" />
            <stop offset="100%" stopColor="#a78bfa" />
          </linearGradient>
        </defs>
        <rect
          x="1.5"
          y="1.5"
          width="41"
          height="41"
          rx="13"
          fill={`url(#${gradientId})`}
          opacity="0.12"
        />
        <rect
          x="1.5"
          y="1.5"
          width="41"
          height="41"
          rx="13"
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeOpacity="0.55"
        />
        <path
          d="M11.5 29.5 L21 14.5 L33 29.5"
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx="11.5" cy="29.5" r="3.3" fill="#05070f" stroke={`url(#${gradientId})`} strokeWidth="2" />
        <circle cx="21" cy="14.5" r="3.3" fill="#05070f" stroke={`url(#${gradientId})`} strokeWidth="2" />
        <circle cx="33" cy="29.5" r="3.3" fill="#05070f" stroke={`url(#${gradientId})`} strokeWidth="2" />
      </svg>
      <span className="brand-word">
        Mechanism<span className="brand-word-accent"> AI</span>
      </span>
    </span>
  );
}
