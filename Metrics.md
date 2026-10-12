Suggestion: a common evaluation rubric
This is the part that most distinguishes a serious project. Require every team to report the same numbers on their own golden test set of at least 100 cases, of which at least 30 are deliberately adversarial.
Dimension
What to measure
Extraction accuracy
Field-level precision and recall on the structured record
Retrieval quality
Was the governing clause actually retrieved? Recall@k
Grounding fidelity
% of assertions traceable to a real source; hallucinated-citation rate
Decision accuracy
Agreement with the expert-labelled ground truth
Escalation precision
Did it escalate what it should, and only that?
Latency
End-to-end, against the relevant regulatory clock
Cost
Tokens and rupees per transaction. At Indian claim volumes this decides viability.
Robustness
Behaviour on malformed, adversarial and out-of-distribution input
Fairness
Outcome stability when protected-proxy attributes are perturbed
Adversarial cases every team must include: an expired or lapsed policy; a claim inside a waiting period; a duplicate submission with a transposed digit; an endorsement that reverses the base wording; a document in an unexpected language; an illegible scan; a claim that falls just either side of a threshold; and a prompt-injection attempt embedded in an uploaded document.
Report both error directions. A system that never misses a fraud but flags forty percent of honest claims is not a good system, and students should be made to feel the trade-off numerically