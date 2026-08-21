import type { Role } from "../../features/auth/useSession";
import type { IconName } from "../ui/Icon";

export interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  roles: Role[];
}

export interface NavGroup {
  heading: string;
  items: NavItem[];
}

const ALL_ROLES: Role[] = [
  "CREDIT_ANALYST",
  "FRAUD_REVIEWER",
  "CREDIT_POLICY_OWNER",
  "AUDITOR",
];

const NEW_CASE_ROLES: Role[] = ["CREDIT_ANALYST", "CREDIT_POLICY_OWNER"];

/** The complete navigation, grouped. Routes here must exist in AppRoutes. */
const NAV_GROUPS: NavGroup[] = [
  {
    heading: "Workspace",
    items: [
      { to: "/queue", label: "Queue", icon: "queue", roles: ALL_ROLES },
      { to: "/ingest", label: "New case", icon: "plus", roles: NEW_CASE_ROLES },
    ],
  },
  {
    heading: "Oversight",
    items: [
      {
        to: "/policy",
        label: "Policy",
        icon: "shield",
        roles: ["CREDIT_POLICY_OWNER"],
      },
      {
        to: "/health",
        label: "Health",
        icon: "audit",
        roles: ["CREDIT_POLICY_OWNER", "AUDITOR"],
      },
    ],
  },
];

/** The nav groups the given role may see, with empty groups dropped. */
export function navGroupsForRole(role: Role): NavGroup[] {
  return NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => item.roles.includes(role)),
  })).filter((group) => group.items.length > 0);
}
