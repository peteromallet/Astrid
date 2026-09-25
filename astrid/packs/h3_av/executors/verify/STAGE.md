# Verify staging

Verification receives the preparation and composition manifests, an explicit
managed `candidate` file, and the optional authoritative source. It never opens
the compose attempt's candidate pathname. It hashes the settled candidate and requires
exact source equality for a wholly protected request. A partial protected
request must provide structured `protected_samples` evidence for every
protected interval: matching source/candidate sample hashes, a positive sample
count, and either the built-in decoded-sample witness or an explicit external
witness digest. Matching interval lists or `unchanged_permissions` claims are
insufficient, and copied/non-media candidates fail closed.

Request, asset, schedule, graph, and Runtime output provenance must remain
consistent with preparation. A missing or contradictory provenance field is a
verification failure, not a warning.

Coverage comparison excludes only observational file paths; measured stream
coverage, candidate hash/size, and preservation evidence must still match.
