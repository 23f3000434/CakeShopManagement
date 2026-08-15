# Butterlane interface

The interface serves cake shop staff handling catalogue updates, counter billing,
kitchen fulfilment, customers and stock. Preserve its existing navigation, role
permissions, API contracts, money calculations and receipt printing.

## Visual direction

Warm cream, cocoa and restrained caramel details retain the bakery identity.
Opaque surfaces and clear borders support repeated use at a busy counter. Reserve
colour for selection, primary actions and meaningful status. Product photography
helps identify cakes; missing photos use the existing cake icon fallback.

## Implementation

- `frontend/src/styles.css` contains component layouts and the receipt print rules.
- `frontend/src/refinements.css` contains the shared screen design tokens and
  responsive refinements, imported after the component styles.
- Use the system sans family for controls, labels and operational data. Body and
  form text use 14–16px equivalents; supporting labels use at least 12px. Use rem
  units, tabular numerals for money, and modest heading tracking.
- Background `#f6f1e9`, surface `#fffdf9`, primary cocoa `#492e20`, text `#34271f`,
  secondary text `#726458`, borders `#e2d9ce`.
- Green means paid/ready/completed, amber confirmed/partial, warm brown in progress,
  red cancelled/refunded or low stock. Always retain the accompanying text label.
- Controls use 8px corners. Panels use 14–16px corners. Resting panels use borders;
  overlays may use a soft shadow. Avoid decorative blur and floating hover motion.
- Maintain visible keyboard focus, named controls and dialog focus containment.
  Respect reduced motion and preserve the existing Escape/backdrop close actions.

## Responsive behaviour

Five dashboard measures share a single band on wide screens, three columns on
intermediate screens and two on phones. Navigation collapses below 850px; the
bottom bar exposes all five destinations. Search remains directly usable.

Tables scroll within their panels. POS retains its desktop catalogue/bill split
and mobile Menu/Bill switch. Long forms scroll inside dialogs. Mobile inputs use
16px text and touch controls remain reachable. Keep screen styling inside
`@media screen` so receipt printing continues using the dedicated print layout.

## Reference

Refined using Impeccable 4.3.1 from https://github.com/pbakaus/impeccable,
including its complete polish, operational UI and craft-floor guidance.
