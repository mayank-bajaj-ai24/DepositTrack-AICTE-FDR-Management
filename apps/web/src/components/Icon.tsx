// One outline icon set at a 1.5px stroke, drawn for DepositTrack's destinations.

const PATHS: Record<string, string> = {
  overview: "M2.5 13.5h11M4 11V7.5M7 11V4.5M10 11V6M13 11V8.5",
  queue: "M2.5 4h11M2.5 8h7M2.5 12h4.5M12 9.5v4M10 11.5l2 2 2-2",
  instruments: "M3.5 1.75h6.25l2.75 2.75v9.75h-9zM9.75 1.75V4.5h2.75M5.75 8h4.5M5.75 10.5h4.5",
  cases: "M5.5 4V2.75h5V4M2.25 4h11.5v8.75H2.25zM2.25 7.5h11.5M7 7.5v1.5h2V7.5",
  reports: "M3 1.75h10v12.5H3zM5.5 11V8.5M8 11V5.5M10.5 11V7",
  audit: "M8 1.75l5 2v4c0 3-2.2 5.3-5 6.5-2.8-1.2-5-3.5-5-6.5v-4zM5.75 8l1.6 1.6 3-3.2",
  verify: "M3.5 1.75h6.25l2.75 2.75v9.75h-9zM5.5 9l1.75 1.75L10.5 7.5",
  admin: "M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4",
  my: "M2 6.5L8 2.5l6 4M3.5 6v7.5h9V6M6.5 13.5V9.5h3v4",
  submit: "M8 10.5V2.5M5 5.5l3-3 3 3M2.5 10v3.5h11V10",
  bank: "M1.75 6L8 2.25 14.25 6zM3 6.5v5.5M6.25 6.5v5.5M9.75 6.5v5.5M13 6.5v5.5M1.75 13.75h12.5",
  search: "M7 2.25a4.75 4.75 0 1 0 0 9.5 4.75 4.75 0 0 0 0-9.5zM10.5 10.5l3.25 3.25",
  sun: "M8 5a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3 3l1 1M12 12l1 1M3 13l1-1M12 4l1-1",
  moon: "M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7z",
  menu: "M2.5 4.5h11M2.5 8h11M2.5 11.5h11",
  close: "M3.5 3.5l9 9M12.5 3.5l-9 9",
  signout: "M6 2.5H3v11h3M10 5l3 3-3 3M13 8H6",
  upload: "M8 11V2.5M5 5.5l3-3 3 3M2.5 10.5v3h11v-3",
  download: "M8 2.5V11M5 8l3 3 3-3M2.5 10.5v3h11v-3",
  refresh: "M13 3v3.5H9.5M3 13V9.5h3.5M12.4 6.5A5 5 0 0 0 3.6 6M3.6 9.5a5 5 0 0 0 8.8.5",
  check: "M3 8.5l3 3 7-7",
  arrow: "M3 8h10M9 4l4 4-4 4",
  back: "M13 8H3M7 4L3 8l4 4",
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 16, label }: { name: IconName | string; size?: number; label?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <path d={PATHS[name] ?? ""} />
    </svg>
  );
}
