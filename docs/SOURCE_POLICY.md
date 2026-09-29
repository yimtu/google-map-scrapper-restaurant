# Source and licensing gate

FoodScan is an acquisition and analysis tool; it does not grant rights to collect or reuse third-party data.

Before approving a production plan, the operator must confirm that the intended source, collection method, storage, and downstream use are authorized for the organization and jurisdiction involved. This confirmation is recorded in the approved run manifest.

For Google Maps specifically, current Google Maps Platform terms restrict scraping, bulk downloading, and storing certain Maps content outside the service. Place IDs have separate storage treatment in Google's documentation. FoodScan therefore treats use of Google Maps-derived content as a product/legal decision that must be reviewed by the operator; it does not represent that scraping is permitted merely because the software can perform it.

Rules:

1. No production run starts without an explicit source-policy acknowledgement.
2. The acknowledgement is stored with the approved plan and snapshot metadata.
3. Credentials and proxy contents are never included in the acknowledgement or report.
4. A source-policy acknowledgement is not legal advice and does not override provider terms or applicable law.
5. If the source or intended use changes materially, create and approve a new plan.
