"""Business OS Platform v1.0 — canonical event names.

The existing `business_events` table stores events.
These constants standardize future event types.
"""

MASTER_PRODUCT_CREATED = "MasterProductCreated"
MASTER_PRODUCT_SEEDED = "MasterProductSeeded"
CHANNEL_MAPPED = "ChannelMapped"
REGISTRY_BACKFILL = "RegistryBackfill"
DECISION_CREATED = "DecisionCreated"
DECISION_APPROVED = "DecisionApproved"
DECISION_EXECUTED = "DecisionExecuted"
DECISION_MEASURED = "DecisionMeasured"
LISTING_UPDATED = "ListingUpdated"
PRICE_CHANGED = "PriceChanged"
CAMPAIGN_CHANGED = "CampaignChanged"
INVENTORY_CHANGED = "InventoryChanged"
