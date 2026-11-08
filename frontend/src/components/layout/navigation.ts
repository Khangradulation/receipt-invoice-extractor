export interface NavItem {
  to: string;
  label: string;
  /** SVG path data (24x24, stroke icons). */
  icon: string;
}

/**
 * Sidebar entries. Only pages that are actually implemented are listed here;
 * the remaining pages (upload, documents, review, analytics, settings) are added in Phase 8.
 */
export const navItems: NavItem[] = [
  {
    to: '/',
    label: 'System status',
    icon: 'M3.75 13.5h3l2.25-6 4.5 12 2.25-6h4.5',
  },
];
