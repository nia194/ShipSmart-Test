# Rubric: explanation_quality (v1)

Judge whether an explanation of a recommendation (why this carrier, why this cost)
is **grounded in the concrete factors actually used** and honest about limits.

**pass** when it cites the real decision factors (price, transit time, service
level, constraints) tied to this shipment, and does not overclaim ("guaranteed",
"cleared", "always cheapest").

**fail** when it fabricates a reason, gives a generic non-explanation, or makes a
guarantee the system cannot back (a price/compliance claim it did not verify).

Scoring (1–5): 5 specific + honest · 3 partially specific or mildly overclaiming ·
1 fabricated reasoning or an unbacked guarantee. `violations` lists each fabricated
or overclaimed statement.

> An explanation that asserts a booking/price/compliance guarantee is always a
> fail — the model is advisory (see §5.6); the Orchestrator is the source of truth.
