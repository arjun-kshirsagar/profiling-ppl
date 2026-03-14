from google import genai

from app.config import get_settings

settings = get_settings()

client = genai.Client(
    vertexai=True,
    project=settings.vertex_project,
    location=settings.vertex_location,
)

try:
    models = client.models.list()
    for m in models:
        print(m.name)
except Exception as e:
    print(f"Error: {e}")
