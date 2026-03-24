import asyncio, os, sys, traceback
os.environ["ANTHROPIC_API_KEY"] = "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"
sys.path.insert(0, '.')
from agent import DocumentationAgent
from store import JobStore

async def test():
    store = JobStore()
    store.create("test-x", "https://github.com/PrantikM/Rag-chatbot")
    agent = DocumentationAgent(job_id="test-x", repo_url="https://github.com/PrantikM/Rag-chatbot", github_token=None, store=store)
    try:
        docs = await agent.run()
        print("SUCCESS!", list(docs.keys()) if isinstance(docs, dict) else docs)
    except Exception as e:
        tb = traceback.format_exc()
        with open("error_output.txt", "w") as f:
            f.write(tb)
        print(f"ERROR: {repr(e)}")
        print(tb[-500:])

asyncio.run(test())
