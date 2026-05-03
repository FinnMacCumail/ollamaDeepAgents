# NetBox AI Assistant: Cloud vs Local - Which Wins?

I've been comparing two AI approaches for querying network infrastructure data:

## The Competitors

**🌐 Cloud AI (Claude SDK)**
- Uses Anthropic's Claude AI (paid service)
- Data goes to the cloud
- Professional web interface

**💻 Local AI (LangChain + Ollama)**
- Runs completely on local server
- Zero costs, complete privacy
- Command-line interface

## The Test

I ran 7 identical queries against my NetBox infrastructure database - things like "show me all cables connected to this device" or "list all sites with their device counts."

## The Results

**Cloud AI: 7/7 queries succeeded (100%)** ✅
**Local AI: 5/7 queries succeeded (71%)** ⚠️

## Why the Difference?

Two main reasons:

1. **Better Instructions (30%)**: The cloud version had clearer warnings about what filters to avoid when querying the database

2. **Smarter Model (60%)**: Claude's AI could figure out patterns from one example and apply them everywhere. The local model needed more explicit guidance.

## What I Learned

- Proper instructions matter MORE than I expected
- Claude is genuinely better at "connecting the dots"
- Local models CAN work well with the right setup

## Next Steps

I'm building an improved solution using:
- **DeepAgents framework** (smarter architecture)
- **Better local models** (qwen2.5:32b, deepseek-r1:70b)
- **SKILLS system** - teaches the AI specific domain knowledge only when needed (like "don't use this type of database filter")
- **Automatic error recovery** - catches mistakes and retries with corrections

Think of SKILLS like a reference manual that the AI can consult when it encounters specific tasks, instead of trying to remember everything upfront.

This means:
- ✅ No cloud costs
- ✅ Complete data privacy
- ✅ Nearly same performance as Claude

The best of both worlds!

---

**Technical Report**: Full 460-line analysis available with LangSmith tracing data, comparative analysis, and implementation details.
