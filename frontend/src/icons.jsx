// Minimal hand-rolled line icons - deliberately not a dependency (lucide,
// heroicons, etc). 20x20 viewBox, stroke-based, inherits color via currentColor.
const base = { viewBox: "0 0 20 20", fill: "none", stroke: "currentColor", strokeWidth: 1.6, strokeLinecap: "round", strokeLinejoin: "round" };

export const GridIcon = (p) => (
  <svg {...base} {...p}><rect x="2.5" y="2.5" width="6" height="6" rx="1"/><rect x="11.5" y="2.5" width="6" height="6" rx="1"/><rect x="2.5" y="11.5" width="6" height="6" rx="1"/><rect x="11.5" y="11.5" width="6" height="6" rx="1"/></svg>
);

export const PlusCircleIcon = (p) => (
  <svg {...base} {...p}><circle cx="10" cy="10" r="7.25"/><path d="M10 7v6M7 10h6"/></svg>
);

export const ListIcon = (p) => (
  <svg {...base} {...p}><path d="M4 5.5h12M4 10h12M4 14.5h12"/><circle cx="4" cy="5.5" r="0" /></svg>
);

export const BookIcon = (p) => (
  <svg {...base} {...p}><path d="M4 3.5h5a2 2 0 0 1 2 2v11a1.5 1.5 0 0 0-1.5-1.5H4z"/><path d="M16 3.5h-5a2 2 0 0 0-2 2v11a1.5 1.5 0 0 1 1.5-1.5H16z"/></svg>
);

export const BarChartIcon = (p) => (
  <svg {...base} {...p}><path d="M4 16.5V9M10 16.5V3.5M16 16.5v-5"/></svg>
);

export const TerminalIcon = (p) => (
  <svg {...base} {...p}><rect x="2.5" y="3.5" width="15" height="13" rx="1.5"/><path d="M5.5 8l3 2.5-3 2.5M10.5 13h4"/></svg>
);

export const CheckCircleIcon = (p) => (
  <svg {...base} {...p}><circle cx="10" cy="10" r="7.25"/><path d="M6.8 10.2l2.1 2.1 4.3-4.6"/></svg>
);

export const CompassIcon = (p) => (
  <svg {...base} {...p}><circle cx="10" cy="10" r="7.25"/><path d="M12.8 7.2l-1.6 4-4 1.6 1.6-4z"/></svg>
);

export const AlertTriangleIcon = (p) => (
  <svg {...base} {...p}><path d="M10 3.2l7.8 13.3H2.2z"/><path d="M10 8.2v3.2"/><circle cx="10" cy="13.8" r="0.15" fill="currentColor"/></svg>
);

export const HelpCircleIcon = (p) => (
  <svg {...base} {...p}><circle cx="10" cy="10" r="7.25"/><path d="M7.8 8a2.2 2.2 0 1 1 3.2 2c-.7.5-1 1-1 1.8"/><circle cx="10" cy="14" r="0.15" fill="currentColor"/></svg>
);

export const GlobeIcon = (p) => (
  <svg {...base} {...p}><circle cx="10" cy="10" r="7.25"/><path d="M2.75 10h14.5M10 2.75c2.2 2.1 2.2 12.4 0 14.5M10 2.75c-2.2 2.1-2.2 12.4 0 14.5"/></svg>
);

export const ClockIcon = (p) => (
  <svg {...base} {...p}><circle cx="10" cy="10" r="7.25"/><path d="M10 5.5V10l3 2"/></svg>
);
