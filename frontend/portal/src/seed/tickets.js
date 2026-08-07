// TEMPORARY - deleted by Phase 3 (helpdesk API). See seed/README.md.

export const SEED_TICKETS = [
  {
    id: "IT-10942",
    subject: "VPN disconnects when joining Teams calls",
    meta: "GlobalProtect 6.1 - Reported from HQ Wi-Fi",
    category: "Network",
    status: "Open",
    date: "4 Aug 2026"
  },
  {
    id: "IT-10938",
    subject: "Microsoft 365 licence for new hire (S. Malik)",
    meta: "Awaiting manager approval",
    category: "Software",
    status: "Pending",
    date: "2 Aug 2026"
  },
  {
    id: "IT-10931",
    subject: "Battery replacement - ThinkPad X1 Carbon",
    meta: "Depot repair completed, collected",
    category: "Hardware",
    status: "Resolved",
    date: "29 Jul 2026"
  },
  {
    id: "IT-10925",
    subject: "Shared drive permissions on \\\\FS02\\Finance",
    meta: "Access granted, read-only",
    category: "Access",
    status: "Resolved",
    date: "24 Jul 2026"
  },
  {
    id: "IT-10919",
    subject: "HP LaserJet M479 jams on duplex printing",
    meta: "Fuser roller replaced on site",
    category: "Hardware",
    status: "Resolved",
    date: "21 Jul 2026"
  },
  {
    id: "IT-10914",
    subject: "MFA re-enrolment after phone upgrade",
    meta: "Resolved by MateAssist without escalation",
    category: "Access",
    status: "Resolved",
    date: "18 Jul 2026"
  }
];

/** Ticket statuses are a closed set enforced by the Phase 3 state machine (D-121). */
export const TICKET_STATUSES = ["Open", "Pending", "Resolved"];
