# Smart model routing

Simple questions should not cost premium money. A bot set to **Auto**
answers simple questions free on the local model and only sends hard
work to its configured premium provider — so the wallet lasts longer.

## How it works

Per bot, in **Make a bot** (Smart routing):

- **Off — always this provider** (default): the bot always uses its
  configured provider and model.
- **Auto — simple free on local, hard to premium**: before each chat,
  LocalBotz checks the question. If it is short (300 characters or
  fewer) and asks for none of the hard-work words below, it is answered
  on the local model (LM Studio / Qwen3.5) instead — free. Anything
  else goes to the bot's configured provider as usual.

Hard-work words (any of them sends the question to the premium
provider): draft, write, proposal, quotation, quote, tender, boq,
contract, analys…, research, compare, plan, strategy, review, audit,
summar…, explain, design, build, code, calculat…, estimat…,
translate, legal.

Examples:

- "What time is the site meeting?" → local, free.
- "Draft the quotation for Pearl Homes" → premium (draft + quotation).
- A 500-word brief → premium (too long to be simple).

## What you see

The chat footer says so when a question was routed: "routed free to
local (from claude)" — so you can see what the bot did and what it
cost (nothing). The API reply also carries `routed_from` (the
provider the question would have used) and `routed_to` (the provider
that answered).

## Honest limits

- Routing never routes a bot that is already on a local provider —
  there is nothing to save.
- Routing is a word-and-length check, not a judgement of the question.
  A short question that needs deep knowledge still goes local if it
  has no hard-work words. Turn it Off per bot if you want that bot to
  always use premium.
- If the local model is not running when a question is routed to it,
  the chat fails honestly ("Could not reach LM Studio…") instead of
  silently spending premium money. Start LM Studio, or turn routing
  Off for that bot.
