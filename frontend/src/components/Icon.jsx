const paths = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
  cake: <><path d="M4 20h16" /><path d="M5 20v-7.2c0-1.4 1.1-2.5 2.5-2.5h9c1.4 0 2.5 1.1 2.5 2.5V20" /><path d="M8 10.2V7.6c0-1.5 1.2-2.6 2.6-2.6h2.8C14.8 5 16 6.1 16 7.6v2.6" /><path d="M9 3.5c0 .8-.7 1.5-1.5 1.5S6 4.3 6 3.5 6.7 2 7.5 2 9 2.7 9 3.5Z" /><path d="M18 3.5c0 .8-.7 1.5-1.5 1.5S15 4.3 15 3.5 15.7 2 16.5 2 18 2.7 18 3.5Z" /><path d="M9 15h.01M15 15h.01" /></>,
  receipt: <><path d="M5 3.5h14v17l-2.5-1.6-2.5 1.6-2.5-1.6-2.5 1.6-2.5-1.6L5 20.5v-17Z" /><path d="M8.5 8h7M8.5 12h7M8.5 16h4" /></>,
  users: <><path d="M16 20v-1.5a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4V20" /><circle cx="9.5" cy="7" r="3.2" /><path d="M17 10.5a3 3 0 0 0 0-6M21 20v-1.5a4 4 0 0 0-2.5-3.7" /></>,
  package: <><path d="m4 7 8-4 8 4-8 4-8-4Z" /><path d="M4 7v10l8 4 8-4V7M12 11v10" /></>,
  plus: <path d="M12 5v14M5 12h14" />,
  search: <><circle cx="10.7" cy="10.7" r="6.4" /><path d="m16 16 4.5 4.5" /></>,
  bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  chevron: <path d="m9 18 6-6-6-6" />,
  chevronDown: <path d="m6 9 6 6 6-6" />,
  arrowRight: <path d="M5 12h14M13 6l6 6-6 6" />,
  trend: <><path d="m4 16 6-6 4 4 6-7" /><path d="M15 7h5v5" /></>,
  sparkle: <><path d="m12 3 1.5 5.1L18.5 10l-5 1.7L12 17l-1.5-5.3L5.5 10l5-1.9L12 3Z" /><path d="m19.5 16 .5 1.7 1.5.6-1.5.5-.5 1.7-.5-1.7-1.5-.5 1.5-.6.5-1.7Z" /></>,
  more: <><circle cx="5" cy="12" r="1" fill="currentColor" /><circle cx="12" cy="12" r="1" fill="currentColor" /><circle cx="19" cy="12" r="1" fill="currentColor" /></>,
  edit: <><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4 11.5-11.5Z" /></>,
  trash: <><path d="M4 7h16M10 11v5M14 11v5M6 7l1 14h10l1-14M9 7V4h6v3" /></>,
  archive: <><path d="M4 8h16v12H4zM3 4h18v4H3zM10 12h4" /></>,
  refresh: <><path d="M20 11a8 8 0 1 0 2 5.4" /><path d="M20 4v7h-7" /></>,
  alert: <><path d="M10.5 4.2 2.8 18a1.5 1.5 0 0 0 1.3 2.2h15.8a1.5 1.5 0 0 0 1.3-2.2L13.5 4.2a1.7 1.7 0 0 0-3 0Z" /><path d="M12 9v4M12 17h.01" /></>,
  check: <path d="m5 12 4.2 4.2L19 6.5" />,
  calendar: <><rect x="3.5" y="5" width="17" height="15.5" rx="2" /><path d="M7.5 3v4M16.5 3v4M3.5 10h17" /></>,
  card: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 10h18M7 15h3" /></>,
  download: <><path d="M12 3v12M7 10l5 5 5-5M4 20h16" /></>,
  filter: <path d="M4 6h16M7 12h10M10 18h4" />,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.5 2" /></>,
  logout: <><path d="M10 4H5v16h5M14 8l4 4-4 4M18 12H9" /></>,
  eye: <><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z" /><circle cx="12" cy="12" r="2.5" /></>,
  coffee: <><path d="M5 8h11v8a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4V8ZM16 10h2a2 2 0 0 1 0 4h-2M8 3c0 1.3-1.5 1.5-1.5 3M12 3c0 1.3-1.5 1.5-1.5 3" /></>,
  printer: <><polyline points="6 9 6 2 18 2 18 9" /><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" /><rect x="6" y="14" width="12" height="8" rx="1" /></>,
  cash: <><rect x="2" y="6" width="20" height="12" rx="2" /><circle cx="12" cy="12" r="2" /><path d="M6 12h.01M18 12h.01" /></>,
  creditCard: <><rect x="2" y="5" width="20" height="14" rx="2" /><line x1="2" y1="10" x2="22" y2="10" /></>,
  list: <><line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" /><line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" /></>,
  camera: <><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z" /><circle cx="12" cy="13" r="3" /></>
};

export function Icon({ name, size = 18, strokeWidth = 1.8, className = "", label }) {
  return (
    <svg
      className={`icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
    >
      {label ? <title>{label}</title> : null}
      {paths[name] || paths.sparkle}
    </svg>
  );
}
