# Interview guide

Target: 20 developers who run tool-using or multi-agent systems with real permissions (email, files, code, APIs). Not people who only use chat assistants.

## Stage 1: problem interviews (all 20, 20 minutes, no pitch)

Goal: understand the pain, not validate MUFFIN. Talk about their life, ask about the past, listen 90% of the time. Do not mention MUFFIN, do not show the demo, and never ask "would you use this?" (people say yes to be polite).

Look for: pain, frequency, current workarounds, budget.

1. Walk me through the last agent you ran with real permissions. What can it touch?
2. Tell me about a time it did something you did not expect. What did you do? How long did it take?
3. How do you limit what it can do today? (prompt, allowlist, sandbox, nothing)
4. How do you find out afterward what it did?
5. What did it cost you (time, money, trust)? What would it cost if this never got solved?
6. What have you tried? What happened? What did you build yourself?
7. Who else on your team feels this?

## Stage 2: solution interviews (only after the problem brief says the pain is real)

Show the README's email-blocking demo (section 12.2) as an early concept. Ask "what is confusing?" not "do you like it?". Watch reactions, not words. Before ending, ask for a commitment: a design-partner trial on one real workflow, a signed LOI, or payment.

## After each call (within 10 minutes)

Add one row to `interviews.csv`. Quote their words in `pain`. When all 20 are done, write `problem-brief.md` from the rows: it is worth more than any feature spec.
