# Our Products — Product Composer and Product Project Factory

## Mission

Vishnu is the private owner system and product factory. Vishnu itself is never a customer deliverable.

`Our Products` turns internal Vishnu capabilities and new customer requirements into separate **Product Projects**. A Product Project may become an AI employee, agent, agent team, workflow, automation, tool, integration, SaaS application, knowledge system, API, desktop/mobile application, or complete business system.

The operating rule is:

```text
Requirement
  -> inspect what Vishnu already has
  -> REUSE qualified capabilities
  -> EXTEND partial matches
  -> CREATE only the missing pieces
  -> create a separate Product Project
  -> let governed Vishnu Projects perform missing development
  -> test and qualify
  -> freeze/version
  -> package/build/license/deploy
  -> customer receives only the product
```

## Vishnu stays private

The following remain owner-side Vishnu concerns and are not copied into a customer Product Project merely because a capability was used during composition:

- Vishnu Home, Conversations, Memory, Projects, Owner Controls, and private management UI
- owner conversations, memories, knowledge, credentials, signing private keys, and account data
- unrelated agents, workflows, automations, projects, products, or customers
- the complete Vishnu source tree or master autonomous runtime
- infrastructure credentials and product signing authority
- another customer's data, private knowledge, rules, code, or secrets

A client-facing product contains only the bounded product components, configuration, UI/backend code, runtime requirements, client-specific integrations/knowledge, and delivery assets that belong to that Product Project.

## Product Requests

A Product Request represents an internal or external requirement such as:

> Build a real-estate sales employee that researches prospects, identifies decision makers, sends outreach, updates CRM, schedules meetings, and scores properties.

A request stores:

- title
- client name or internal use
- natural-language requirement
- requested or inferred product type
- AI mode
- preferred delivery targets
- commercial-use classification
- generated Product Blueprint
- linked Vishnu Project ID
- linked Product ID

A named-client request defaults to `client_specific` unless the owner deliberately chooses a different use classification. Internal requests default to `internal_reusable`.

## Capability Catalog

The Capability Catalog is the reusable inventory the Product Composer searches before new development begins.

Current catalog sources include:

- qualified Vishnu worker/agent profiles
- governed tools
- automations
- workflows
- integrations/connectors
- existing Product Projects
- product components
- manually registered reusable modules
- explicitly promoted/generalized product components

Each capability records:

- type
- source and stable source reference
- description/tags
- client scope
- commercial-use state
- qualification state
- whether it is reusable/exportable
- AI modes/platform metadata where relevant
- inputs/outputs/dependencies/permissions metadata

Catalog synchronization records descriptors and references. It does not package Vishnu's master runtime into a product.

## Client isolation

Capability scope is part of the reuse authority.

### Internal request

An internal request can match only `shared` reusable capabilities.

### Client request

A client request can match:

- `shared` reusable capabilities
- capabilities explicitly scoped to that same client

It cannot match a different client's private capability.

A generic classification edit cannot move a client-scoped capability to `shared`. The only supported path is an explicit Product Composer promotion in which the owner marks the component as generalized and documents that client-private data/rules were removed.

Client-derived generic capability promotion therefore follows:

```text
Client Product Component
  -> owner reviews/generalizes
  -> remove client data, knowledge, secrets, pricing, thresholds and proprietary rules
  -> document the generalization
  -> promote shared reusable capability
```

Without that explicit step the capability remains client-scoped.

## Reuse / Extend / Create matching

The Product Composer converts a requirement into bounded requirement units and scores them against available capabilities.

A decision is made for every unit:

- `reuse` — the existing capability substantially covers the requirement
- `extend` — a useful existing capability exists but requires bounded development
- `create` — no sufficiently close reusable capability exists

The Product Blueprint records:

- recommended product type
- AI mode
- target platforms
- commercial classification
- overall existing-capability coverage
- reuse/extend/create counts
- matched capability and score for each requirement
- missing development work

The deterministic matcher is intentionally explainable. It is a safe baseline that can later be supplemented by model-assisted semantic retrieval, but product creation authority does not depend on a model returning an opaque result.

## Product Project creation

`Create Product Project & Start Vishnu` creates two linked owner records:

1. a normal Vishnu **Project** that owns development work
2. a separate **Product** record that owns product configuration, components, versions, builds, licensing, and delivery

The Project contains tasks for:

- each missing capability
- each capability extension
- integration of selected reusable components
- Product Project qualification
- final freeze/build/release preparation

The Product contains only the selected capability references/configuration and Product Project state. It does not inherit the whole Vishnu system.

Creation is retry/idempotency-safe:

- the Project link is persisted immediately
- the Product link is persisted immediately after product creation
- retries reuse those records
- selected capabilities are reconciled instead of duplicated
- lineage has a uniqueness boundary

A network retry therefore does not manufacture duplicate Product Projects.

## Governed automatic Vishnu work

On the first Product Project creation, Product Composer can start actual development through the existing Vishnu Project work stack:

```text
Product Composer
  -> ProjectWorkService
  -> existing P10 goal/plan/work projection
  -> ProjectAutonomyService ACTIVE
  -> existing execution / approvals / verification / recovery / emergency stop
```

Product Composer does **not** introduce a second autonomous executor.

The normal Vishnu governance system remains authoritative for:

- tool permissions
- approval requirements
- plan validation
- task dependencies
- execution budgets
- recovery/retry behavior
- verification
- completion authority
- emergency stop

Automatic start occurs only on the first successful Product Project creation. If the same HTTP request is replayed, additional autonomous work is not silently advanced. The owner can explicitly choose **Start / Continue Vishnu Work** to advance an existing Product Project.

If work cannot start, Product creation remains valid and the UI reports the blocked state instead of claiming execution occurred.

## Commercial-use states

Products and reusable capabilities can be classified as:

- `internal_only`
- `internal_reusable`
- `internal_sellable`
- `commercial`
- `client_specific`
- `template`
- `experimental`

This supports the company's intended model: Vishnu may build something for internal use first, later generalize it, and then use the same underlying capability as a foundation for products that can be sold.

## Product lineage

Product lineage records where a Product Project came from without copying those sources into the customer build.

Relations include:

- Product Request -> `created_from`
- Vishnu Project -> `implemented_by`
- reusable capability -> `reuse`
- reusable capability -> `extend`

Lineage lets the owner answer questions such as:

- Which internal capability does this product use?
- Which client request created it?
- Which Vishnu Project implemented the missing work?
- Which reusable base/version should be reviewed when an improvement is available?

Lineage is metadata and dependency history, not permission to copy client-private data into other products.

## Templates

An internal or commercial product can become a reusable product foundation. Templates are starting points, not customer clones.

A new Product Request created from a template still receives its own:

- client scope
- configuration
- integrations
- AI policy
- knowledge
- permissions
- versions
- builds
- licenses
- deployments

## Product delivery

After composition and development, existing Our Products infrastructure handles:

1. qualification
2. immutable version freeze
3. sanitized product manifest/package generation
4. product signing
5. licensing
6. target build request
7. local or platform runner compilation
8. target signing/provisioning/notarization/attestation when applicable
9. checksum/evidence verification
10. download/deployment

Current target architecture includes Web, PWA, API, Worker, Android, iOS, Windows, macOS, Linux, and Docker/OCI.

Real production platform artifacts remain fail-closed unless their real environment-owned credentials and target qualification are present. The system never invents an Android signing keystore, Apple identity/provisioning profile, Windows certificate, or Docker signing authority.

## UI

`Our Products` exposes four primary owner factory views:

- **Products** — all Product Projects and their build/distribution workspaces
- **Requests** — requirements and Product Blueprints
- **Reusable Components** — the scoped Capability Catalog
- **Templates** — reusable product foundations

A Product workspace also exposes Commercial and Lineage views in addition to the existing Overview, AI & Models, Platforms, Components, Build & Export, Manifest, and Package & License functions.

## Completion definition

The Product Composer feature is complete only when repository qualification proves:

- request analysis and matching
- same-client reuse and cross-client isolation
- internal request isolation from all client-private capabilities
- explicit generalization requirement
- retry/idempotency safety
- Project + Product creation
- governed work handoff
- lineage/classification
- responsive desktop/mobile Product Composer UI
- existing Our Products packaging/licensing/platform behavior remains green

Production platform distribution additionally requires the real external signing/provisioning infrastructure documented in `OUR_PRODUCTS_PRODUCTION_QUALIFICATION.md`.
