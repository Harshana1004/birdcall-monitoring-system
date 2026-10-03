// Placeholder logo: a perched bird with sound waves, in the app's greens.
// Swap this file for the real logo later; it is sized by `size`.

function Logo({ size = 34, title = "AvianAcoustics" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role="img"
      aria-label={title}
    >
      <defs>
        <linearGradient id="aa-logo-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1a7347" />
          <stop offset="1" stopColor="#0f3d2a" />
        </linearGradient>
        <linearGradient id="aa-logo-bird" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#c9f2db" />
          <stop offset="1" stopColor="#4fd08b" />
        </linearGradient>
      </defs>

      <rect width="48" height="48" rx="12" fill="url(#aa-logo-bg)" />

      {/* Bird */}
      <path
        d="M11 29c0-6.4 5-11.4 11.3-11.4 2.6 0 4.7.9 6.2 2.2l4.4-1.2-2.4 3.7c.5 1.3.7 2.6.7 3.9 0 6.5-5.4 10.8-11.6 10.8H11l3.4-3.6C12.3 32.7 11 31 11 29z"
        fill="url(#aa-logo-bird)"
      />
      <circle cx="25.5" cy="22.6" r="1.4" fill="#0f3d2a" />
      <path
        d="M16 31.5c3.2 1.4 7.3 1.2 10.3-1.1"
        stroke="#0f3d2a"
        strokeWidth="1.6"
        strokeLinecap="round"
        fill="none"
      />

      {/* Sound waves */}
      <path
        d="M36 15.5c2 2 3.2 4.7 3.2 7.6s-1.2 5.6-3.2 7.6"
        stroke="#7fe0ab"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
        opacity="0.9"
      />
      <path
        d="M39.6 11.8c3 2.9 4.8 6.9 4.8 11.3s-1.8 8.4-4.8 11.3"
        stroke="#4fd08b"
        strokeWidth="2"
        strokeLinecap="round"
        fill="none"
        opacity="0.55"
      />
    </svg>
  );
}


export default Logo;
