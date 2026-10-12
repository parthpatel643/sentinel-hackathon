# Sentinel Platform

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Control-room operators monitor cameras and alerts and investigate vehicle
sightings. Administrators manage access, integrations, watchlists, and retention.
Field officers use a separate mobile web interface.

## Product Purpose

Connect camera monitoring with number-plate searches, route reconstruction,
watchlist alerts, and evidence. The documented usability goal is to let an
untrained constable find a vehicle in under 30 seconds.

## Operating Context

The operator workspace gives monitoring and investigation equal prominence,
as confirmed for the redesign. Dark control rooms and daytime office or field
use require both dark and light themes. New sessions open in light mode;
existing theme preferences are preserved. The workspace is a departures
gate board for vehicles: ranked rows of ink on cool paper, one amber signal
reserved for what needs action, and a perforated sighting pass for each
read (see [DESIGN.md](DESIGN.md)). The board is scoped to the operator's
jurisdiction, shows one row per vehicle rather than one per read, and rolls
up by district so it stays readable at statewide scale. Overview workspaces
support camera filtering, map/list switching, and direct transitions from
detections and watchlist matches into investigation and triage.

## Capabilities and Constraints

Preserve existing authentication, role checks, camera streaming, onboarding,
search, evidence, and offline field-report workflows. English, Hindi, and
Gujarati are supported. Camera names, plates, evidence, and API data remain
unaltered. Unknown or unavailable information must not look like a healthy state.

## Brand Commitments

Keep the Sentinel name. Use plain, professional language and an interface that
stays calm under pressure. Locally installed agent skills are not product files
and must not be committed.

## Evidence on Hand

The current application, API types, and [experience specification](docs/03-UX-DESIGN.md)
document the supported workflows. Runtime data is not a source of promotional claims.

## Accessibility & Inclusion

Use labels alongside status colors, visible keyboard focus, accessible forms,
responsive layouts, and readable typography for all three supported scripts.
