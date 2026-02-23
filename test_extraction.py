import asyncio, os, time
from dotenv import load_dotenv
load_dotenv()
from src.models.patient import Patient
from src.providers.extraction.gemini_gpt import GeminiGPTProvider

async def test():
    provider = GeminiGPTProvider(api_key=os.environ["GEMINI_API_KEY"])
    start = time.perf_counter()
    result = await provider.extract(
        transcript="Patient: I have had a headache for 3 days and nausea.\nDoctor: The long screen hours might be triggering this. Take Paracetamol 500mg twice daily. Reduce screen time. Get a CBC test done.\nPatient: I have a family history of migraine. I am also allergic to peanuts. \nDoctor: I would suggest you to avoid peanuts and get a gut test also in addition toCBC test.",
        patient=Patient(name="Test", age=30, gender="Male"),
    )
    elapsed = time.perf_counter() - start
    print(result.model_dump_json(indent=2))
    print(f"\nGemini response time: {elapsed:.2f}s")

asyncio.run(test())
